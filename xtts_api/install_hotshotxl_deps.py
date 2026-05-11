#!/usr/bin/env python3
"""Safe SDXL/HotshotXL motion-model installer for a local ComfyUI portable setup.

The helper validates an existing ComfyUI portable install, verifies the custom
nodes used by XTTS Studio's `generated_hotshotxl` backend, and downloads one
SDXL-compatible AnimateDiff/HotshotXL motion module without overwriting files.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_HOTSHOTXL_URL = "https://huggingface.co/hotshotco/Hotshot-XL/resolve/main/hsxl_temporal_layers.safetensors"
DEFAULT_HOTSHOTXL_FILENAME = "hsxl_temporal_layers.safetensors"
FALLBACK_URLS = [
    DEFAULT_HOTSHOTXL_URL,
    "https://huggingface.co/hotshotco/Hotshot-XL/tree/main",
    "https://huggingface.co/guoyww/animatediff/tree/main",
]
PLACEHOLDER_VALUES = {"", "PASTE_HUGGINGFACE_DIRECT_URL_HERE"}
REQUIRED_CUSTOM_NODE_NAMES = {
    "animatediff": {"comfyui-animatediff-evolved"},
    "videohelpersuite": {"comfyui-videohelpersuite", "comfyui-videohelpersuite-main", "comfyui-videohelper-suite"},
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install a HotshotXL / SDXL AnimateDiff motion model for ComfyUI.")
    parser.add_argument(
        "--comfyui-root",
        default=os.environ.get("COMFYUI_PORTABLE_ROOT", str(Path(__file__).resolve().parent / ".." / "ComfyUI_windows_portable")),
        help="ComfyUI portable root folder containing ComfyUI/main.py. Can also be set with COMFYUI_PORTABLE_ROOT.",
    )
    parser.add_argument(
        "--motion-model-url",
        default=os.environ.get("HOTSHOTXL_MOTION_MODEL_URL", DEFAULT_HOTSHOTXL_URL),
        help="Direct SDXL/HotshotXL motion model URL. Can also be set with HOTSHOTXL_MOTION_MODEL_URL.",
    )
    parser.add_argument(
        "--motion-model-filename",
        default=os.environ.get("HOTSHOTXL_MOTION_MODEL_FILENAME", DEFAULT_HOTSHOTXL_FILENAME),
        help="Filename to write under ComfyUI/models/animatediff_models.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without downloading.")
    parser.add_argument("--yes", action="store_true", help="Run without interactive Y confirmation.")
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


def validate_plain_filename(filename: str) -> str:
    candidate = Path(filename)
    if candidate.name != filename or not filename.strip():
        raise ValueError("Motion model filename must be a plain file name, not a path.")
    if candidate.suffix.lower() not in {".safetensors", ".ckpt", ".pt", ".pth"}:
        raise ValueError("Motion model filename should end with .safetensors, .ckpt, .pt, or .pth.")
    return filename


def make_request(url: str) -> urllib.request.Request:
    headers = {"User-Agent": "XTTS-Studio-HotshotXL-Installer/1.0"}
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def ensure_comfyui_root(raw_root: str) -> tuple[Path, Path]:
    root = Path(raw_root).resolve()
    comfy_dir = root / "ComfyUI"
    main_py = comfy_dir / "main.py"
    if not main_py.exists():
        raise FileNotFoundError(
            f"ComfyUI portable root was not found or is not valid: {root}\n"
            f"Expected file: {main_py}\n"
            "Set COMFYUI_PORTABLE_ROOT or pass --comfyui-root to the folder that contains ComfyUI\\main.py."
        )
    return root, comfy_dir


def custom_node_status(comfy_dir: Path) -> dict[str, str]:
    custom_nodes_dir = comfy_dir / "custom_nodes"
    existing = {path.name.lower(): path for path in custom_nodes_dir.iterdir() if path.is_dir()} if custom_nodes_dir.exists() else {}
    status: dict[str, str] = {}
    for key, accepted_names in REQUIRED_CUSTOM_NODE_NAMES.items():
        match = next((existing[name] for name in accepted_names if name in existing), None)
        status[key] = str(match) if match else ""
    return status


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
                            print(f"Downloaded {format_size(downloaded)} / {format_size(total_bytes)} ({pct:.1f}%)")
                        else:
                            print(f"Downloaded {format_size(downloaded)}")
                        next_report = downloaded + 256 * 1024 * 1024
        tmp_path.replace(output_path)
    except urllib.error.HTTPError as exc:
        details = exc.read(800).decode("utf-8", errors="replace")
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"HTTP {exc.code} while downloading. Details: {details}") from exc
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def print_manual_fallback(comfy_dir: Path, model_url: str, model_filename: str) -> None:
    custom_nodes_dir = comfy_dir / "custom_nodes"
    model_dir = comfy_dir / "models" / "animatediff_models"
    print()
    print("Manual fallback instructions:")
    print(f"  1. Verify AnimateDiff-Evolved exists at: {custom_nodes_dir / 'ComfyUI-AnimateDiff-Evolved'}")
    print(f"  2. Verify VideoHelperSuite exists at: {custom_nodes_dir / 'ComfyUI-VideoHelperSuite'}")
    print(f"  3. Download SDXL/HotshotXL motion model URL: {model_url}")
    print(f"  4. Save it as: {model_dir / model_filename}")
    print("  5. Restart ComfyUI, then open XTTS Studio diagnostics:")
    print("     http://127.0.0.1:7870/api/comfyui/animatediff-sdxl/diagnostics")
    print("  Fallback model pages:")
    for url in FALLBACK_URLS:
        print(f"     {url}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        _portable_root, comfy_dir = ensure_comfyui_root(args.comfyui_root)
        motion_filename = validate_plain_filename(args.motion_model_filename.strip())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    model_url = args.motion_model_url.strip()
    parsed = urllib.parse.urlparse(model_url)
    if model_url in PLACEHOLDER_VALUES or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        print("ERROR: HOTSHOTXL_MOTION_MODEL_URL must be a valid direct http(s) URL.", file=sys.stderr)
        print_manual_fallback(comfy_dir, DEFAULT_HOTSHOTXL_URL, motion_filename)
        return 2

    node_status = custom_node_status(comfy_dir)
    motion_model_dir = comfy_dir / "models" / "animatediff_models"
    motion_model_path = motion_model_dir / motion_filename

    print("HotshotXL / SDXL AnimateDiff installer for ComfyUI")
    print("----------------------------------------------------")
    print(f"ComfyUI folder:       {comfy_dir}")
    print(f"AnimateDiff-Evolved:  {node_status.get('animatediff') or 'missing'}")
    print(f"VideoHelperSuite:     {node_status.get('videohelpersuite') or 'missing'}")
    print(f"Motion model folder:  {motion_model_dir}")
    print(f"Motion model file:    {motion_model_path}")
    print(f"Motion model URL:     {model_url}")
    print()
    print("Safety:")
    print("  Existing custom nodes are only checked, not modified.")
    print("  Existing motion model files are not overwritten.")
    print("  No image or video generation will be started.")

    missing_nodes = [name for name, path in node_status.items() if not path]
    if missing_nodes:
        print(f"ERROR: required custom node folder(s) missing: {', '.join(missing_nodes)}", file=sys.stderr)
        print_manual_fallback(comfy_dir, model_url, motion_filename)
        return 2

    if not args.yes and not args.dry_run:
        answer = input("Continue with HotshotXL motion-model download? Type Y to continue: ").strip()
        if answer != "Y":
            print("Cancelled. No files were created or downloaded.")
            print_manual_fallback(comfy_dir, model_url, motion_filename)
            return 0

    try:
        if motion_model_path.exists():
            print(f"Result: motion model already present, not overwritten: {motion_model_path}")
        elif args.dry_run:
            print(f"Result: would download motion model: {model_url} -> {motion_model_path}")
        else:
            motion_model_dir.mkdir(parents=True, exist_ok=True)
            download(model_url, motion_model_path)
            print(f"Result: motion model downloaded: {motion_model_path}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Partial .part downloads are removed on errors; existing user files were not overwritten.", file=sys.stderr)
        print_manual_fallback(comfy_dir, model_url, motion_filename)
        return 1

    print_manual_fallback(comfy_dir, model_url, motion_filename)
    print()
    print("Next steps:")
    print("  1. Restart ComfyUI so AnimateDiff-Evolved reloads model names.")
    print("  2. Restart XTTS Studio if it was already running.")
    print("  3. Open http://127.0.0.1:7870/api/comfyui/animatediff-sdxl/diagnostics")
    print("  4. Use generated_hotshotxl only if diagnostics ready=true; start with Fast quality and short clips.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
