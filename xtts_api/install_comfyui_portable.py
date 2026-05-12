#!/usr/bin/env python3
"""Install the optional ComfyUI Windows portable runtime from release assets.

This installer is intentionally conservative: an existing valid portable runtime
is accepted, an invalid existing target is left untouched unless --force is used,
and --force renames the existing folder to a backup instead of deleting it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_MANIFEST = SCRIPT_DIR / "comfyui_portable_manifest.json"
DEFAULT_CACHE_DIR = PROJECT_ROOT / ".installer_cache" / "comfyui-portable"
APPROVED_STATUS = "approved"
CHUNK_SIZE = 1024 * 1024
CORE_REQUIRED_FILES = [
    "ComfyUI/main.py",
    "ComfyUI/comfy/sd.py",
    "ComfyUI/comfy/ldm/models/autoencoder.py",
    "ComfyUI/comfy/ldm/models/diffusion/ddpm.py",
    "ComfyUI/comfy/ldm/modules/attention.py",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install ComfyUI Windows portable from a manifest.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Path to comfyui_portable_manifest.json.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without downloading or writing files.")
    parser.add_argument("--yes", action="store_true", help="Run without interactive confirmation.")
    parser.add_argument(
        "--allow-pending",
        action="store_true",
        help="Allow manifests whose redistribution_status is not approved.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="If target exists but is invalid, rename it to a backup before installing.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE_DIR),
        help="Download/reassembly cache directory. Defaults to .installer_cache/comfyui-portable.",
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


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("required_files"), list) or not data["required_files"]:
        raise ValueError("Manifest must contain a non-empty required_files list.")
    if not isinstance(data.get("parts"), list) or not data["parts"]:
        raise ValueError("Manifest must contain a non-empty parts list.")
    if not str(data.get("target_dir") or "").strip():
        raise ValueError("Manifest must contain target_dir.")
    return data


def safe_relative_path(relative_path: str) -> Path:
    pure = PurePosixPath(relative_path.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or not pure.name:
        raise ValueError(f"Unsafe relative path in manifest: {relative_path!r}")
    return Path(*pure.parts)


def target_dir_from_manifest(manifest: dict[str, Any]) -> Path:
    rel = safe_relative_path(str(manifest.get("target_dir") or ""))
    return (PROJECT_ROOT / rel).resolve()


def validate_required_files(root: Path, manifest: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    required = list(dict.fromkeys([str(item) for item in manifest["required_files"]] + CORE_REQUIRED_FILES))
    for item in required:
        rel = safe_relative_path(str(item))
        if not (root / rel).is_file():
            missing.append(str(item).replace("/", "\\"))
    return missing


def format_missing_required_files(missing: list[str]) -> str:
    return "\n".join(f"  - {item}" for item in missing)


def classify_missing_required_files(missing: list[str]) -> str:
    normalized = [item.replace("\\", "/") for item in missing]
    if any(path.startswith("ComfyUI/comfy/") for path in normalized):
        return (
            "Core ComfyUI Python package files are missing. This is an incomplete or corrupted "
            "ComfyUI portable runtime, not a missing checkpoint/model download."
        )
    if any(path.startswith("python_embeded/") for path in normalized):
        return "The embedded Python runtime is incomplete or corrupted."
    if any(path.startswith("ComfyUI/") for path in normalized):
        return "The ComfyUI application tree is incomplete or corrupted."
    return "Required ComfyUI portable runtime files are missing."


def print_invalid_target_guidance(missing: list[str], force: bool) -> None:
    print("WARNING: Existing ComfyUI target is present but invalid/missing required files:")
    print(format_missing_required_files(missing))
    print(classify_missing_required_files(missing))
    print("ОБНАРУЖЕНО ПОВРЕЖДЕНИЕ ЯДРА ComfyUI: отсутствуют файлы comfy/ldm/models.")
    print("Установщик переустановит базовый ComfyUI portable из проверенного архива и сохранит старую папку как backup.")
    if not force:
        print()
        print("Repair action:")
        print("  Rerun this installer with --force to rename the broken folder to a timestamped backup")
        print("  and install a clean ComfyUI portable runtime from the verified release archive.")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE * 8), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": "XTTS-Studio-ComfyUI-Portable-Installer/1.0"})


def download_file(url: str, target: Path, expected_sha256: str = "") -> None:
    part_path = target.with_name(target.name + ".download")
    if part_path.exists():
        part_path.unlink()
    digest = hashlib.sha256()
    downloaded = 0
    next_report = 0
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(make_request(url), timeout=60) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise RuntimeError(f"Unexpected HTTP status: {status}")
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else None
            print(f"Downloading {url}")
            print(f"Remote size: {format_size(total)}")
            with part_path.open("wb") as handle:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_report:
                        if total:
                            pct = downloaded * 100.0 / total
                            print(f"Downloaded {format_size(downloaded)} / {format_size(total)} ({pct:.1f}%)")
                        else:
                            print(f"Downloaded {format_size(downloaded)}")
                        next_report = downloaded + 512 * 1024 * 1024
        actual = digest.hexdigest()
        if expected_sha256 and actual.lower() != expected_sha256.lower():
            raise RuntimeError(f"SHA256 mismatch for {target.name}: expected {expected_sha256}, got {actual}")
        part_path.replace(target)
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise


def ensure_parts(manifest: dict[str, Any], cache_dir: Path, dry_run: bool) -> list[Path]:
    part_paths: list[Path] = []
    for index, part in enumerate(manifest.get("parts") or [], start=1):
        if not isinstance(part, dict):
            raise ValueError(f"Manifest part {index} must be an object.")
        name = str(part.get("name") or "").strip()
        url = str(part.get("url") or "").strip()
        if not name or not url:
            raise ValueError(f"Manifest part {index} must contain name and url.")
        target = cache_dir / safe_relative_path(name)
        expected_sha = str(part.get("sha256") or "").strip()
        part_paths.append(target)
        if dry_run:
            print(f"Would ensure part {index}: {url} -> {target}")
            continue
        if target.exists():
            if expected_sha:
                actual = sha256_file(target)
                if actual.lower() == expected_sha.lower():
                    print(f"Cached part OK: {target.name}")
                    continue
                print(f"Cached part SHA256 mismatch; redownloading: {target.name}")
                target.unlink()
            else:
                print(f"Using cached part without per-part SHA256: {target.name}")
                continue
        download_file(url, target, expected_sha)
    return part_paths


def reassemble_zip(manifest: dict[str, Any], part_paths: list[Path], cache_dir: Path, dry_run: bool) -> Path:
    archive_name = str(manifest.get("archive_base_name") or "comfyui_windows_portable.zip").strip()
    archive_path = cache_dir / safe_relative_path(archive_name)
    expected_sha = str(manifest.get("sha256") or "").strip()
    if dry_run:
        print(f"Would reassemble {len(part_paths)} part(s) into {archive_path}")
        return archive_path
    if archive_path.exists() and expected_sha:
        actual = sha256_file(archive_path)
        if actual.lower() == expected_sha.lower():
            print(f"Cached archive SHA256 OK: {archive_path}")
            return archive_path
        print("Cached archive SHA256 mismatch; rebuilding from parts.")
        archive_path.unlink()
    elif archive_path.exists() and len(part_paths) == 1 and part_paths[0] == archive_path:
        return archive_path
    tmp_path = archive_path.with_name(archive_path.name + ".reassemble")
    if tmp_path.exists():
        tmp_path.unlink()
    with tmp_path.open("wb") as output:
        for part_path in part_paths:
            with part_path.open("rb") as input_handle:
                shutil.copyfileobj(input_handle, output, length=CHUNK_SIZE * 8)
    if expected_sha:
        actual = sha256_file(tmp_path)
        if actual.lower() != expected_sha.lower():
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"Archive SHA256 mismatch: expected {expected_sha}, got {actual}")
    tmp_path.replace(archive_path)
    return archive_path


def find_extracted_runtime(extract_root: Path, manifest: dict[str, Any]) -> Path:
    direct_missing = validate_required_files(extract_root, manifest)
    if not direct_missing:
        return extract_root
    target_name = str(manifest.get("target_dir") or "ComfyUI_windows_portable")
    candidates = [extract_root / target_name]
    candidates.extend([item for item in extract_root.iterdir() if item.is_dir()])
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not validate_required_files(candidate, manifest):
            return candidate
    raise RuntimeError("Extracted archive is missing required files: " + ", ".join(direct_missing))


def backup_existing_target(target_dir: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = target_dir.with_name(f"{target_dir.name}.backup-{stamp}")
    suffix = 1
    while backup.exists():
        backup = target_dir.with_name(f"{target_dir.name}.backup-{stamp}-{suffix}")
        suffix += 1
    target_dir.rename(backup)
    return backup


def install_from_archive(archive_path: Path, target_dir: Path, manifest: dict[str, Any], force: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="comfyui-portable-extract-", dir=str(DEFAULT_CACHE_DIR.parent)) as temp_name:
        extract_root = Path(temp_name)
        print(f"Extracting archive to temporary folder: {extract_root}")
        with zipfile.ZipFile(archive_path, "r") as archive:
            archive.extractall(extract_root)
        runtime_root = find_extracted_runtime(extract_root, manifest)
        if target_dir.exists():
            if not force:
                raise RuntimeError(f"Target already exists and --force was not provided: {target_dir}")
            backup = backup_existing_target(target_dir)
            print(f"Existing invalid target was renamed to backup: {backup}")
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(runtime_root), str(target_dir))
    missing = validate_required_files(target_dir, manifest)
    if missing:
        raise RuntimeError(
            "Installed runtime failed validation:\n"
            + format_missing_required_files(missing)
            + "\n"
            + classify_missing_required_files(missing)
        )


def print_plan(manifest: dict[str, Any], target_dir: Path, cache_dir: Path, args: argparse.Namespace) -> None:
    print("ComfyUI portable runtime installer")
    print("===================================")
    print(f"Manifest:              {Path(args.manifest).resolve()}")
    print(f"Release repo:          {manifest.get('repo', 'unknown')}")
    print(f"Release tag:           {manifest.get('release_tag', 'unknown')}")
    print(f"Redistribution status: {manifest.get('redistribution_status', 'unknown')}")
    print(f"Target folder:         {target_dir}")
    print(f"Cache folder:          {cache_dir}")
    print(f"Archive:               {manifest.get('archive_base_name', 'unknown')} ({format_size(manifest.get('size_bytes'))})")
    print(f"Archive SHA256:        {manifest.get('sha256') or 'not provided'}")
    print(f"Mode:                  {'dry-run' if args.dry_run else 'install'}")
    print()
    print("Safety:")
    print("  Existing valid ComfyUI portable installs are left untouched.")
    print("  Existing invalid target folders fail by default; --force renames them to a backup first.")
    print("  Runtime archives and split parts are cached under .installer_cache and are not Git-tracked.")
    print("  pending_review manifests require --allow-pending.")
    print()


def main() -> int:
    args = build_parser().parse_args()
    try:
        manifest = load_manifest(Path(args.manifest))
        target_dir = target_dir_from_manifest(manifest)
        cache_dir = Path(args.cache_dir).resolve()
        print_plan(manifest, target_dir, cache_dir, args)

        if target_dir.exists():
            missing = validate_required_files(target_dir, manifest)
            if not missing:
                print(f"ComfyUI portable is already installed and valid: {target_dir}")
                return 0
            print_invalid_target_guidance(missing, args.force)
            if not args.force:
                return 1

        status = str(manifest.get("redistribution_status") or "").strip().lower()
        if status != APPROVED_STATUS and not args.allow_pending:
            print(f"Redistribution status is {status or 'unknown'}; rerun with --allow-pending only after local approval.")
            return 1

        if args.dry_run:
            ensure_parts(manifest, cache_dir, dry_run=True)
            print(f"Would validate archive, extract to a temporary folder, and install into: {target_dir}")
            return 0

        if not args.yes:
            answer = input("Download/install ComfyUI portable runtime? Type Y to continue: ").strip()
            if answer != "Y":
                print("Cancelled. No files were installed.")
                return 0

        part_paths = ensure_parts(manifest, cache_dir, dry_run=False)
        archive_path = reassemble_zip(manifest, part_paths, cache_dir, dry_run=False)
        install_from_archive(archive_path, target_dir, manifest, args.force)
        print(f"ComfyUI portable installed successfully: {target_dir}")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"ERROR: Download failed with HTTP {exc.code}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
