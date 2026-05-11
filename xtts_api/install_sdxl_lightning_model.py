#!/usr/bin/env python3
"""Safe SDXL Lightning checkpoint downloader for ComfyUI.

The helper intentionally requires an explicit Y confirmation before creating
the target folder or downloading any model file.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_FILENAME = "sdxl_lightning_4step.safetensors"
PLACEHOLDER_VALUES = {"", "PASTE_HUGGINGFACE_DIRECT_URL_HERE"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely download an SDXL Lightning 4-step checkpoint for ComfyUI."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("SDXL_LIGHTNING_MODEL_URL", ""),
        help=(
            "Direct model URL, preferably the ByteDance/SDXL-Lightning "
            "4-step checkpoint /resolve/main/*.safetensors URL. Can also be "
            "provided through SDXL_LIGHTNING_MODEL_URL. Do not use a LoRA URL."
        ),
    )
    parser.add_argument(
        "--target-dir",
        default=str(
            Path(__file__).resolve().parent
            / ".."
            / "ComfyUI_windows_portable"
            / "ComfyUI"
            / "models"
            / "checkpoints"
        ),
        help="ComfyUI checkpoints folder.",
    )
    parser.add_argument(
        "--filename",
        default=DEFAULT_FILENAME,
        help="Filename to write inside the checkpoints folder.",
    )
    return parser


def format_size(num_bytes: int | None) -> str:
    if not num_bytes or num_bytes < 0:
        return "unknown size"
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{num_bytes} B"


def validate_filename(filename: str) -> str:
    candidate = Path(filename)
    if candidate.name != filename or not filename.strip():
        raise ValueError("Filename must be a plain file name, not a path.")
    if candidate.suffix.lower() != ".safetensors":
        raise ValueError("Checkpoint filename must end with .safetensors.")
    return filename


def make_request(url: str) -> urllib.request.Request:
    headers = {"User-Agent": "XTTS-Studio-SDXL-Lightning-Installer/1.0"}
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def download(url: str, output_path: Path) -> None:
    tmp_path = output_path.with_suffix(output_path.suffix + ".part")
    if tmp_path.exists():
        tmp_path.unlink()

    try:
        with urllib.request.urlopen(make_request(url), timeout=60) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise RuntimeError(f"Unexpected HTTP status: {status}")

            total = response.headers.get("Content-Length")
            total_bytes = int(total) if total and total.isdigit() else None
            print(f"Download started. Size: {format_size(total_bytes)}")

            downloaded = 0
            next_report = 0
            with tmp_path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_report:
                        if total_bytes:
                            pct = downloaded * 100.0 / total_bytes
                            print(
                                f"Downloaded {format_size(downloaded)} / "
                                f"{format_size(total_bytes)} ({pct:.1f}%)"
                            )
                        else:
                            print(f"Downloaded {format_size(downloaded)}")
                        next_report = downloaded + 512 * 1024 * 1024

        tmp_path.replace(output_path)
    except urllib.error.HTTPError as exc:
        details = exc.read(800).decode("utf-8", errors="replace")
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(
            f"HTTP {exc.code} while downloading. Hugging Face may require login, "
            f"license acceptance, or a different direct URL. Details: {details}"
        ) from exc
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def main() -> int:
    args = build_parser().parse_args()
    url = args.url.strip()

    try:
        filename = validate_filename(args.filename.strip())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if url in PLACEHOLDER_VALUES:
        print("ERROR: No SDXL Lightning model URL is configured.", file=sys.stderr)
        print(
            "Set SDXL_LIGHTNING_MODEL_URL to a direct ByteDance/SDXL-Lightning "
            "4-step checkpoint /resolve/main/*.safetensors URL, or edit "
            "MODEL_URL in the .cmd file. Do not use a LoRA URL.",
            file=sys.stderr,
        )
        print("No files were created and nothing was downloaded.", file=sys.stderr)
        return 2

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        print("ERROR: MODEL_URL must be a valid http(s) URL.", file=sys.stderr)
        return 2

    target_dir = Path(args.target_dir).resolve()
    output_path = target_dir / filename

    print("WARNING: SDXL Lightning is a large SDXL checkpoint.")
    print("Use the 4-step checkpoint file from ByteDance/SDXL-Lightning, not a LoRA.")
    print("You need a stable internet connection and enough free disk space.")
    print("Nothing will be downloaded unless you type exactly Y and press Enter.")
    print()
    print(f"URL: {url}")
    print(f"Target folder: {target_dir}")
    print(f"Output file: {output_path}")
    print()

    answer = input("Continue with download? Type Y to continue: ").strip()
    if answer != "Y":
        print("Cancelled. No files were created and nothing was downloaded.")
        return 0

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        download(url, output_path)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("The project was not modified. Any partial .part file was removed.", file=sys.stderr)
        return 1

    print()
    print("Download completed successfully.")
    print(f"Saved checkpoint: {output_path}")
    print(f"In XTTS Studio set image_model_checkpoint={filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
