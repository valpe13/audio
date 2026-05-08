from __future__ import annotations

import argparse
from pathlib import Path

import requests


def main() -> None:
    parser = argparse.ArgumentParser(description="Call the local Fish Speech API wrapper")
    parser.add_argument("--url", default="http://127.0.0.1:7865/v1/tts")
    parser.add_argument("--text", default="Пример локального синтеза речи через Fish Speech API.")
    parser.add_argument("--language", default="ru")
    args = parser.parse_args()

    response = requests.post(
        args.url,
        json={"text": args.text, "language": args.language},
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()
    print(data)

    audio_path = Path(data["audio_path"])
    print(f"Generated audio: {audio_path}")


if __name__ == "__main__":
    main()

