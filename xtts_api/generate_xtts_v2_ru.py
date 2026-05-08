import contextlib
import json
import os
import wave
from pathlib import Path

os.environ.setdefault("COQUI_TOS_AGREED", "1")

from TTS.api import TTS


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "xtts_api" / "outputs" / "xtts_v2_ru_30s_test.wav"
REF = ROOT / "fish_speech_api" / "reference_audio" / "female_ja_pozzhe_napishu.wav"
TEXT = (
    "Спокойный короткий тест XTTS версии два на русском языке. "
    "Проверяем клонирование женского референсного голоса, мягкую интонацию "
    "и разборчивость речи. Это отдельная проверка, не связанная с сервером Silero."
)


def main() -> None:
    print("Loading XTTS v2...")
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=True, gpu=True)
    print(f"Generating: {OUT}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tts.tts_to_file(text=TEXT, speaker_wav=str(REF), language="ru", file_path=str(OUT))
    with contextlib.closing(wave.open(str(OUT), "rb")) as wav_file:
        stats = {
            "path": str(OUT),
            "channels": wav_file.getnchannels(),
            "sample_rate": wav_file.getframerate(),
            "frames": wav_file.getnframes(),
            "duration_sec": round(wav_file.getnframes() / float(wav_file.getframerate()), 3),
        }
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
