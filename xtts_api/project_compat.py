"""Compatibility helpers for loading older XTTS Studio project shapes."""

from __future__ import annotations

import uuid
from typing import Any


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def normalize_legacy_chunk(raw: Any, order: int) -> dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"text": raw}
    if not isinstance(raw, dict):
        return None
    chunk = dict(raw)
    chunk["id"] = str(raw.get("id") or raw.get("chunk_id") or "").strip() or uuid.uuid4().hex[:12]
    try:
        chunk["order"] = int(raw.get("order", order))
    except (TypeError, ValueError):
        chunk["order"] = order
    chunk["text"] = str(raw.get("text") or raw.get("raw_text") or raw.get("content") or "")
    if raw.get("tts_text") is not None:
        chunk["tts_text"] = str(raw.get("tts_text") or "")
    if raw.get("stressed_text") is not None:
        chunk["stressed_text"] = str(raw.get("stressed_text") or "")
    try:
        chunk["pause_after"] = max(0.0, float(raw.get("pause_after", raw.get("pause", 0.25)) or 0.0))
    except (TypeError, ValueError):
        chunk["pause_after"] = 0.25
    if raw.get("boundary_type") is not None:
        chunk["boundary_type"] = str(raw.get("boundary_type") or "sentence")
    return chunk


def extract_legacy_chunks(project: dict[str, Any] | None) -> list[dict[str, Any]]:
    project = project if isinstance(project, dict) else {}
    candidates: list[Any] = [
        project.get("chunks"),
        project.get("timeline") if isinstance(project.get("timeline"), list) else None,
        project.get("timeline", {}).get("chunks") if isinstance(project.get("timeline"), dict) else None,
        project.get("project", {}).get("chunks") if isinstance(project.get("project"), dict) else None,
        project.get("arrangement", {}).get("timeline", {}).get("chunks") if isinstance(project.get("arrangement"), dict) and isinstance(project.get("arrangement", {}).get("timeline"), dict) else None,
        project.get("arrangement", {}).get("voice", {}).get("chunks") if isinstance(project.get("arrangement"), dict) and isinstance(project.get("arrangement", {}).get("voice"), dict) else None,
    ]
    raw_chunks = next((_as_list(candidate) for candidate in candidates if _as_list(candidate)), [])
    chunks = [chunk for idx, raw in enumerate(raw_chunks) if (chunk := normalize_legacy_chunk(raw, idx))]
    chunks.sort(key=lambda item: item.get("order", 0))
    for idx, chunk in enumerate(chunks):
        chunk["order"] = idx
    return chunks
