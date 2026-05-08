import json
import math
import re
import subprocess
import tempfile
import urllib.request
import wave
from html import unescape
from pathlib import Path

import imageio_ffmpeg
import librosa
import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
XTTS_DIR = ROOT / "xtts_api"
PAGE_URL = "https://zvukipro.com/razgovori/2410-zvuki-golosovogo-soobschenija-ot-devushki.html"
PAGE_HTML = XTTS_DIR / "reference_downloads_page.html"
REF_DIR = XTTS_DIR / "reference_audio"
RAW_DIR = REF_DIR / "raw"
CLIPS_DIR = REF_DIR / "processed_clips"
MERGED_WAV = REF_DIR / "girl_voice_messages_merged.wav"
MANIFEST = REF_DIR / "girl_voice_messages_merged.manifest.json"
SAMPLE_RATE = 24000

# Neutral/non-explicit clips from the public page. Keep the merged reference
# focused on one speaker and ordinary voice-message intonation.
PREFERRED_SLUGS = [
    "dobrogo-vremni-sutok",
    "utro",
    "vecher",
    "che-delaesh",
    "kak-dela",
    "knigu",
    "nogti",
    "ne-ponjala",
    "podojdi",
    "celyj",
    "smajliki",
    "ja-pozzhe-napishu",
    "ne-otvechala",
    "serial",
    "film-smotrju",
    "posovetuy-film",
    "muzyki",
    "skinesh",
    "zhdat3",
    "davaybudu-jdat",
    "dogovorilis",
    "spat",
    "do-zavtra",
    "poka-poka",
    "spokoynoy-nochi",
    "sladkih-snov",
]


def download(url: str, path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        data = response.read()
    path.write_bytes(data)


def extract_urls(html: str) -> list[str]:
    urls = re.findall(r'data-url="([^"]+\.mp3)"', html)
    seen = set()
    unique = []
    for url in urls:
        url = unescape(url)
        if url not in seen:
            unique.append(url)
            seen.add(url)
    return unique


def decode_with_ffmpeg(src: Path, dst: Path) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "wav",
        str(dst),
    ]
    subprocess.run(cmd, check=True)


def trim_edges(y: np.ndarray, sr: int) -> np.ndarray:
    if y.size == 0:
        return y
    intervals = librosa.effects.split(y, top_db=34, frame_length=1024, hop_length=256)
    if len(intervals) == 0:
        return y
    pad = int(0.08 * sr)
    start = max(0, int(intervals[0][0]) - pad)
    end = min(len(y), int(intervals[-1][1]) + pad)
    return y[start:end]


def normalize(y: np.ndarray, peak: float = 0.86) -> np.ndarray:
    if y.size == 0:
        return y
    y = y.astype(np.float32)
    y = y - float(np.mean(y))
    current = float(np.max(np.abs(y)))
    if current > 1e-6:
        y = y * (peak / current)
    return np.clip(y, -0.98, 0.98)


def fade(y: np.ndarray, sr: int, seconds: float = 0.025) -> np.ndarray:
    n = min(len(y) // 3, max(1, int(seconds * sr)))
    if n > 1:
        y[:n] *= np.linspace(0.0, 1.0, n, dtype=np.float32)
        y[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
    return y


def crossfade_join(parts: list[np.ndarray], sr: int, crossfade_sec: float = 0.055) -> np.ndarray:
    if not parts:
        return np.zeros(0, dtype=np.float32)
    cf = int(crossfade_sec * sr)
    out = parts[0].copy()
    for part in parts[1:]:
        if len(out) < cf or len(part) < cf:
            out = np.concatenate([out, np.zeros(int(0.03 * sr), dtype=np.float32), part])
            continue
        a = out[-cf:]
        b = part[:cf]
        ramp = np.linspace(0.0, 1.0, cf, dtype=np.float32)
        mixed = a * (1.0 - ramp) + b * ramp
        out = np.concatenate([out[:-cf], mixed, part[cf:]])
    return out


def wav_stats(path: Path) -> dict:
    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.getnframes()
        sr = wav_file.getframerate()
        return {
            "path": str(path.relative_to(ROOT)),
            "channels": wav_file.getnchannels(),
            "sample_rate": sr,
            "frames": frames,
            "duration_sec": round(frames / float(sr), 3),
        }


def main() -> None:
    REF_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    if not PAGE_HTML.exists():
        download(PAGE_URL, PAGE_HTML)
    html = PAGE_HTML.read_text(encoding="utf-8", errors="ignore")
    urls = extract_urls(html)
    selected = []
    for slug in PREFERRED_SLUGS:
        match = next((url for url in urls if slug in url), None)
        if match:
            selected.append(match)

    processed = []
    parts = []
    total = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for idx, url in enumerate(selected, 1):
            raw_path = RAW_DIR / f"{idx:02d}_{Path(url).name}"
            if not raw_path.exists() or raw_path.stat().st_size == 0:
                download(url, raw_path)
            wav_tmp = tmp_dir / f"{idx:02d}.wav"
            decode_with_ffmpeg(raw_path, wav_tmp)
            y, sr = sf.read(wav_tmp, dtype="float32", always_2d=False)
            if y.ndim > 1:
                y = np.mean(y, axis=1)
            if sr != SAMPLE_RATE:
                y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)
                sr = SAMPLE_RATE
            y = fade(normalize(trim_edges(y, sr)), sr)
            duration = len(y) / float(sr) if sr else 0.0
            if duration < 0.35:
                continue
            clip_path = CLIPS_DIR / f"{idx:02d}_{raw_path.stem}.wav"
            sf.write(clip_path, y, sr, subtype="PCM_16")
            processed.append(
                {
                    "source_url": url,
                    "raw_path": str(raw_path.relative_to(ROOT)),
                    "processed_path": str(clip_path.relative_to(ROOT)),
                    "duration_sec": round(duration, 3),
                }
            )
            parts.append(y)
            total += duration
            if total >= 45.0:
                break

    merged = normalize(crossfade_join(parts, SAMPLE_RATE), peak=0.84)
    if len(merged) > int(60 * SAMPLE_RATE):
        merged = merged[: int(60 * SAMPLE_RATE)]
    sf.write(MERGED_WAV, merged, SAMPLE_RATE, subtype="PCM_16")

    manifest = {
        "page_url": PAGE_URL,
        "page_html": str(PAGE_HTML.relative_to(ROOT)),
        "rights_warning": "Use downloaded voice references only if you have rights/permission, especially for publishing or monetization.",
        "selected_clip_count": len(processed),
        "target_format": {"sample_rate": SAMPLE_RATE, "channels": 1, "subtype": "PCM_16"},
        "merged_reference": wav_stats(MERGED_WAV),
        "clips": processed,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
