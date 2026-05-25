import json
import os
import re
import socket
import urllib.error
from typing import Any


def _strip_json_fence(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
    return raw


def extract_json_object(text: str) -> dict[str, Any]:
    raw = _strip_json_fence(text)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(raw[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("AI response root must be a JSON object")
    return parsed


def extract_json_value(text: str) -> Any:
    raw = _strip_json_fence(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        starts = [idx for idx in (raw.find("["), raw.find("{")) if idx >= 0]
        start = min(starts) if starts else -1
        end = max(raw.rfind("]"), raw.rfind("}"))
        if start < 0 or end <= start:
            raise
        return json.loads(raw[start:end + 1])


def resolve_xai_text_model(override: str | None = None, *, default_model: str = "grok-3-mini") -> str:
    """Resolve the shared xAI chat/text model used by Grok grouping and optional text helpers."""
    explicit = str(override or "").strip()
    if explicit:
        return explicit
    env_model = str(os.environ.get("XAI_MODEL") or "").strip()
    if env_model:
        return env_model
    return default_model


def bounded_int_setting(settings: dict[str, Any], key: str, default: int, *, min_value: int, max_value: int) -> int:
    try:
        value = int(settings.get(key, default))
    except (AttributeError, TypeError, ValueError):
        value = int(default)
    return max(min_value, min(max_value, value))


def bounded_float_setting(settings: dict[str, Any], key: str, default: float, *, min_value: float, max_value: float) -> float:
    try:
        value = float(settings.get(key, default))
    except (AttributeError, TypeError, ValueError):
        value = float(default)
    return max(min_value, min(max_value, value))


def preset_bounded_int_setting(settings: dict[str, Any], preset: dict[str, Any], key: str, default: int, *, min_value: int, max_value: int) -> int:
    preset_key = key.replace("video_i2v_", "")
    fallback = int(preset.get(preset_key, default))
    raw_value = settings.get(key)
    try:
        value = int(raw_value) if raw_value not in (None, "") else fallback
    except (TypeError, ValueError):
        value = fallback
    return max(min_value, min(max_value, value))


def preset_bounded_float_setting(settings: dict[str, Any], preset: dict[str, Any], key: str, default: float, *, min_value: float, max_value: float) -> float:
    preset_key = key.replace("video_i2v_", "")
    fallback = float(preset.get(preset_key, default))
    raw_value = settings.get(key)
    try:
        value = float(raw_value) if raw_value not in (None, "") else fallback
    except (TypeError, ValueError):
        value = fallback
    return max(min_value, min(max_value, value))


def is_transient_xai_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout, urllib.error.URLError)):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc).lower()
        if any(token in message for token in ("timed out", "timeout", "temporarily unavailable", "connection reset", "remote end closed", "service unavailable")):
            return True
        match = re.search(r"http\s+(\d{3})", message, flags=re.IGNORECASE)
        if match and int(match.group(1)) in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True
    return False
