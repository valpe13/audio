import hashlib
import math
import uuid
import wave
from pathlib import Path
from typing import Any, Callable

try:
    from studio_prompt_helpers import truncate_text
except ImportError:  # pragma: no cover - package-style imports
    from .studio_prompt_helpers import truncate_text


def normalize_group_image_meta(raw_image: Any) -> dict[str, Any]:
    if not isinstance(raw_image, dict):
        return {}
    meta: dict[str, Any] = {
        "status": str(raw_image.get("status") or "ready")[:40],
        "provider": str(raw_image.get("provider") or "placeholder")[:40],
        "model": str(raw_image.get("model") or "")[:80],
        "aspect_ratio": str(raw_image.get("aspect_ratio") or "")[:40],
        "path": str(raw_image.get("path") or ""),
        "url": str(raw_image.get("url") or ""),
        "positive_prompt": truncate_text(raw_image.get("positive_prompt"), 3000),
        "negative_prompt": truncate_text(raw_image.get("negative_prompt"), 1500),
        "error": truncate_text(raw_image.get("error"), 1000),
    }
    for key in ("width", "height", "seed", "created_at", "updated_at"):
        if raw_image.get(key) is not None:
            meta[key] = raw_image.get(key)
    return {key: value for key, value in meta.items() if value not in (None, "")}


def normalize_group_video_meta(raw_video: Any) -> dict[str, Any]:
    if not isinstance(raw_video, dict):
        return {}
    meta: dict[str, Any] = {
        "status": str(raw_video.get("status") or "ready")[:40],
        "provider": str(raw_video.get("provider") or "comfyui")[:40],
        "model": str(raw_video.get("model") or "svd_xt")[:80],
        "model_checkpoint": str(raw_video.get("model_checkpoint") or "")[:200],
        "aspect_ratio": str(raw_video.get("aspect_ratio") or "")[:40],
        "resolution": str(raw_video.get("resolution") or "")[:40],
        "path": str(raw_video.get("path") or ""),
        "url": str(raw_video.get("url") or ""),
        "source_image_path": str(raw_video.get("source_image_path") or ""),
        "request_id": str(raw_video.get("request_id") or "")[:120],
        "positive_prompt": truncate_text(raw_video.get("positive_prompt"), 3000),
        "error": truncate_text(raw_video.get("error"), 1000),
    }
    for key in ("width", "height", "seed", "frames", "fps", "output_fps", "output_frames", "loop_count", "target_duration_sec", "motion_bucket_id", "augmentation_level", "min_cfg", "cfg", "steps", "created_at", "updated_at", "duration_sec"):
        if raw_video.get(key) is not None:
            meta[key] = raw_video.get(key)
    for key in ("loop", "pingpong"):
        if raw_video.get(key) is not None:
            meta[key] = bool(raw_video.get(key))
    return {key: value for key, value in meta.items() if value not in (None, "")}


