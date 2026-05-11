#!/usr/bin/env python3
"""Create a sanitized local ComfyUI portable release archive.

The script never uploads release assets. It builds a zip under an ignored local
folder, splits it into GitHub-friendly part files, computes checksums/sizes, and
prints the manual gh commands to run only after approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_SOURCE = PROJECT_ROOT / "ComfyUI_windows_portable"
DEFAULT_MANIFEST = SCRIPT_DIR / "comfyui_portable_manifest.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "release_assets" / "comfyui-portable-v1"
DEFAULT_PART_SIZE = 1800 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


DEFAULT_EXCLUDE_PATTERNS = [
    "ComfyUI/models/**",
    "ComfyUI/output/**",
    "ComfyUI/input/**",
    "ComfyUI/temp/**",
    "ComfyUI/user/**",
    "ComfyUI/custom_nodes/**/.git/**",
    "ComfyUI/custom_nodes/**/__pycache__/**",
    "ComfyUI/custom_nodes/**/*.pyc",
    "ComfyUI/**/__pycache__/**",
    "ComfyUI/**/*.pyc",
    "ComfyUI/**/*.log",
    "ComfyUI/**/*.tmp",
    "ComfyUI/**/*.temp",
    "python_embeded/Lib/site-packages/torch_extensions/**",
    "python_embeded/Lib/site-packages/**/__pycache__/**",
    "python_embeded/**/*.pyc",
    ".cache/**",
    "cache/**",
    "hf_cache/**",
    "huggingface/**",
    "torch_cache/**",
    "*.mp4",
    "*.mov",
    "*.avi",
    "*.mkv",
    "*.webm",
    "*.wav",
    "*.mp3",
    "*.flac",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.webp",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Package sanitized ComfyUI portable runtime into split release assets.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Local ComfyUI_windows_portable source folder.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Manifest to read/update into generated copy.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Ignored local output folder for zip/parts.")
    parser.add_argument("--part-size-mib", type=int, default=1800, help="Maximum split part size in MiB.")
    parser.add_argument("--write-manifest", action="store_true", help="Write generated manifest copy next to the archive parts.")
    parser.add_argument("--force", action="store_true", help="Replace existing generated zip/part files in output-dir.")
    return parser


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def format_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{num_bytes} B"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE * 8), b""):
            digest.update(chunk)
    return digest.hexdigest()


def posix_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def matches_pattern(rel: str, pattern: str) -> bool:
    rel_path = PurePosixPath(rel)
    if rel_path.match(pattern):
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return rel == prefix or rel.startswith(prefix + "/")
    return False


def should_exclude(rel: str, patterns: list[str]) -> bool:
    rel_lower = rel.lower()
    normalized = [pattern.replace("\\", "/") for pattern in patterns]
    for pattern in normalized:
        if matches_pattern(rel, pattern):
            return True
        if matches_pattern(rel_lower, pattern.lower()):
            return True
    parts = rel_lower.split("/")
    if "__pycache__" in parts or ".git" in parts:
        return True
    if any(part in {"models", "output", "input", "temp", "cache", ".cache", "hf_cache", "torch_cache", "huggingface"} for part in parts):
        return True
    if rel_lower.endswith((".pyc", ".pyo", ".log", ".tmp", ".temp")):
        return True
    if rel_lower.endswith((".safetensors", ".ckpt", ".pth", ".pt", ".onnx", ".bin", ".gguf")):
        return True
    if rel_lower.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm", ".wav", ".mp3", ".flac", ".png", ".jpg", ".jpeg", ".webp")):
        return True
    return False


def iter_included_files(source: Path, patterns: list[str]) -> tuple[list[Path], list[str]]:
    included: list[Path] = []
    excluded: list[str] = []
    for root, dirnames, filenames in os.walk(source):
        root_path = Path(root)
        kept_dirs = []
        for dirname in dirnames:
            rel = posix_rel(root_path / dirname, source)
            if should_exclude(rel, patterns):
                excluded.append(rel + "/")
            else:
                kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in filenames:
            path = root_path / filename
            rel = posix_rel(path, source)
            if should_exclude(rel, patterns):
                excluded.append(rel)
            else:
                included.append(path)
    return included, excluded


def validate_required(source: Path, manifest: dict[str, Any]) -> None:
    missing = []
    for item in manifest.get("required_files", []):
        rel = Path(*PurePosixPath(str(item).replace("\\", "/")).parts)
        if not (source / rel).is_file():
            missing.append(str(item))
    if missing:
        raise RuntimeError("Source is missing required files: " + ", ".join(missing))


def create_zip(source: Path, archive_path: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for index, path in enumerate(files, start=1):
            rel = posix_rel(path, source)
            archive.write(path, rel)
            if index % 500 == 0:
                print(f"Archived {index}/{len(files)} files...")


def split_file(path: Path, part_size: int) -> list[Path]:
    parts: list[Path] = []
    if path.stat().st_size <= part_size:
        part = path.with_name(path.name + ".part01")
        shutil.copyfile(path, part)
        parts.append(part)
        return parts
    with path.open("rb") as handle:
        index = 1
        while True:
            chunk = handle.read(part_size)
            if not chunk:
                break
            part = path.with_name(f"{path.name}.part{index:02d}")
            with part.open("wb") as output:
                output.write(chunk)
            parts.append(part)
            index += 1
    return parts


def update_manifest(manifest: dict[str, Any], archive_path: Path, parts: list[Path]) -> dict[str, Any]:
    repo = str(manifest.get("repo") or "valpe13/audio")
    tag = str(manifest.get("release_tag") or "comfyui-portable-v1")
    generated = dict(manifest)
    generated["archive_base_name"] = archive_path.name
    generated["sha256"] = sha256_file(archive_path)
    generated["size_bytes"] = archive_path.stat().st_size
    generated["redistribution_status"] = manifest.get("redistribution_status", "pending_review")
    generated["parts"] = []
    for part in parts:
        generated["parts"].append(
            {
                "name": part.name,
                "url": f"https://github.com/{repo}/releases/download/{tag}/{part.name}",
                "size_bytes": part.stat().st_size,
                "sha256": sha256_file(part),
            }
        )
    return generated


def main() -> int:
    args = build_parser().parse_args()
    source = Path(args.source).resolve()
    manifest_path = Path(args.manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    part_size = args.part_size_mib * 1024 * 1024
    manifest = load_manifest(manifest_path)
    archive_name = str(manifest.get("archive_base_name") or "comfyui_windows_portable_v1.zip")
    archive_path = output_dir / archive_name

    if not source.is_dir():
        raise SystemExit(f"ERROR: Source folder does not exist: {source}")
    validate_required(source, manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_existing = list(output_dir.glob(archive_name + "*"))
    if generated_existing and not args.force:
        raise SystemExit(f"ERROR: Output files already exist in {output_dir}; use --force to replace them.")
    for path in generated_existing:
        if path.is_file():
            path.unlink()

    patterns = list(manifest.get("exclusions") or DEFAULT_EXCLUDE_PATTERNS)
    files, excluded = iter_included_files(source, patterns)
    print(f"Source:       {source}")
    print(f"Output:       {output_dir}")
    print(f"Included:     {len(files)} file(s)")
    print(f"Excluded:     {len(excluded)} path(s)")
    print(f"Part size:    {args.part_size_mib} MiB")
    print("Creating sanitized archive...")
    create_zip(source, archive_path, files)
    archive_sha = sha256_file(archive_path)
    print(f"Archive:      {archive_path}")
    print(f"Archive size: {format_size(archive_path.stat().st_size)}")
    print(f"Archive SHA:  {archive_sha}")
    print("Splitting archive...")
    parts = split_file(archive_path, part_size)
    generated = update_manifest(manifest, archive_path, parts)
    for part in parts:
        print(f"Part:         {part.name}  {format_size(part.stat().st_size)}  {sha256_file(part)}")

    print()
    print("Generated manifest snippet:")
    print(json.dumps({"sha256": generated["sha256"], "size_bytes": generated["size_bytes"], "parts": generated["parts"]}, indent=2))
    if args.write_manifest:
        generated_path = output_dir / "comfyui_portable_manifest.generated.json"
        generated_path.write_text(json.dumps(generated, indent=2) + "\n", encoding="utf-8")
        print(f"Generated manifest copy written: {generated_path}")

    repo = generated.get("repo", "valpe13/audio")
    tag = generated.get("release_tag", "comfyui-portable-v1")
    asset_list = " ".join(str(part) for part in parts)
    print()
    print("Manual release commands (do not run until redistribution/upload approval):")
    print(f"gh release create {tag} --repo {repo} --title \"ComfyUI portable runtime v1\" --notes \"Sanitized ComfyUI portable runtime; excludes models, user data, outputs, caches, and generated media.\"")
    print(f"gh release upload {tag} {asset_list} --repo {repo}")
    print()
    print("No upload was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
