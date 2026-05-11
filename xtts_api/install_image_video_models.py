#!/usr/bin/env python3
"""Manifest-driven image/video model installer for XTTS Studio + ComfyUI.

The installer downloads missing model files from GitHub Release assets first,
optionally falling back to original source URLs. It never overwrites existing
files unless --force is passed and writes downloads to .part files before a
final atomic replace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_MANIFEST = SCRIPT_DIR / "image_video_models_manifest.json"
DEFAULT_MODELS_DIR = PROJECT_ROOT / "ComfyUI_windows_portable" / "ComfyUI" / "models"
APPROVED_STATUS = "approved"
CHUNK_SIZE = 1024 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install/update missing XTTS Studio image/video models from a manifest."
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Path to image_video_models_manifest.json.")
    parser.add_argument(
        "--models-dir",
        default=os.environ.get("COMFYUI_MODELS_DIR", str(DEFAULT_MODELS_DIR)),
        help="ComfyUI models folder. Can also be set with COMFYUI_MODELS_DIR.",
    )
    parser.add_argument(
        "--comfyui-root",
        default=os.environ.get("COMFYUI_PORTABLE_ROOT", ""),
        help="Optional ComfyUI portable root containing ComfyUI/models. Overrides --models-dir when provided.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without downloading or writing files.")
    parser.add_argument("--yes", action="store_true", help="Run without interactive confirmation.")
    parser.add_argument("--github-first", action="store_true", default=True, help="Prefer GitHub Release URLs first.")
    parser.add_argument(
        "--allow-original-source-fallback",
        action="store_true",
        help="If GitHub download fails, try original_source_url from the manifest when present.",
    )
    parser.add_argument("--only", choices=("image", "video"), help="Install only image or only video entries.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing target files after confirmation.")
    parser.add_argument(
        "--allow-pending",
        action="store_true",
        help="Allow downloading entries whose redistribution_status is not approved.",
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
    if not isinstance(data.get("models"), list):
        raise ValueError("Manifest must contain a models list.")
    return data


def resolve_models_dir(args: argparse.Namespace) -> Path:
    if args.comfyui_root.strip():
        return (Path(args.comfyui_root).resolve() / "ComfyUI" / "models")
    return Path(args.models_dir).resolve()


def safe_target_path(models_dir: Path, relative_path: str) -> Path:
    pure = PurePosixPath(relative_path.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or not pure.name:
        raise ValueError(f"Unsafe target_relative_path in manifest: {relative_path!r}")
    target = (models_dir / Path(*pure.parts)).resolve()
    try:
        target.relative_to(models_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Manifest target escapes models directory: {relative_path!r}") from exc
    return target


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE * 8), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_request(url: str) -> urllib.request.Request:
    headers = {"User-Agent": "XTTS-Studio-Image-Video-Model-Installer/1.0"}
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if token and "huggingface.co" in url.lower():
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def download_to_part(url: str, target: Path, expected_sha256: str = "") -> None:
    part_path = target.with_name(target.name + ".part")
    if part_path.exists():
        part_path.unlink()
    digest = hashlib.sha256()
    downloaded = 0
    next_report = 0
    try:
        with urllib.request.urlopen(make_request(url), timeout=60) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise RuntimeError(f"Unexpected HTTP status: {status}")
            total = response.headers.get("Content-Length")
            total_bytes = int(total) if total and total.isdigit() else None
            print(f"Download started: {url}")
            print(f"Remote size: {format_size(total_bytes)}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with part_path.open("wb") as handle:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_report:
                        if total_bytes:
                            pct = downloaded * 100.0 / total_bytes
                            print(f"Downloaded {format_size(downloaded)} / {format_size(total_bytes)} ({pct:.1f}%)")
                        else:
                            print(f"Downloaded {format_size(downloaded)}")
                        next_report = downloaded + 512 * 1024 * 1024
        actual_sha256 = digest.hexdigest()
        if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
            raise RuntimeError(f"SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}")
        part_path.replace(target)
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise


def download_parts_to_part(urls: list[str], target: Path, expected_sha256: str = "") -> None:
    part_path = target.with_name(target.name + ".part")
    if part_path.exists():
        part_path.unlink()
    digest = hashlib.sha256()
    downloaded = 0
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with part_path.open("wb") as output:
            for index, url in enumerate(urls, start=1):
                print(f"Downloading part {index}/{len(urls)}: {url}")
                with urllib.request.urlopen(make_request(url), timeout=60) as response:
                    status = getattr(response, "status", 200)
                    if status != 200:
                        raise RuntimeError(f"Unexpected HTTP status for part {index}: {status}")
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        output.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                print(f"Downloaded combined size so far: {format_size(downloaded)}")
        actual_sha256 = digest.hexdigest()
        if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
            raise RuntimeError(f"SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}")
        part_path.replace(target)
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise


def candidate_urls(model: dict[str, Any], allow_fallback: bool) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    github_url = str(model.get("github_release_url") or "").strip()
    original_url = str(model.get("original_source_url") or "").strip()
    if github_url:
        urls.append(("GitHub Release", github_url))
    if allow_fallback and original_url:
        urls.append(("Original source fallback", original_url))
    return urls


def candidate_sources(model: dict[str, Any], allow_fallback: bool) -> list[tuple[str, str | list[str]]]:
    sources: list[tuple[str, str | list[str]]] = []
    parts = model.get("github_release_parts")
    if isinstance(parts, list) and parts and all(isinstance(url, str) and url.strip() for url in parts):
        sources.append(("GitHub Release split assets", [str(url).strip() for url in parts]))
    github_url = str(model.get("github_release_url") or "").strip()
    original_url = str(model.get("original_source_url") or "").strip()
    if github_url:
        sources.append(("GitHub Release", github_url))
    if allow_fallback and original_url:
        sources.append(("Original source fallback", original_url))
    return sources


def print_plan(manifest: dict[str, Any], models_dir: Path, selected: list[tuple[dict[str, Any], Path]], args: argparse.Namespace) -> None:
    print("XTTS Studio image/video model manifest installer")
    print("================================================")
    print(f"Manifest:      {Path(args.manifest).resolve()}")
    print(f"Release repo:  {manifest.get('repo', 'unknown')}")
    print(f"Release tag:   {manifest.get('release_tag', 'unknown')}")
    print(f"Models folder: {models_dir}")
    print(f"Mode:          {'dry-run' if args.dry_run else 'install'}")
    print()
    print("Safety:")
    print("  Existing model files are not overwritten unless --force is used.")
    print("  Downloads are written to *.part and renamed only after completion and SHA256 verification.")
    print("  Entries with redistribution_status != approved are skipped unless --allow-pending is used.")
    print("  Model binaries must remain GitHub Release assets, not Git commits.")
    print()
    for model, target in selected:
        status = str(model.get("redistribution_status") or "").strip() or "unknown"
        exists = target.exists()
        category = model.get("category", "unknown")
        print(f"- {model.get('name', model.get('filename'))} [{category}]")
        print(f"  target: {target}")
        print(f"  size:   {format_size(model.get('size_bytes'))}")
        print(f"  sha256: {model.get('sha256') or 'not provided'}")
        print(f"  status: {status}; local file: {'present' if exists else 'missing'}")
        print(f"  url:    {model.get('github_release_url') or 'not provided'}")
        if model.get("github_release_parts"):
            print(f"  split:  {len(model.get('github_release_parts') or [])} GitHub Release part assets")
        if model.get("original_source_url"):
            print(f"  fallback: {model.get('original_source_url')}")


def install_one(model: dict[str, Any], target: Path, args: argparse.Namespace) -> str:
    filename = model.get("filename", target.name)
    status = str(model.get("redistribution_status") or "").strip().lower()
    if target.exists() and not args.force:
        expected = str(model.get("sha256") or "").strip()
        if expected:
            actual = sha256_file(target)
            if actual.lower() == expected.lower():
                return f"present and verified: {filename}"
            return f"present but SHA256 differs; left untouched without --force: {filename}"
        return f"present, left untouched: {filename}"
    if status != APPROVED_STATUS and not args.allow_pending:
        return f"skipped pending license/redistribution review: {filename}"
    if args.dry_run:
        action = "would overwrite" if target.exists() and args.force else "would download"
        return f"{action}: {filename} -> {target}"
    if not args.yes:
        answer = input(f"Download {filename}? Type Y to continue: ").strip()
        if answer != "Y":
            return f"cancelled by user: {filename}"
    last_error: Exception | None = None
    sources = candidate_sources(model, args.allow_original_source_fallback)
    if not sources:
        return f"no usable URL in manifest: {filename}"
    for label, source in sources:
        try:
            print(f"Installing {filename} from {label}...")
            if isinstance(source, list):
                download_parts_to_part(source, target, str(model.get("sha256") or ""))
            else:
                download_to_part(source, target, str(model.get("sha256") or ""))
            return f"downloaded and verified: {filename}"
        except urllib.error.HTTPError as exc:
            last_error = exc
            print(f"WARNING: {label} failed for {filename}: HTTP {exc.code}", file=sys.stderr)
        except Exception as exc:
            last_error = exc
            print(f"WARNING: {label} failed for {filename}: {exc}", file=sys.stderr)
    return f"failed: {filename}: {last_error}"


def main() -> int:
    args = build_parser().parse_args()
    try:
        manifest = load_manifest(Path(args.manifest))
        models_dir = resolve_models_dir(args)
        selected: list[tuple[dict[str, Any], Path]] = []
        for model in manifest["models"]:
            if args.only and model.get("category") != args.only:
                continue
            selected.append((model, safe_target_path(models_dir, str(model.get("target_relative_path") or ""))))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print_plan(manifest, models_dir, selected, args)
    if not selected:
        print("No manifest entries selected.")
        return 0

    if not args.yes and not args.dry_run:
        answer = input("Continue with missing model downloads? Type Y to continue: ").strip()
        if answer != "Y":
            print("Cancelled. No files were created or downloaded.")
            return 0

    results = []
    failures = 0
    for model, target in selected:
        try:
            result = install_one(model, target, args)
        except Exception as exc:
            result = f"failed: {model.get('filename', target.name)}: {exc}"
        print(f"Result: {result}")
        results.append(result)
        if result.startswith("failed:"):
            failures += 1

    print()
    print("Summary:")
    for result in results:
        print(f"  - {result}")
    print()
    if failures:
        print("One or more model downloads failed. Existing files were not overwritten or deleted.")
        if not args.allow_original_source_fallback:
            print("If GitHub Release assets are not available yet, rerun with --allow-original-source-fallback.")
        return 1
    print("Installer finished. Restart ComfyUI and XTTS Studio if new model files were downloaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
