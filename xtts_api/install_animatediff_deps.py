#!/usr/bin/env python3
"""Safe AnimateDiff dependency installer for a local ComfyUI portable setup.

The helper installs only missing custom-node folders and a missing motion module.
It never deletes or overwrites existing user files.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


CUSTOM_NODES = {
    "ComfyUI-AnimateDiff-Evolved": "https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git",
    "ComfyUI-VideoHelperSuite": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git",
}

DEFAULT_MOTION_MODEL_URL = "https://huggingface.co/guoyww/animatediff/resolve/main/mm_sd_v15_v2.ckpt"
DEFAULT_MOTION_MODEL_FILENAME = "mm_sd_v15_v2.ckpt"
PLACEHOLDER_VALUES = {"", "PASTE_HUGGINGFACE_DIRECT_URL_HERE"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install missing AnimateDiff custom nodes and a motion model for ComfyUI."
    )
    parser.add_argument(
        "--comfyui-root",
        default=os.environ.get(
            "COMFYUI_PORTABLE_ROOT",
            str(Path(__file__).resolve().parent / ".." / "ComfyUI_windows_portable"),
        ),
        help=(
            "ComfyUI portable root folder, containing ComfyUI/main.py. "
            "Can also be set with COMFYUI_PORTABLE_ROOT."
        ),
    )
    parser.add_argument(
        "--motion-model-url",
        default=os.environ.get("ANIMATEDIFF_MOTION_MODEL_URL", DEFAULT_MOTION_MODEL_URL),
        help="Direct AnimateDiff motion model URL. Can also be set with ANIMATEDIFF_MOTION_MODEL_URL.",
    )
    parser.add_argument(
        "--motion-model-filename",
        default=os.environ.get("ANIMATEDIFF_MOTION_MODEL_FILENAME", DEFAULT_MOTION_MODEL_FILENAME),
        help="Filename to write under ComfyUI/models/animatediff_models.",
    )
    parser.add_argument(
        "--skip-requirements",
        action="store_true",
        help="Clone nodes and download model, but do not run pip install -r requirements.txt for custom nodes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned actions without creating folders, cloning, downloading, or installing requirements.",
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


def validate_plain_filename(filename: str) -> str:
    candidate = Path(filename)
    if candidate.name != filename or not filename.strip():
        raise ValueError("Motion model filename must be a plain file name, not a path.")
    if candidate.suffix.lower() not in {".ckpt", ".safetensors", ".pt", ".pth"}:
        raise ValueError("Motion model filename should end with .ckpt, .safetensors, .pt, or .pth.")
    return filename


def make_request(url: str) -> urllib.request.Request:
    headers = {"User-Agent": "XTTS-Studio-AnimateDiff-Installer/1.0"}
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
                            print(f"Downloaded {format_size(downloaded)} / {format_size(total_bytes)} ({pct:.1f}%)")
                        else:
                            print(f"Downloaded {format_size(downloaded)}")
                        next_report = downloaded + 256 * 1024 * 1024
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


def ensure_comfyui_root(raw_root: str) -> tuple[Path, Path]:
    root = Path(raw_root).expanduser().resolve()
    comfy_dir = root / "ComfyUI"
    main_py = comfy_dir / "main.py"
    if not main_py.exists():
        raise FileNotFoundError(
            f"ComfyUI portable root was not found or is not valid: {root}\n"
            f"Expected file: {main_py}\n"
            "Set COMFYUI_PORTABLE_ROOT or pass --comfyui-root to the folder that contains ComfyUI\\main.py."
        )
    return root, comfy_dir


def run_command(command: list[str], cwd: Path) -> None:
    printable = " ".join(f'"{part}"' if " " in part else part for part in command)
    print(f"Running: {printable}")
    subprocess.run(command, cwd=str(cwd), check=True)


def git_clone_missing(name: str, repo_url: str, target: Path, dry_run: bool) -> str:
    if target.exists():
        return f"present: {target}"
    if shutil.which("git") is None:
        return (
            f"missing: {target}\n"
            f"  Git was not found. Manual fallback: git clone {repo_url} \"{target}\""
        )
    if dry_run:
        return f"would clone: {repo_url} -> {target}"
    target.parent.mkdir(parents=True, exist_ok=True)
    run_command(["git", "clone", "--depth", "1", repo_url, str(target)], target.parent)
    return f"cloned: {target}"


def install_requirements_for_node(node_dir: Path, python_exe: Path | None, dry_run: bool) -> str:
    requirements = node_dir / "requirements.txt"
    if not node_dir.exists():
        return f"requirements skipped, node folder missing: {node_dir}"
    if not requirements.exists():
        return f"requirements not present: {node_dir.name}"
    if not python_exe or not python_exe.exists():
        return (
            f"requirements not installed for {node_dir.name}: embedded python was not found.\n"
            f"  Manual fallback: <ComfyUI python> -m pip install -r \"{requirements}\""
        )
    if dry_run:
        return f"would install requirements: {python_exe} -m pip install -r {requirements}"
    run_command([str(python_exe), "-m", "pip", "install", "-r", str(requirements)], node_dir)
    return f"requirements installed: {node_dir.name}"


def print_manual_fallback(comfy_dir: Path, model_url: str, model_filename: str) -> None:
    custom_nodes_dir = comfy_dir / "custom_nodes"
    model_dir = comfy_dir / "models" / "animatediff_models"
    print()
    print("Manual fallback commands/locations:")
    print(f"  git clone https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git \"{custom_nodes_dir / 'ComfyUI-AnimateDiff-Evolved'}\"")
    print(f"  git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git \"{custom_nodes_dir / 'ComfyUI-VideoHelperSuite'}\"")
    print(f"  Download motion model URL: {model_url}")
    print(f"  Save as: {model_dir / model_filename}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        portable_root, comfy_dir = ensure_comfyui_root(args.comfyui_root)
        motion_filename = validate_plain_filename(args.motion_model_filename.strip())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    model_url = args.motion_model_url.strip()
    parsed = urllib.parse.urlparse(model_url)
    if model_url in PLACEHOLDER_VALUES or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        print("ERROR: ANIMATEDIFF_MOTION_MODEL_URL must be a valid direct http(s) URL.", file=sys.stderr)
        print_manual_fallback(comfy_dir, DEFAULT_MOTION_MODEL_URL, motion_filename)
        return 2

    custom_nodes_dir = comfy_dir / "custom_nodes"
    motion_model_dir = comfy_dir / "models" / "animatediff_models"
    motion_model_path = motion_model_dir / motion_filename
    embedded_python = portable_root / "python_embeded" / "python.exe"

    print("AnimateDiff dependency installer for ComfyUI")
    print("------------------------------------------")
    print(f"ComfyUI portable root: {portable_root}")
    print(f"ComfyUI folder:        {comfy_dir}")
    print(f"Custom nodes folder:  {custom_nodes_dir}")
    print(f"Motion model folder:  {motion_model_dir}")
    print(f"Motion model file:    {motion_model_path}")
    print(f"Motion model URL:     {model_url}")
    print(f"Embedded Python:      {embedded_python if embedded_python.exists() else 'not found'}")
    print()
    print("Safety:")
    print("  Existing custom-node folders are left untouched.")
    print("  Existing motion model files are not overwritten.")
    print("  No generation will be started.")

    if not args.yes and not args.dry_run:
        answer = input("Continue with install/download? Type Y to continue: ").strip()
        if answer != "Y":
            print("Cancelled. No files were created, cloned, or downloaded.")
            print_manual_fallback(comfy_dir, model_url, motion_filename)
            return 0

    results: list[str] = []
    try:
        if not args.dry_run:
            custom_nodes_dir.mkdir(parents=True, exist_ok=True)
        for name, repo_url in CUSTOM_NODES.items():
            results.append(git_clone_missing(name, repo_url, custom_nodes_dir / name, args.dry_run))

        if motion_model_path.exists():
            results.append(f"motion model present: {motion_model_path}")
        elif args.dry_run:
            results.append(f"would download motion model: {model_url} -> {motion_model_path}")
        else:
            motion_model_dir.mkdir(parents=True, exist_ok=True)
            download(model_url, motion_model_path)
            results.append(f"motion model downloaded: {motion_model_path}")

        if args.skip_requirements:
            results.append("requirements skipped by --skip-requirements")
        else:
            python_exe = embedded_python if embedded_python.exists() else None
            for name in CUSTOM_NODES:
                results.append(install_requirements_for_node(custom_nodes_dir / name, python_exe, args.dry_run))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Partial downloads use .part files and are removed on download errors; existing user files were not overwritten.", file=sys.stderr)
        print_manual_fallback(comfy_dir, model_url, motion_filename)
        return 1

    print()
    print("Result:")
    for result in results:
        print(f"  - {result}")
    print_manual_fallback(comfy_dir, model_url, motion_filename)
    print()
    print("Next steps:")
    print("  1. Restart ComfyUI so the new custom nodes are loaded.")
    print("  2. In XTTS Studio, choose video_i2v_workflow_mode=generated_animatediff only for testing.")
    print("  3. Use object-locked prompts: locked camera, static camera, no camera movement, objects move naturally inside the frame.")
    print("  4. First validate a small AnimateDiff workflow directly in ComfyUI before wiring a real graph into XTTS Studio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
