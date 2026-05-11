#!/usr/bin/env python3
"""Safe SD1.5 checkpoint downloader for AnimateDiff workflows in ComfyUI.

The helper installs one missing SD1.5 checkpoint into the local ComfyUI
checkpoints folder. It never deletes or overwrites existing checkpoint files.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_URL = "https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors"
DEFAULT_FILENAME = "DreamShaper_8_pruned.safetensors"
PLACEHOLDER_VALUES = {"", "PASTE_HUGGINGFACE_DIRECT_URL_HERE"}
MIN_CHECKPOINT_BYTES = 1_000_000_000


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely download an SD1.5 checkpoint for ComfyUI AnimateDiff workflows."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("ANIMATEDIFF_SD15_CHECKPOINT_URL", DEFAULT_URL),
        help=(
            "Direct SD1.5 checkpoint URL. Defaults to DreamShaper 8 pruned. "
            "Can also be provided through ANIMATEDIFF_SD15_CHECKPOINT_URL."
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
        default=os.environ.get("ANIMATEDIFF_SD15_CHECKPOINT_FILENAME", DEFAULT_FILENAME),
        help=(
            "Filename to write inside the checkpoints folder. "
            "Can also be provided through ANIMATEDIFF_SD15_CHECKPOINT_FILENAME."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Run without the interactive Y confirmation. Intended for repeatable local installs only.",
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
        raise ValueError("Checkpoint filename must be a plain file name, not a path.")
    if candidate.suffix.lower() not in {".safetensors", ".ckpt"}:
        raise ValueError("Checkpoint filename must end with .safetensors or .ckpt.")
    return filename


def make_request(url: str) -> urllib.request.Request:
    headers = {"User-Agent": "XTTS-Studio-AnimateDiff-SD15-Installer/1.0"}
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

        if tmp_path.stat().st_size < MIN_CHECKPOINT_BYTES:
            size = tmp_path.stat().st_size
            tmp_path.unlink()
            raise RuntimeError(
                f"Downloaded file is unexpectedly small: {format_size(size)}. "
                "The URL may point to an error page instead of a checkpoint."
            )
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


def print_manual_fallback(target_dir: Path, url: str, filename: str) -> None:
    print()
    print("Manual fallback:")
    print("  1. Open the model page in a browser:")
    print("     https://huggingface.co/Lykon/DreamShaper")
    print("  2. Download an SD1.5 checkpoint file, for example:")
    print(f"     {url}")
    print("  3. Save it without overwriting existing files as:")
    print(f"     {target_dir / filename}")
    print("  4. Restart ComfyUI and XTTS Studio before re-running AnimateDiff diagnostics.")
    print()
    print("Alternative SD1.5 checkpoints also work if they are full SD1.5 checkpoints, not SDXL/SVD/LoRA files.")


def main() -> int:
    args = build_parser().parse_args()
    url = args.url.strip()

    try:
        filename = validate_filename(args.filename.strip())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    parsed = urllib.parse.urlparse(url)
    if url in PLACEHOLDER_VALUES or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        print("ERROR: ANIMATEDIFF_SD15_CHECKPOINT_URL must be a valid direct http(s) URL.", file=sys.stderr)
        return 2

    target_dir = Path(args.target_dir).resolve()
    output_path = target_dir / filename

    print("AnimateDiff SD1.5 checkpoint installer for ComfyUI")
    print("--------------------------------------------------")
    print("Default checkpoint: DreamShaper 8 pruned, SD1.5-compatible")
    print(f"URL:           {url}")
    print(f"Target folder: {target_dir}")
    print(f"Output file:   {output_path}")
    print()
    print("Safety:")
    print("  Existing checkpoint files are not overwritten.")
    print("  Partial downloads use .part files and are removed on errors.")
    print("  No image or video generation will be started.")
    print()

    if output_path.exists():
        print(f"Checkpoint already present, leaving it untouched: {output_path}")
        print_manual_fallback(target_dir, url, filename)
        return 0

    if not args.yes:
        answer = input("Continue with download? Type Y to continue: ").strip()
        if answer != "Y":
            print("Cancelled. No files were created and nothing was downloaded.")
            print_manual_fallback(target_dir, url, filename)
            return 0

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        download(url, output_path)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("No existing checkpoint files were deleted or overwritten.", file=sys.stderr)
        print_manual_fallback(target_dir, url, filename)
        return 1

    print()
    print("Download completed successfully.")
    print(f"Saved SD1.5 checkpoint: {output_path}")
    print(f"For AnimateDiff diagnostics, ComfyUI should report this checkpoint as: {filename}")
    print("Restart ComfyUI and XTTS Studio if they were already running.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
