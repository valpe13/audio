import json
import math
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "xtts_api" / "reference_audio" / "natalia_shtin"
PAGE = WORK / "natalia_page.html"
RAW = WORK / "raw"
PROCESSED = WORK / "processed"
MERGED = WORK / "natalia_shtin_clean_reference.wav"
MANIFEST = WORK / "natalia_shtin_clean_reference.manifest.json"
PAGE_URL = "https://audio-production.ru/baza-diktorov/top-woman-voices/nalia-shtin/"


def download_page() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    if PAGE.exists() and PAGE.stat().st_size > 1000:
        return
    req = urllib.request.Request(PAGE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        PAGE.write_bytes(response.read())


def extract_urls() -> list[str]:
    data = PAGE.read_bytes()
    pattern = rb"https://audio-production\.ru/wp-content/uploads/2021/02/[^\"'<> ]+\.mp3"
    raw_urls = sorted(set(re.findall(pattern, data, flags=re.IGNORECASE)))
    urls: list[str] = []
    for raw in raw_urls:
        url = raw.decode("utf-8", errors="ignore")
        # HTML was saved through UTF-8 path; non-ascii URLs can be mojibake in console,
        # but bytes are still usable after percent-encoding path segments.
        parsed = urllib.parse.urlsplit(url)
        path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/")
        urls.append(urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", "")))
    return sorted(set(urls))


def download_file(url: str, out: Path) -> None:
    if out.exists() and out.stat().st_size > 1024:
        return
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": PAGE_URL})
    with urllib.request.urlopen(req, timeout=60) as response:
        out.write_bytes(response.read())


def ffmpeg_path() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def convert_to_wav(mp3: Path, wav: Path, sr: int = 24000) -> None:
    cmd = [
        ffmpeg_path(),
        "-y",
        "-i",
        str(mp3),
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-vn",
        "-acodec",
        "pcm_s16le",
        str(wav),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def trim_edges(y: np.ndarray, sr: int, threshold: float = 0.018, pad_sec: float = 0.10) -> np.ndarray:
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32)
    frame = max(256, int(0.025 * sr))
    hop = max(128, frame // 2)
    if len(y) < frame:
        return y
    rms = []
    starts = []
    for start in range(0, len(y) - frame + 1, hop):
        chunk = y[start : start + frame]
        rms.append(float(np.sqrt(np.mean(chunk * chunk))))
        starts.append(start)
    if not rms:
        return y
    rms_arr = np.asarray(rms)
    active = np.where(rms_arr > threshold)[0]
    if len(active) == 0:
        return y
    pad = int(pad_sec * sr)
    start = max(0, starts[int(active[0])] - pad)
    end = min(len(y), starts[int(active[-1])] + frame + pad)
    return y[start:end]


def gentle_voice_enhance(y: np.ndarray, sr: int) -> np.ndarray:
    # Conservative reference cleanup: normalize, fade, and avoid heavy denoise that can
    # imprint artifacts into XTTS speaker conditioning.
    y = y.astype(np.float32)
    y = y - float(np.mean(y))
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 1e-6:
        y *= 0.72 / peak
    fade = min(len(y) // 5, int(0.035 * sr))
    if fade > 1:
        y[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        y[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return np.clip(y, -0.95, 0.95)


def crossfade_concat(parts: list[np.ndarray], sr: int, crossfade_sec: float = 0.08) -> np.ndarray:
    if not parts:
        return np.zeros(1, dtype=np.float32)
    out = parts[0]
    for part in parts[1:]:
        n = min(int(crossfade_sec * sr), len(out) // 4, len(part) // 4)
        if n <= 1:
            out = np.concatenate([out, part])
            continue
        fade_out = np.linspace(1.0, 0.0, n, dtype=np.float32)
        fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
        out = np.concatenate([out[:-n], out[-n:] * fade_out + part[:n] * fade_in, part[n:]]).astype(np.float32)
    return out


def wav_info(path: Path) -> dict:
    with wave.open(str(path), "rb") as w:
        frames = w.getnframes()
        sr = w.getframerate()
        return {"path": str(path.relative_to(ROOT)), "sample_rate": sr, "channels": w.getnchannels(), "frames": frames, "duration_sec": round(frames / sr, 3)}


def main() -> None:
    download_page()
    urls = extract_urls()
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    processed = []
    sources = []
    for idx, url in enumerate(urls, start=1):
        raw_path = RAW / f"{idx:02d}_natalia_shtin.mp3"
        wav_path = PROCESSED / f"{idx:02d}_natalia_shtin_clean.wav"
        print(f"Downloading {idx}/{len(urls)}: {url}")
        download_file(url, raw_path)
        convert_to_wav(raw_path, wav_path)
        y, sr = sf.read(wav_path, dtype="float32", always_2d=False)
        y = gentle_voice_enhance(trim_edges(y, sr), sr)
        sf.write(wav_path, y, sr, subtype="PCM_16")
        processed.append(y)
        sources.append({"url": url, "raw": str(raw_path.relative_to(ROOT)), "processed": str(wav_path.relative_to(ROOT)), "info": wav_info(wav_path)})
    if not processed:
        raise SystemExit("No audio files found/downloaded")
    merged = crossfade_concat(processed, 24000)
    # Keep reference in XTTS-friendly range; first 90 sec is enough and avoids excessive music/noise exposure.
    max_len = int(90 * 24000)
    if len(merged) > max_len:
        merged = merged[:max_len]
    merged = gentle_voice_enhance(merged, 24000)
    sf.write(MERGED, merged, 24000, subtype="PCM_16")
    manifest = {
        "source_page": PAGE_URL,
        "permission_asserted_by_user": True,
        "rights_note": "User stated they have permission to use and process Natalia Shtin voice for TTS/voice cloning.",
        "urls_found": len(urls),
        "sources": sources,
        "merged": wav_info(MERGED),
        "processing": ["download public mp3 URLs from authorized page", "convert to 24k mono WAV", "trim edge silence", "gentle normalization/fades", "short crossfade concat"],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest["merged"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