def normalize_group_media_duration(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(fallback if value in (None, "") else value)
    except (TypeError, ValueError):
        number = float(fallback or 0.0)
    if not math.isfinite(number):
        number = float(fallback or 0.0)
    return round(max(0.0, min(36000.0, number)), 3)


def normalize_group_media_layout(value: Any) -> str:
    layout = str(value or "sequence").strip().lower()
    return layout if layout in {"sequence", "overlay", "background", "manual"} else "sequence"


def normalize_group_media_item(raw_item: Any, idx: int = 0) -> dict[str, Any] | None:
    if not isinstance(raw_item, dict):
        return None
    media_type = str(raw_item.get("type") or raw_item.get("media_type") or "image").strip().lower()
    if media_type not in {"image", "video"}:
        media_type = "video" if str(raw_item.get("path") or raw_item.get("url") or "").lower().endswith((".mp4", ".webm", ".gif", ".mov")) else "image"
    path = str(raw_item.get("path") or "").strip()
    url = str(raw_item.get("url") or "").strip()
    item: dict[str, Any] = {
        "id": str(raw_item.get("id") or uuid.uuid4().hex[:10]),
        "type": media_type,
        "path": path,
        "url": url,
        "label": truncate_text(raw_item.get("label") or Path(path).name or f"Media {idx + 1}", 120),
        "role": truncate_text(raw_item.get("role") or "main", 80),
        "start_offset_sec": normalize_group_media_duration(raw_item.get("start_offset_sec"), 0.0),
        "duration_sec": normalize_group_media_duration(raw_item.get("duration_sec"), 0.0),
        "scheduled": bool(raw_item.get("scheduled", raw_item.get("timeline_enabled", raw_item.get("placed", True)))),
        "fit": str(raw_item.get("fit") or "cover").strip().lower(),
        "order": idx,
    }
    if raw_item.get("kind") is not None:
        item["kind"] = truncate_text(raw_item.get("kind"), 80)
    if raw_item.get("source_id") is not None:
        item["source_id"] = truncate_text(raw_item.get("source_id"), 120)
    if item["fit"] not in {"cover", "contain", "fill"}:
        item["fit"] = "cover"
    if raw_item.get("volume") is not None:
        try:
            item["volume"] = round(max(0.0, min(2.0, float(raw_item.get("volume") or 0.0))), 3)
        except (TypeError, ValueError):
            item["volume"] = 1.0
    if raw_item.get("source") is not None:
        item["source"] = truncate_text(raw_item.get("source"), 80)
    for key, limit in (("timeline_source", 80), ("auto_sequence_id", 160), ("chunk_id", 80), ("prompt_scope", 80), ("prompt_source", 120), ("provider", 80), ("model", 120), ("positive_prompt", 3000), ("negative_prompt", 1500)):
        if raw_item.get(key) is not None:
            item[key] = truncate_text(raw_item.get(key), limit)
    for key in ("sequence_index", "sequence_count"):
        if raw_item.get(key) is not None:
            try:
                item[key] = max(1, min(100, int(raw_item.get(key) or 1)))
            except (TypeError, ValueError):
                item[key] = 1
    if raw_item.get("created_at") is not None:
        item["created_at"] = raw_item.get("created_at")
    return item


def normalize_group_media_items(raw_items: Any, group: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(raw_items, list):
        for idx, raw_item in enumerate(raw_items):
            item = normalize_group_media_item(raw_item, idx)
            if item:
                items.append(item)
    group = group if isinstance(group, dict) else {}
    legacy: list[dict[str, Any]] = []
    image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
    video_meta = group.get("video") if isinstance(group.get("video"), dict) else {}
    if image_meta.get("path") or image_meta.get("url"):
        image_key = str(image_meta.get("path") or image_meta.get("url") or "")
        legacy.append({"id": f"legacy_image_{hashlib.sha1(image_key.encode('utf-8')).hexdigest()[:8]}", "type": "image", "path": image_meta.get("path", ""), "url": image_meta.get("url", ""), "label": "Generated image", "role": "library", "duration_sec": 0.0, "scheduled": False, "source": "generated"})
    if video_meta.get("path") or video_meta.get("url"):
        video_key = str(video_meta.get("path") or video_meta.get("url") or "")
        legacy.append({"id": f"legacy_video_{hashlib.sha1(video_key.encode('utf-8')).hexdigest()[:8]}", "type": "video", "path": video_meta.get("path", ""), "url": video_meta.get("url", ""), "label": "Generated video", "role": "library", "duration_sec": float(video_meta.get("duration_sec") or 0.0), "scheduled": False, "source": "generated"})
    seen = {str(item.get("path") or item.get("url") or item.get("id")) for item in items}
    for raw_item in legacy:
        key = str(raw_item.get("path") or raw_item.get("url") or raw_item.get("id"))
        if key in seen:
            continue
        item = normalize_group_media_item(raw_item, len(items))
        if item:
            items.append(item)
            seen.add(key)
    for idx, item in enumerate(items):
        item["order"] = idx
    prevent_group_media_overlaps(items, group)
    return items


def group_chunk_media_items(items: list[dict[str, Any]], chunk_id: str, media_type: str) -> list[dict[str, Any]]:
    """Return scheduled chunk-scoped media items with a path or URL for one chunk."""
    return [
        item
        for item in items
        if item.get("scheduled") is not False
        and item.get("type") == media_type
        and item.get("prompt_scope") == "chunk"
        and str(item.get("chunk_id") or "") == str(chunk_id)
        and (item.get("path") or item.get("url"))
    ]


def group_chunk_id_strings(group: dict[str, Any]) -> list[str]:
    """Return non-empty chunk ids from a video group as strings, preserving order."""
    return [str(item) for item in group.get("chunk_ids", []) if str(item)]


def build_normalized_video_group_media_subtitle_fields(
    prompt_fields: dict[str, Any],
    *,
    playback_speed: float,
    image: dict[str, Any] | None = None,
    video: dict[str, Any] | None = None,
    media_items: list[dict[str, Any]] | None = None,
    media_layout: str = "sequence",
    default_media_duration_sec: float = 0.0,
    subtitle_defaults: dict[str, Any] | None = None,
    subtitle_blocks: list[dict[str, Any]] | None = None,
    repair_note: str = "",
) -> dict[str, Any]:
    """Return one normalized video-group item with media/subtitle fields attached."""
    item = dict(prompt_fields)
    item["playback_speed"] = playback_speed
    if isinstance(image, dict) and image:
        item["image"] = image
    if isinstance(video, dict) and video:
        item["video"] = video
    item["media_items"] = list(media_items or [])
    item["media_layout"] = media_layout
    item["default_media_duration_sec"] = default_media_duration_sec
    item["subtitle_defaults"] = dict(subtitle_defaults or {})
    item["subtitle_blocks"] = list(subtitle_blocks or [])
    if repair_note:
        item["repair_note"] = repair_note
    return item


def select_normalized_media_meta(meta: Any) -> dict[str, Any] | None:
    """Return normalized media metadata when it is an object, otherwise None."""
    return meta if isinstance(meta, dict) else None


def build_normalized_video_group_media_field_args(raw_group: dict[str, Any], media_group: dict[str, Any]) -> dict[str, Any]:
    """Return normalized media keyword arguments for a normalized video-group item."""
    return {
        "image": select_normalized_media_meta(media_group.get("image")),
        "video": select_normalized_media_meta(media_group.get("video")),
        "media_items": normalize_group_media_items(raw_group.get("media_items"), media_group),
        "media_layout": normalize_group_media_layout(raw_group.get("media_layout")),
        "default_media_duration_sec": normalize_group_media_duration(raw_group.get("default_media_duration_sec"), 0.0),
    }


def build_media_subtitle_normalizer_context(
    prompt_fields: dict[str, Any],
    *,
    image: dict[str, Any] | None = None,
    video: dict[str, Any] | None = None,
    subtitle_defaults: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return media/subtitle context dictionaries for group child normalizers."""
    media_group = dict(prompt_fields)
    if isinstance(image, dict) and image:
        media_group["image"] = image
    if isinstance(video, dict) and video:
        media_group["video"] = video
    subtitle_group = {**media_group, "subtitle_defaults": dict(subtitle_defaults or {})}
    return media_group, subtitle_group


def format_ffmpeg_concat_file_line(path: Path) -> str:
    """Return one ffmpeg concat demuxer file-list line for a local path."""
    escaped_path = str(path).replace("\\", "/").replace("'", "'\\''")
    return f"file '{escaped_path}'\n"


def format_ffmpeg_concat_file(paths: list[Path]) -> str:
    """Return ffmpeg concat demuxer file-list content for local paths."""
    return "".join(format_ffmpeg_concat_file_line(path) for path in paths)


def make_media_stats_helpers(rel_path: Callable[[Path], str]) -> dict[str, Callable[..., dict[str, Any]]]:
    """Return path metadata helpers bound to the server's relative path formatter."""

    def wav_stats(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"path": rel_path(path), "exists": False}
        with wave.open(str(path), "rb") as wav_file:
            frames = wav_file.getnframes()
            sr = wav_file.getframerate()
            return {
                "path": rel_path(path),
                "url": f"/api/audio?path={rel_path(path)}&v={int(path.stat().st_mtime)}",
                "exists": True,
                "channels": wav_file.getnchannels(),
                "sample_rate": sr,
                "frames": frames,
                "duration_sec": round(frames / float(sr), 3),
            }

    def media_stats(path: Path, *, sample_rate: int | None = None, duration_sec: float | None = None, media_type: str = "audio") -> dict[str, Any]:
        if not path.exists():
            return {"path": rel_path(path), "exists": False, "media_type": media_type}
        suffix = path.suffix.lower().lstrip(".")
        rel = rel_path(path)
        url_path = "/api/video" if media_type == "video" else "/api/audio"
        result: dict[str, Any] = {
            "path": rel,
            "url": f"{url_path}?path={rel}&v={int(path.stat().st_mtime)}",
            "exists": True,
            "media_type": media_type,
            "format": suffix,
            "bytes": path.stat().st_size,
        }
        if sample_rate:
            result["sample_rate"] = int(sample_rate)
        if duration_sec is not None:
            result["duration_sec"] = round(float(duration_sec), 3)
        return result

    return {"wav_stats": wav_stats, "media_stats": media_stats}


def prevent_group_media_overlaps(items: list[dict[str, Any]], group: dict[str, Any] | None = None) -> None:
    duration = 36000.0
    if isinstance(group, dict):
        try:
            duration = max(0.05, float(group.get("duration") or group.get("duration_sec") or duration))
        except (TypeError, ValueError):
            pass
    occupied: list[tuple[float, float]] = []
    for item in items:
        if item.get("scheduled") is False:
            continue
        start = max(0.0, min(duration, float(item.get("start_offset_sec") or 0.0)))
        length = max(0.05, min(duration, float(item.get("duration_sec") or 0.0) or duration))
        length = min(length, max(0.05, duration - start))
        for occ_start, occ_end in sorted(occupied):
            if start + length <= occ_start + 0.001 or start >= occ_end - 0.001:
                continue
            start = occ_end
        if start >= duration - 0.001:
            item["scheduled"] = False
            item["kind"] = "media_asset"
            continue
        length = min(length, duration - start)
        if length < 0.05:
            item["scheduled"] = False
            item["kind"] = "media_asset"
            continue
        item["start_offset_sec"] = round(start, 3)
        item["duration_sec"] = round(length, 3)
        item["kind"] = item.get("kind") or "timeline_block"
        occupied.append((start, start + length))
