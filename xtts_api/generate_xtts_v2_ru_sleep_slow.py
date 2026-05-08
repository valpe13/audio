import argparse
import contextlib
import inspect
import json
import os
import re
import wave
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

os.environ.setdefault("COQUI_TOS_AGREED", "1")

from TTS.api import TTS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REF = ROOT / "xtts_api" / "reference_audio" / "girl_voice_messages_merged.wav"
DEFAULT_OUT = ROOT / "xtts_api" / "outputs" / "xtts_v2_ru_sleep_slow_merged_ref_test.wav"
TMP_DIR = ROOT / "xtts_api" / "outputs" / "_sleep_slow_chunks"

TEXT_CHUNKS = [
    (
        "Представьте себе тёплый вечер у тихого озера. "
        "Воздух почти неподвижен, и всё вокруг постепенно становится мягче."
    ),
    (
        "Вы делаете спокойный вдох. "
        "И затем медленно отпускаете напряжение, как будто оно растворяется в сумерках."
    ),
    (
        "Далёкий лес темнеет на горизонте. "
        "Небо над водой остаётся светлым, ровным и очень глубоким."
    ),
    (
        "Пусть внимание просто следует за голосом. "
        "Не нужно стараться; достаточно слушать, дышать ровно и отдыхать."
    ),
]


