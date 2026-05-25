import time
import unicodedata
import uuid
from typing import Any

try:
    from studio_audio_helpers import clamp_pause
    from studio_storage import normalize_loaded_chunk_selected_version
    from studio_text import clean_text, compact_stress_validation_text, repair_mojibake_text
except ImportError:  # pragma: no cover - package-style imports
    from .studio_audio_helpers import clamp_pause
    from .studio_storage import normalize_loaded_chunk_selected_version
    from .studio_text import clean_text, compact_stress_validation_text, repair_mojibake_text


def create_chunk_dict(project: dict[str, Any], payload: Any, order: int, normalize_chunk_pauses: Any) -> dict[str, Any]:
    """Create a normalized project chunk from a chunk-create payload."""
    text = repair_mojibake_text(payload.text or "")[0]
    tts_text = repair_mojibake_text(payload.tts_text)[0] if payload.tts_text is not None else text
    chunk = {
        "id": uuid.uuid4().hex[:12],
        "order": order,
        "text": text,
        "boundary_type": "sentence",
        "pause_after": clamp_pause(payload.pause_after),
        "audio_path": "",
        "audio_url": "",
        "versions": [],
        "selected_version_id": "",
        "duration_sec": 0.0,
        "generated_at": None,
    }
    if tts_text and compact_stress_validation_text(tts_text) == compact_stress_validation_text(text):
        chunk["tts_text"] = unicodedata.normalize("NFC", tts_text)
        chunk["stressed_text"] = chunk["tts_text"]
        chunk["stress_source"] = "manual" if chunk["tts_text"] != text else "original"
    normalize_chunk_pauses(project, chunk)
    return chunk


def normalize_chunk_versions(chunk: dict[str, Any]) -> None:
    """Normalize audio version metadata and ensure selected_version_id is valid."""
    versions = chunk.setdefault("versions", [])
    if chunk.get("audio_path") and not versions:
        versions.append({
            "id": "legacy",
            "label": "Legacy version",
            "audio_path": chunk.get("audio_path", ""),
            "created_at": chunk.get("generated_at") or time.time(),
            "settings": {},
            "duration_sec": chunk.get("duration_sec", 0.0),
            "index": 1,
        })
    for idx, version in enumerate(versions, start=1):
        version.setdefault("id", uuid.uuid4().hex[:10])
        version.setdefault("label", f"v{idx}")
        version.setdefault("audio_path", "")
        version.setdefault("created_at", chunk.get("generated_at") or time.time())
        version.setdefault("duration_sec", 0.0)
        version.setdefault("settings", {})
        version.setdefault("index", idx)
        settings = version.get("settings") if isinstance(version.get("settings"), dict) else {}
        if not isinstance(version.get("settings"), dict):
            version["settings"] = settings
        text_snapshot = version.get("text") or settings.get("text") or chunk.get("text") or ""
        tts_snapshot = version.get("tts_text") or settings.get("tts_text") or version.get("stressed_text") or text_snapshot
        version["text"] = clean_text(text_snapshot)
        version["tts_text"] = unicodedata.normalize("NFC", str(tts_snapshot or version["text"]))
        settings.setdefault("text", version["text"])
        settings.setdefault("tts_text", version["tts_text"])
    normalize_loaded_chunk_selected_version(chunk)


def get_selected_version(chunk: dict[str, Any]) -> dict[str, Any] | None:
    """Return the currently selected audio version after normalizing version metadata."""
    normalize_chunk_versions(chunk)
    selected_id = chunk.get("selected_version_id")
    versions = chunk.get("versions", [])
    return next((v for v in versions if v.get("id") == selected_id), None)


def selected_chunk_audio_path(chunk: dict[str, Any], resolve_user_path: Any) -> Any:
    """Return the resolved audio path for the selected chunk version, if any."""
    selected = get_selected_version(chunk)
    audio_value = selected.get("audio_path") if selected else chunk.get("audio_path")
    return resolve_user_path(audio_value) if audio_value else None


