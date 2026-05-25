#!/usr/bin/env python3
"""Install project-specific ComfyUI custom nodes for the audio workspace.

This helper intentionally does not scan or depend on the ignored local
ComfyUI_windows_portable tree contents beyond targeted existence checks and
copy/clone destinations. Existing third-party custom-node folders are left
untouched; local bridge node files are refreshed from this repository so a clean
deployment matches the current project state.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_COMFYUI_ROOT = PROJECT_ROOT / "ComfyUI_windows_portable"

LOCAL_BRIDGE_NODES = [
    {
        "name": "comfyui-silero-tts-api",
        "source": PROJECT_ROOT / "comfyui_silero_tts_bridge" / "silero_tts_api_node.py",
        "target_file": "__init__.py",
        "requires_requests": True,
    },
    {
        "name": "comfyui-fish-speech-api",
        "source": PROJECT_ROOT / "comfyui_fish_speech_bridge" / "fish_speech_api_node.py",
        "target_file": "__init__.py",
        "requires_requests": True,
    },
]

EXTERNAL_CUSTOM_NODES = [
    {
        "name": "ComfyUI-Manager",
        "repo": "https://github.com/ltdrdata/ComfyUI-Manager.git",
        "zip_url": "https://github.com/ltdrdata/ComfyUI-Manager/archive/refs/heads/main.zip",
        "install_requirements": False,
    },
    {
        "name": "ComfyUI-XTTS",
        "repo": "https://github.com/AIFSH/ComfyUI-XTTS.git",
        "zip_url": "https://github.com/AIFSH/ComfyUI-XTTS/archive/refs/heads/main.zip",
        # Do not install requirements automatically. The current portable uses
        # Python 3.13, while Coqui TTS pins are Python 3.10-era packages.
        "install_requirements": False,
    },
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install Audio project ComfyUI custom nodes.")
    parser.add_argument(
        "--comfyui-root",
        default=os.environ.get("COMFYUI_PORTABLE_ROOT", str(DEFAULT_COMFYUI_ROOT)),
        help="ComfyUI portable root folder containing ComfyUI/main.py. Can also be set with COMFYUI_PORTABLE_ROOT.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without copying, cloning, or installing packages.")
    parser.add_argument("--skip-external", action="store_true", help="Only copy repository bridge nodes; do not clone external custom nodes.")
    parser.add_argument("--skip-pip", action="store_true", help="Do not verify/install tiny Python dependencies such as requests.")
    parser.add_argument("--yes", action="store_true", help="Accepted for noninteractive installer compatibility; no prompt is used.")
    return parser


def ensure_comfyui_root(raw_root: str) -> tuple[Path, Path, Path, Path | None]:
    root = Path(raw_root).resolve()
    comfy_dir = root / "ComfyUI"
    main_py = comfy_dir / "main.py"
    if not main_py.exists():
        raise FileNotFoundError(
            f"ComfyUI portable root was not found or is not valid: {root}\n"
            f"Expected file: {main_py}\n"
            "Run xtts_api\\install_comfyui_portable.cmd first, set COMFYUI_PORTABLE_ROOT, "
            "or pass --comfyui-root."
        )
    custom_nodes_dir = comfy_dir / "custom_nodes"
    embedded_python = root / "python_embeded" / "python.exe"
    return root, comfy_dir, custom_nodes_dir, embedded_python if embedded_python.exists() else None


def run_command(command: list[str], cwd: Path, dry_run: bool) -> None:
    printable = " ".join(f'"{part}"' if " " in part else part for part in command)
    print(f"Running: {printable}")
    if dry_run:
        return
    subprocess.run(command, cwd=str(cwd), check=True)


def download_zip_node(zip_url: str, target: Path, dry_run: bool) -> str:
    if dry_run:
        return f"would download ZIP fallback: {zip_url} -> {target}"
    with tempfile.TemporaryDirectory(prefix="comfyui-node-zip-") as temp_name:
        temp_dir = Path(temp_name)
        zip_path = temp_dir / "node.zip"
        request = urllib.request.Request(zip_url, headers={"User-Agent": "Audio-ComfyUI-Node-Installer/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise RuntimeError(f"Unexpected HTTP status while downloading {zip_url}: {status}")
            with zip_path.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
        extract_dir = temp_dir / "extract"
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(extract_dir)
        candidates = [path for path in extract_dir.iterdir() if path.is_dir()]
        if not candidates:
            raise RuntimeError(f"Downloaded ZIP did not contain a folder: {zip_url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(candidates[0]), str(target))
    return f"downloaded ZIP fallback external node: {target}"


def copy_local_bridge_nodes(custom_nodes_dir: Path, dry_run: bool) -> list[str]:
    results: list[str] = []
    for node in LOCAL_BRIDGE_NODES:
        source = Path(node["source"])
        target_dir = custom_nodes_dir / str(node["name"])
        target_file = target_dir / str(node["target_file"])
        if not source.is_file():
            raise FileNotFoundError(f"Local bridge source file is missing: {source}")
        if dry_run:
            results.append(f"would copy local bridge: {source} -> {target_file}")
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_file)
        results.append(f"copied local bridge: {target_file}")
    return results


def clone_external_nodes(custom_nodes_dir: Path, dry_run: bool) -> list[str]:
    results: list[str] = []
    git_available = shutil.which("git") is not None
    for node in EXTERNAL_CUSTOM_NODES:
        name = str(node["name"])
        target = custom_nodes_dir / name
        if target.exists():
            results.append(f"present external node, left untouched: {target}")
            continue
        if dry_run and git_available:
            results.append(f"would clone external node: {node['repo']} -> {target}")
            continue
        if git_available:
            target.parent.mkdir(parents=True, exist_ok=True)
            run_command(["git", "clone", "--depth", "1", str(node["repo"]), str(target)], target.parent, dry_run=False)
            results.append(f"cloned external node: {target}")
        else:
            zip_url = str(node.get("zip_url") or "")
            if not zip_url:
                results.append(f"Git unavailable and no ZIP fallback configured for: {name}")
                continue
            results.append(download_zip_node(zip_url, target, dry_run))
    return results


def ensure_requests(python_exe: Path | None, dry_run: bool, skip_pip: bool) -> str:
    if skip_pip:
        return "requests check/install skipped by --skip-pip"
    if not python_exe:
        return "requests not checked: embedded ComfyUI python was not found"
    check = [str(python_exe), "-c", "import requests"]
    if dry_run:
        return f"would check/install requests with: {python_exe}"
    if subprocess.run(check, cwd=str(PROJECT_ROOT)).returncode == 0:
        return "requests already importable in embedded ComfyUI python"
    run_command([str(python_exe), "-m", "pip", "install", "requests>=2.32.0"], PROJECT_ROOT, dry_run=False)
    return "installed requests into embedded ComfyUI python"


def main() -> int:
    args = build_parser().parse_args()
    try:
        root, comfy_dir, custom_nodes_dir, embedded_python = ensure_comfyui_root(args.comfyui_root)
        print("Audio project ComfyUI custom-node installer")
        print("===========================================")
        print(f"ComfyUI portable root: {root}")
        print(f"ComfyUI folder:        {comfy_dir}")
        print(f"Custom nodes folder:  {custom_nodes_dir}")
        print(f"Embedded Python:      {embedded_python if embedded_python else 'not found'}")
        print(f"Mode:                 {'dry-run' if args.dry_run else 'install'}")
        print()
        print("Safety:")
        print("  Local bridge nodes are refreshed from this repository.")
        print("  Existing external custom-node folders are left untouched.")
        print("  ComfyUI-XTTS requirements are not installed automatically to avoid Python-version conflicts.")
        print()

        if not args.dry_run:
            custom_nodes_dir.mkdir(parents=True, exist_ok=True)

        results = []
        results.extend(copy_local_bridge_nodes(custom_nodes_dir, args.dry_run))
        if args.skip_external:
            results.append("external custom-node clone skipped by --skip-external")
        else:
            results.extend(clone_external_nodes(custom_nodes_dir, args.dry_run))
        results.append(ensure_requests(embedded_python, args.dry_run, args.skip_pip))

        print("Result:")
        for result in results:
            print(f"  - {result}")
        print()
        print("Restart ComfyUI after installing or refreshing custom nodes.")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Command failed with exit code {exc.returncode}: {exc.cmd}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