def clean_text(text: str) -> str:
    text = text.replace("ё", "ё")
    text = re.sub(r"[\u0300\u0301]", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("--", " — ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def wav_stats(path: Path) -> dict:
    path = Path(path).resolve()
    with contextlib.closing(wave.open(str(path), "rb")) as wav_file:
        frames = wav_file.getnframes()
        sr = wav_file.getframerate()
        try:
            display_path = str(path.relative_to(ROOT))
        except ValueError:
            display_path = str(path)
        return {
            "path": display_path,
            "channels": wav_file.getnchannels(),
            "sample_rate": sr,
            "frames": frames,
            "duration_sec": round(frames / float(sr), 3),
        }


def trim_outer_silence(y: np.ndarray, sr: int, pad_sec: float = 0.07) -> np.ndarray:
    intervals = librosa.effects.split(y, top_db=43, frame_length=2048, hop_length=512)
    if len(intervals) == 0:
        return y
    pad = int(pad_sec * sr)
    start = max(0, int(intervals[0][0]) - pad)
    end = min(len(y), int(intervals[-1][1]) + pad)
    return y[start:end]


def soften_and_normalize(y: np.ndarray, sr: int, target_peak: float = 0.78) -> np.ndarray:
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32)
    y = trim_outer_silence(y, sr)
    fade_len = min(len(y) // 4, int(0.030 * sr))
    if fade_len > 1:
        y[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        y[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 1e-6:
        y = y * (target_peak / peak)
    return np.clip(y, -0.98, 0.98).astype(np.float32)


def room_tone(sr: int, seconds: float, seed: int, level: float = 0.0012) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = max(1, int(seconds * sr))
    noise = rng.normal(0.0, level, n).astype(np.float32)
    fade = min(n // 3, int(0.08 * sr))
    if fade > 1:
        noise[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        noise[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return noise


def append_crossfaded(parts: list[np.ndarray], new: np.ndarray, sr: int, crossfade_sec: float) -> None:
    if not parts or crossfade_sec <= 0:
        parts.append(new)
        return
    prev = parts.pop()
    n = min(int(crossfade_sec * sr), len(prev) // 3, len(new) // 3)
    if n <= 1:
        parts.extend([prev, new])
        return
    fade_out = np.linspace(1.0, 0.0, n, dtype=np.float32)
    fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
    joined = np.concatenate([prev[:-n], prev[-n:] * fade_out + new[:n] * fade_in, new[n:]])
    parts.append(joined.astype(np.float32))


def max_adjacent_repetition(y: np.ndarray, sr: int, window_ms: int = 140) -> dict:
    window = max(128, int(sr * window_ms / 1000))
    hop = max(64, window // 2)
    if len(y) < window * 3:
        return {"max_corr": 0.0, "at_sec": 0.0, "window_ms": window_ms}
    max_corr = -1.0
    max_at = 0
    for start in range(0, len(y) - 2 * window, hop):
        a = y[start : start + window]
        b = y[start + window : start + 2 * window]
        a = a - float(np.mean(a))
        b = b - float(np.mean(b))
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom <= 1e-8:
            continue
        corr = float(np.dot(a, b) / denom)
        if corr > max_corr:
            max_corr = corr
            max_at = start
    return {"max_corr": round(max_corr, 4), "at_sec": round(max_at / float(sr), 3), "window_ms": window_ms}


def generate_chunk(tts: TTS, text: str, ref: Path, out: Path, args: argparse.Namespace) -> None:
    kwargs = {
        "text": clean_text(text),
        "speaker_wav": str(ref),
        "language": "ru",
        "file_path": str(out),
        "temperature": args.temperature,
        "top_p": args.top_p,
        "top_k": args.top_k,
        "repetition_penalty": args.repetition_penalty,
        "length_penalty": args.length_penalty,
        "speed": args.speed,
    }
    if "split_sentences" in inspect.signature(tts.tts_to_file).parameters:
        kwargs["split_sentences"] = False
    tts.tts_to_file(**kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate slow Russian sleep-lecture XTTS v2 sample with chunk stitching.")
    parser.add_argument("--reference", default=str(DEFAULT_REF), help="Speaker reference WAV.")
    parser.add_argument("--output", default=str(DEFAULT_OUT), help="Output WAV path.")
    parser.add_argument("--cpu", action="store_true", help="Force CPU instead of CUDA.")
    parser.add_argument("--temperature", type=float, default=0.62, help="Lower values are usually more stable.")
    parser.add_argument("--top-p", type=float, default=0.78)
    parser.add_argument("--top-k", type=int, default=35)
    parser.add_argument("--repetition-penalty", type=float, default=7.0)
    parser.add_argument("--length-penalty", type=float, default=1.0)
    parser.add_argument("--speed", type=float, default=0.88, help="XTTS inference speed factor; below 1.0 is slower.")
    parser.add_argument("--pause", type=float, default=0.92, help="Room-tone pause between chunks in seconds.")
    parser.add_argument("--crossfade", type=float, default=0.045, help="Crossfade between chunk/pause boundaries.")
    parser.add_argument("--seed", type=int, default=4242)
    args = parser.parse_args()

    ref = Path(args.reference)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading XTTS v2...")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=True, gpu=not args.cpu)

    rendered = []
    chunk_stats = []
    sr = None
    for idx, chunk_text in enumerate(TEXT_CHUNKS, start=1):
        chunk_path = TMP_DIR / f"sleep_slow_chunk_{idx:02d}.wav"
        text = clean_text(chunk_text)
        print(f"Generating chunk {idx}/{len(TEXT_CHUNKS)} ({len(text)} chars): {text}")
        generate_chunk(tts, text, ref, chunk_path, args)
        y, this_sr = sf.read(chunk_path, dtype="float32", always_2d=False)
        sr = this_sr if sr is None else sr
        if this_sr != sr:
            y = librosa.resample(y.astype(np.float32), orig_sr=this_sr, target_sr=sr)
        y = soften_and_normalize(y, sr)
        sf.write(chunk_path, y, sr, subtype="PCM_16")
        chunk_stats.append({"index": idx, "text_chars": len(text), "stats": wav_stats(chunk_path), "repetition": max_adjacent_repetition(y, sr)})
        append_crossfaded(rendered, y, sr, args.crossfade)
        if idx != len(TEXT_CHUNKS):
            append_crossfaded(rendered, room_tone(sr, args.pause, args.seed + idx), sr, args.crossfade)

    final = np.concatenate(rendered).astype(np.float32)
    final = soften_and_normalize(final, sr, target_peak=0.76)
    sf.write(out, final, sr, subtype="PCM_16")

    stats = {
        "reference": wav_stats(ref),
        "output": wav_stats(out),
        "chunks": chunk_stats,
        "settings": {
            "language": "ru",
            "split_sentences": False,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "top_k": args.top_k,
            "repetition_penalty": args.repetition_penalty,
            "length_penalty": args.length_penalty,
            "speed": args.speed,
            "pause_sec": args.pause,
            "crossfade_sec": args.crossfade,
        },
        "final_repetition_probe": max_adjacent_repetition(final, sr),
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

