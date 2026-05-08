import argparse
import contextlib
import inspect
import json
import os
import wave
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

os.environ.setdefault("COQUI_TOS_AGREED", "1")

from TTS.api import TTS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REF = ROOT / "xtts_api" / "reference_audio" / "girl_voice_messages_merged.wav"
DEFAULT_OUT = ROOT / "xtts_api" / "outputs" / "xtts_v2_ru_merged_ref_smooth_test.wav"
TEXT = (
    "Привет. Это спокойная проверка XTTS версии два на русском языке с новым объединённым референсом. "
    "Сейчас мы генерируем один цельный фрагмент, без отдельной нарезки по коротким фразам, чтобы между предложениями не появлялись резкие провалы. "
    "Голос должен звучать мягко и естественно, с небольшими живыми паузами, но без длинной тишины и щелчков на стыках. "
    "Если результат нужен для публикации, обязательно используйте только те референсы, на которые есть разрешение."
)


def wav_stats(path: Path) -> dict:
    with contextlib.closing(wave.open(str(path), "rb")) as wav_file:
        frames = wav_file.getnframes()
        sr = wav_file.getframerate()
        return {
            "path": str(path.relative_to(ROOT)),
            "channels": wav_file.getnchannels(),
            "sample_rate": sr,
            "frames": frames,
            "duration_sec": round(frames / float(sr), 3),
        }


def trim_outer_silence(y: np.ndarray, sr: int) -> np.ndarray:
    intervals = librosa.effects.split(y, top_db=42, frame_length=2048, hop_length=512)
    if len(intervals) == 0:
        return y
    pad = int(0.08 * sr)
    start = max(0, int(intervals[0][0]) - pad)
    end = min(len(y), int(intervals[-1][1]) + pad)
    return y[start:end]


def compress_long_silences(y: np.ndarray, sr: int, max_silence_sec: float = 0.45) -> np.ndarray:
    """Keep natural internal pauses, but shorten only excessive silent gaps."""
    if y.size == 0:
        return y
    intervals = librosa.effects.split(y, top_db=42, frame_length=2048, hop_length=512)
    if len(intervals) <= 1:
        return y
    max_gap = int(max_silence_sec * sr)
    chunks = []
    cursor = 0
    for start, end in intervals:
        start = int(start)
        end = int(end)
        gap = y[cursor:start]
        if len(gap) > max_gap:
            keep = gap[: max_gap // 2]
            tail = gap[-(max_gap - len(keep)) :]
            gap = np.concatenate([keep, tail]) if len(tail) else keep
        chunks.append(gap)
        chunks.append(y[start:end])
        cursor = end
    chunks.append(y[cursor:])
    return np.concatenate(chunks).astype(np.float32)


def de_click_and_normalize(path: Path) -> None:
    y, sr = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = trim_outer_silence(y, sr)
    y = compress_long_silences(y, sr)
    fade_len = min(len(y) // 4, int(0.025 * sr))
    if fade_len > 1:
        y[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        y[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 1e-6:
        y = y * (0.90 / peak)
    sf.write(path, np.clip(y, -0.98, 0.98), sr, subtype="PCM_16")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate smoother Russian XTTS v2 sample with merged reference.")
    parser.add_argument("--text", default=TEXT, help="Text to synthesize as one continuous block.")
    parser.add_argument("--reference", default=str(DEFAULT_REF), help="Speaker reference WAV.")
    parser.add_argument("--output", default=str(DEFAULT_OUT), help="Output WAV path.")
    parser.add_argument("--cpu", action="store_true", help="Force CPU instead of CUDA.")
    parser.add_argument("--split-sentences", action="store_true", help="Allow Coqui sentence splitting; disabled by default for smoother joins.")
    args = parser.parse_args()

    ref = Path(args.reference)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    print("Loading XTTS v2...")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=True, gpu=not args.cpu)

    kwargs = {
        "text": " ".join(args.text.split()),
        "speaker_wav": str(ref),
        "language": "ru",
        "file_path": str(out),
    }
    if "split_sentences" in inspect.signature(tts.tts_to_file).parameters:
        kwargs["split_sentences"] = bool(args.split_sentences)

    print(f"Generating one continuous XTTS block: {out}")
    tts.tts_to_file(**kwargs)
    de_click_and_normalize(out)
    stats = {"reference": wav_stats(ref), "output": wav_stats(out), "split_sentences": bool(args.split_sentences)}
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
