import re
import uuid
from pathlib import Path
from typing import Any

import numpy as np


def clamp_pause(value: Any, fallback: float = 0.0) -> float:
    try:
        pause = float(fallback if value is None else value)
    except (TypeError, ValueError):
        pause = float(fallback)
    return round(max(0.0, min(30.0, pause)), 3)


def envelope_values(points: list[dict[str, Any]], total_len: int, sr: int, base_volume: float) -> np.ndarray:
    if total_len <= 0:
        return np.zeros(0, dtype=np.float32)
    if not points:
        return np.full(total_len, base_volume, dtype=np.float32)
    sorted_points = sorted(points, key=lambda p: float(p.get("time", 0.0)))
    xp = np.array([max(0, int(float(p.get("time", 0.0)) * sr)) for p in sorted_points], dtype=np.int64)
    fp = np.array([max(0.0, min(2.0, float(p.get("volume", base_volume)))) for p in sorted_points], dtype=np.float32)
    if xp[0] > 0:
        xp = np.insert(xp, 0, 0)
        fp = np.insert(fp, 0, fp[0])
    if xp[-1] < total_len - 1:
        xp = np.append(xp, total_len - 1)
        fp = np.append(fp, fp[-1])
    return np.interp(np.arange(total_len), xp, fp).astype(np.float32)


def room_tone(sr: int, seconds: float, seed: int, level: float) -> np.ndarray:
    n = max(0, int(seconds * sr))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, level, n).astype(np.float32)
    fade = min(n // 3, int(0.08 * sr))
    if fade > 1:
        noise[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        noise[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return noise


def append_crossfaded(parts: list[np.ndarray], new: np.ndarray, sr: int, crossfade_sec: float) -> None:
    if new.size == 0:
        return
    if not parts or crossfade_sec <= 0:
        parts.append(new.astype(np.float32))
        return
    prev = parts.pop()
    n = min(int(crossfade_sec * sr), len(prev) // 3, len(new) // 3)
    if n <= 1:
        parts.extend([prev, new.astype(np.float32)])
        return
    fade_out = np.linspace(1.0, 0.0, n, dtype=np.float32)
    fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
    parts.append(np.concatenate([prev[:-n], prev[-n:] * fade_out + new[:n] * fade_in, new[n:]]).astype(np.float32))


def clip_effective_duration(audio: np.ndarray, sr: int, clip: dict[str, Any]) -> float:
    try:
        offset_sec = max(0.0, float(clip.get("offset_sec", 0.0) or 0.0))
    except (TypeError, ValueError):
        offset_sec = 0.0
    try:
        duration_sec = max(0.0, float(clip.get("duration_sec", 0.0) or 0.0))
    except (TypeError, ValueError):
        duration_sec = 0.0
    available = max(0.0, (len(audio) / sr) - offset_sec)
    return min(duration_sec, available) if duration_sec > 0 else available


def normalize_music_clip(raw_clip: dict[str, Any], idx: int) -> dict[str, Any]:
    try:
        start_time = max(0.0, float(raw_clip.get("start_time", raw_clip.get("offset", 0.0)) or 0.0))
    except (AttributeError, TypeError, ValueError):
        start_time = 0.0
    try:
        offset_sec = max(0.0, float(raw_clip.get("offset_sec", 0.0) or 0.0))
    except (AttributeError, TypeError, ValueError):
        offset_sec = 0.0
    try:
        duration_sec = max(0.0, float(raw_clip.get("duration_sec", raw_clip.get("duration", 0.0)) or 0.0))
    except (AttributeError, TypeError, ValueError):
        duration_sec = 0.0
    try:
        volume = max(0.0, min(2.0, float(raw_clip.get("volume", 1.0) or 1.0)))
    except (AttributeError, TypeError, ValueError):
        volume = 1.0
    return {
        "id": str(raw_clip.get("id") or uuid.uuid4().hex[:10]),
        "start_time": round(start_time, 3),
        "offset_sec": round(offset_sec, 3),
        "duration_sec": round(duration_sec, 3),
        "volume": round(volume, 3),
    }


def normalize_music_source_duration(raw_source: dict[str, Any]) -> float | None:
    if raw_source.get("duration") is None:
        return None
    try:
        return round(max(0.0, float(raw_source.get("duration") or 0.0)), 3)
    except (AttributeError, TypeError, ValueError):
        return None


def music_source_item(raw_source: dict[str, Any], source_id: str, path: str, idx: int) -> dict[str, Any]:
    item = {
        "id": source_id,
        "path": path,
        "label": str(raw_source.get("label") or Path(path).name or f"Music source {idx + 1}"),
    }
    duration = normalize_music_source_duration(raw_source)
    if duration is not None:
        item["duration"] = duration
    return item


def normalize_music_volume(value: Any, fallback: float = 1.0) -> float:
    try:
        volume = max(0.0, min(2.0, float(value or fallback)))
    except (TypeError, ValueError):
        volume = fallback
    return round(volume, 3)


def normalize_music_lane_order(raw_lane: dict[str, Any], idx: int) -> int:
    try:
        return int(raw_lane.get("order", idx) or idx)
    except (TypeError, ValueError):
        return idx


def normalize_music_mode(value: Any) -> str:
    return value if value in {"loop", "once", "chain_loop"} else "loop"


def normalize_music_lane_defaults(raw_lane: dict[str, Any], idx: int) -> dict[str, Any]:
    return {
        "volume": normalize_music_volume(raw_lane.get("volume", 1.0)),
        "volume_envelope": normalize_volume_envelope_points(raw_lane.get("volume_envelope") if isinstance(raw_lane.get("volume_envelope"), list) else [], 1.0),
        "order": normalize_music_lane_order(raw_lane, idx),
    }


def legacy_music_track_lane_defaults(track: dict[str, Any], key: tuple[str, str], order: int, *, loop: bool) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:10],
        "source_id": key[0],
        "path": key[1],
        "label": str(track.get("label") or Path(key[1]).name or f"Music lane {order + 1}"),
        "enabled": True,
        "loop": loop,
        "volume": 1.0,
        "volume_envelope": [{"time": 0.0, "volume": 1.0}],
        "order": order,
        "clips": [],
    }


def legacy_music_path_track_item(path: str, source_id: str) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:10],
        "source_id": source_id,
        "path": path,
        "start_time": 0.0,
        "offset_sec": 0.0,
        "volume": 1.0,
        "label": Path(path).name,
    }


