from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from silero_backend import DEFAULT_OUTPUT_DIR, DEFAULT_SAMPLE_RATE, DEFAULT_SPEAKER, REALISM_PRESETS, SileroTTSBackend, load_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Russian speech with Silero TTS through torch.hub.")
    parser.add_argument("--text", default=None)
    parser.add_argument("--text-file", default=str(Path(__file__).resolve().parent / "sample_ru_soft_female_30s.txt"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR / "silero_ru_30s_soft_female_test.wav"))
    parser.add_argument("--speaker", default=DEFAULT_SPEAKER)
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--model-id", default="v4_ru")
    parser.add_argument("--realism-enabled", action="store_true")
    parser.add_argument("--preset", default="sleep_safe", choices=list(REALISM_PRESETS.keys()))
    parser.add_argument("--pause-scale", type=float, default=None)
    parser.add_argument("--breath-amount", type=float, default=None)
    parser.add_argument("--room-tone", choices=["on", "off"], default=None)
    parser.add_argument("--loudness-variation", type=float, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--speed", type=float, default=None)
    parser.add_argument("--soften", choices=["on", "off"], default=None)
    parser.add_argument("--target-peak", type=float, default=None)
    parser.add_argument("--tone-softening", type=float, default=None)
    parser.add_argument("--sleep-softness", type=float, default=None)
    parser.add_argument("--list-speakers", action="store_true")
    args = parser.parse_args()

    backend = SileroTTSBackend(model_id=args.model_id, language="ru", device=args.device)
    if args.list_speakers:
        print(json.dumps({"speakers": backend.speakers}, ensure_ascii=False, indent=2))
        return 0

    result = backend.synthesize(
        text=load_text(args.text, args.text_file),
        output_path=args.output,
        speaker=args.speaker,
        sample_rate=args.sample_rate,
        realism_enabled=args.realism_enabled,
        preset=args.preset,
        pause_scale=args.pause_scale,
        breath_amount=args.breath_amount,
        room_tone=None if args.room_tone is None else args.room_tone == "on",
        loudness_variation=args.loudness_variation,
        seed=args.seed,
        speed=args.speed,
        soften=None if args.soften is None else args.soften == "on",
        target_peak=args.target_peak,
        tone_softening=args.tone_softening,
        sleep_softness=args.sleep_softness,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