def sync_chunk_to_selected_version(chunk: dict[str, Any]) -> None:
    """Sync denormalized chunk audio/text fields from the selected version."""
    selected = get_selected_version(chunk)
    if selected:
        chunk["audio_path"] = selected.get("audio_path", "")
        chunk["duration_sec"] = selected.get("duration_sec", 0.0)
        version_text = selected.get("text") or selected.get("settings", {}).get("text")
        version_tts_text = selected.get("tts_text") or selected.get("settings", {}).get("tts_text")
        if version_text:
            chunk["text"] = str(version_text)
        if version_tts_text:
            chunk["tts_text"] = unicodedata.normalize("NFC", str(version_tts_text))
            chunk["stressed_text"] = chunk["tts_text"]
            base_text = str(chunk.get("text") or "")
            chunk["stress_source"] = "manual" if chunk["tts_text"] != base_text else "original"
    else:
        chunk["audio_path"] = ""
        chunk["duration_sec"] = 0.0


def reset_current_chunk_audio_selection(chunk: dict[str, Any]) -> None:
    """Invalidate the currently selected audio without deleting historical versions."""
    normalize_chunk_versions(chunk)
    chunk["audio_path"] = ""
    chunk["audio_url"] = ""
    chunk["selected_version_id"] = ""
    chunk["duration_sec"] = 0.0


def make_chunk_pause_helpers(deps: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic chunk pause normalization helpers."""
    default_settings = deps["DEFAULT_SETTINGS"]

    def pause_range_for_boundary(boundary_type: Any, low: float, high: float) -> tuple[float, float]:
        low_value = clamp_pause(low)
        high_value = clamp_pause(high)
        if high_value < low_value:
            low_value, high_value = high_value, low_value
        span = max(0.01, high_value - low_value)
        kind = str(boundary_type or "sentence").lower()
        if kind == "section":
            return clamp_pause(max(0.9, high_value + span * 2.0)), clamp_pause(max(1.4, high_value + span * 3.8))
        if kind == "paragraph":
            return clamp_pause(max(0.45, high_value + span * 0.9)), clamp_pause(max(0.9, high_value + span * 2.2))
        return low_value, high_value

    def stable_split_pause_after(project: dict[str, Any], text: str, order: int, low: float, high: float, boundary_type: Any = "sentence") -> float:
        low_value = clamp_pause(low)
        high_value = clamp_pause(high)
        if high_value < low_value:
            low_value, high_value = high_value, low_value
        if abs(high_value - low_value) < 0.0005:
            return round(low_value, 3)
        settings = project.get("settings", {})
        seed_payload = deps["json"].dumps({
            "project_seed": settings.get("seed", default_settings["seed"]),
            "order": order,
            "text": text,
            "field": "pause_after",
            "min": low_value,
            "max": high_value,
            "boundary_type": boundary_type or "sentence",
        }, ensure_ascii=False, sort_keys=True)
        digest = deps["hashlib"].sha256(seed_payload.encode("utf-8")).digest()
        unit = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
        return round(low_value + (high_value - low_value) * unit, 3)

    def normalize_chunk_pauses(project: dict[str, Any], chunk: dict[str, Any]) -> None:
        fallback = chunk.get("pause_after_resolved", chunk.get("pause_after", 0.0))
        chunk["pause_after"] = clamp_pause(chunk.get("pause_after"), float(fallback or 0.0))
        chunk["pause_after_resolved"] = chunk["pause_after"]
        if chunk.get("boundary_type") not in {"sentence", "paragraph", "section"}:
            chunk["boundary_type"] = "sentence"
        for legacy_key in ("pause_before", "pause_before_min", "pause_before_max", "pause_after_min", "pause_after_max", "pause_before_resolved"):
            chunk.pop(legacy_key, None)

    return {
        "pause_range_for_boundary": pause_range_for_boundary,
        "stable_split_pause_after": stable_split_pause_after,
        "normalize_chunk_pauses": normalize_chunk_pauses,
    }