def music_lane_item(raw_lane: dict[str, Any], source_id: str, path: str, idx: int, lane_defaults: dict[str, Any], clips: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": str(raw_lane.get("id") or uuid.uuid4().hex[:10]),
        "source_id": source_id,
        "path": path,
        "label": str(raw_lane.get("label") or Path(path).name or f"Music lane {idx + 1}"),
        "enabled": bool(raw_lane.get("enabled", True)),
        "loop": bool(raw_lane.get("loop", False)),
        "volume": lane_defaults["volume"],
        "volume_envelope": lane_defaults["volume_envelope"],
        "order": lane_defaults["order"],
        "clips": clips,
    }


def normalize_music_lane_clips(raw_lane: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        normalize_music_clip(clip, clip_idx)
        for clip_idx, clip in enumerate(raw_lane.get("clips") if isinstance(raw_lane.get("clips"), list) else [])
        if isinstance(clip, dict)
    ]


def normalize_music_lanes_order(lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered_lanes = sorted(lanes, key=lambda item: item.get("order", 0))
    for order, lane in enumerate(ordered_lanes):
        lane["order"] = order
    return ordered_lanes


def music_track_clip_projection(track: dict[str, Any], clip: dict[str, Any], source_id: str, path: str, idx: int) -> dict[str, Any]:
    return {
        "id": clip["id"],
        "source_id": source_id,
        "path": path,
        "label": str(track.get("label") or Path(path).name or f"Music clip {idx + 1}"),
        "start_time": clip["start_time"],
        "offset_sec": clip["offset_sec"],
        "duration_sec": clip["duration_sec"],
        "volume": clip["volume"],
    }


def music_lane_clip_track_projection(lane: dict[str, Any], clip: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": clip.get("id", uuid.uuid4().hex[:10]),
        "source_id": lane.get("source_id", ""),
        "path": lane.get("path", ""),
        "label": lane.get("label", Path(str(lane.get("path", ""))).name),
        "start_time": clip.get("start_time", 0.0),
        "offset_sec": clip.get("offset_sec", 0.0),
        "duration_sec": clip.get("duration_sec", 0.0),
        "volume": clip.get("volume", 1.0),
    }


def music_lanes_track_projection(lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened_tracks: list[dict[str, Any]] = []
    for lane in lanes:
        for clip in lane.get("clips", []):
            flattened_tracks.append(music_lane_clip_track_projection(lane, clip))
    return flattened_tracks


def normalize_volume_envelope_points(raw_points: Any, fallback_volume: float) -> list[dict[str, float]]:
    points = raw_points or [{"time": 0.0, "volume": fallback_volume}]
    clean_points: list[dict[str, float]] = []
    for point in points:
        try:
            clean_points.append({
                "time": round(max(0.0, float(point.get("time", 0.0))), 3),
                "volume": round(max(0.0, min(2.0, float(point.get("volume", fallback_volume)))), 3),
            })
        except (AttributeError, TypeError, ValueError):
            continue
    return sorted(clean_points or [{"time": 0.0, "volume": fallback_volume}], key=lambda p: p["time"])


def sanitize_bitrate(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip().lower()
    if re.fullmatch(r"[1-9][0-9]{1,3}k", text):
        return text
    return fallback
