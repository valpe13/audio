import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

try:
    from studio_json_helpers import bounded_int_setting, extract_json_value, is_transient_xai_error, resolve_xai_text_model as resolve_xai_text_model_base
    from studio_text import (
        apply_ai_stress_to_chunk,
        compact_stress_chunks,
        compact_stress_validation_text,
        ensure_chunk_stress_fields,
        normalize_ai_stress_items,
        split_chunks_for_stress_batches as calculate_stress_batches,
        stress_response_missing_ids,
        stress_response_token_budget as calculate_stress_response_token_budget,
    )
except ImportError:  # pragma: no cover - package-style imports
    from .studio_json_helpers import bounded_int_setting, extract_json_value, is_transient_xai_error, resolve_xai_text_model as resolve_xai_text_model_base
    from .studio_text import (
        apply_ai_stress_to_chunk,
        compact_stress_chunks,
        compact_stress_validation_text,
        ensure_chunk_stress_fields,
        normalize_ai_stress_items,
        split_chunks_for_stress_batches as calculate_stress_batches,
        stress_response_missing_ids,
        stress_response_token_budget as calculate_stress_response_token_budget,
    )


XAI_STRESS_ATTEMPTS = 3
XAI_STRESS_TIMEOUT_SECONDS = 90
XAI_STRESS_MAX_CHUNKS_PER_BATCH = 2
XAI_STRESS_MAX_REQUEST_CHARS = 2500
XAI_STRESS_MAX_TOKENS = 6000
XAI_STRESS_LONG_CHUNK_CHARS = 1200


@dataclass
class AiStressStats:
    total: int = 0
    marked: int = 0
    unchanged: int = 0
    rejected: int = 0
    retried_individually: int = 0
    failed_batches: int = 0
    errors: int = 0


def split_chunks_for_stress_batches(chunks: list[dict[str, Any]], max_chunks: int = XAI_STRESS_MAX_CHUNKS_PER_BATCH, max_chars: int = XAI_STRESS_MAX_REQUEST_CHARS) -> list[list[dict[str, Any]]]:
    return calculate_stress_batches(
        chunks,
        max_chunks=max_chunks,
        max_chars=max_chars,
        long_chunk_chars=XAI_STRESS_LONG_CHUNK_CHARS,
    )


def stress_response_token_budget(chunks: list[dict[str, Any]]) -> int:
    return calculate_stress_response_token_budget(chunks, max_tokens=XAI_STRESS_MAX_TOKENS)


def call_xai_stress_batch(chunks: list[dict[str, Any]], api_key: str, *, model: str = "") -> dict[str, str]:
    api_key = (api_key or "").strip()
    if not api_key:
        raise RuntimeError("xAI API key is not configured")
    base_url = (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
    selected_model = resolve_xai_text_model_base(model)
    payload = {
        "task": "Add Russian stress marks for TTS chunk synthesis.",
        "output_schema": [{"id": "same id", "stressed_text": "same text with combining acute marks U+0301 after stressed Russian vowels where possible"}],
        "rules": [
            "Return strictly valid JSON array only, with one object per input chunk and keys id and stressed_text only. No commentary and no root object.",
            "Preserve every character, word order, punctuation, capitalization, spacing meaning, numbers, and paragraph boundaries; do not rewrite, translate, normalize ё, or correct style.",
            "Only add Russian stress marks as combining acute accent U+0301 after stressed vowels, for example за́мок, холме́, мука́, or столе́.",
            "Add exactly one stress mark to every Russian word that contains at least one Russian vowel when the stress is known, obvious, dictionary-standard, or can be reasonably inferred from normal Russian pronunciation.",
            "Do not mark only unusual or uncertain words: common short words, function words, inflected forms, and repeated words must also receive stress marks when they contain Russian vowels.",
            "Do not add stress to abbreviations, numbers, symbols, foreign words, vowel-less words, or words where a stress mark would be inappropriate.",
            "If the correct stress for a word is genuinely unknown or uncertain, leave that word unchanged rather than guessing.",
            "Return every provided id exactly once and do not invent ids.",
        ],
        "chunks": compact_stress_chunks(chunks),
    }
    request_body = {
        "model": selected_model,
        "temperature": 0.0,
        "max_tokens": stress_response_token_budget(chunks),
        "messages": [
            {"role": "system", "content": "Return a JSON array only. Add Russian combining acute stress marks for TTS. Never rewrite text."},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=XAI_STRESS_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"xAI stress request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"xAI stress request failed: {exc.reason}") from exc
    completion = json.loads(response_body)
    content = completion.get("choices", [{}])[0].get("message", {}).get("content", "")
    ai_value = extract_json_value(content)
    return normalize_ai_stress_items(ai_value, chunks)


def call_xai_stress_batch_with_retry(chunks: list[dict[str, Any]], api_key: str, *, model: str = "", attempts: int | None = None, retry_base_delay_seconds: float = 1.5) -> dict[str, str]:
    max_attempts = max(1, int(attempts if attempts is not None else XAI_STRESS_ATTEMPTS))
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return call_xai_stress_batch(chunks, api_key, model=model)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts or not is_transient_xai_error(exc):
                break
            time.sleep(retry_base_delay_seconds * (2 ** (attempt - 1)))
    raise RuntimeError(f"Grok stress marking failed after {max_attempts} attempts: {last_exc}") from last_exc


def apply_ai_stress_result_to_chunk(chunk: dict[str, Any], stressed_by_id: dict[str, str], stats: AiStressStats) -> bool:
    chunk_id = str(chunk.get("id") or "")
    original = str(chunk.get("text") or "")
    stressed = stressed_by_id.get(chunk_id)
    if not stressed:
        stats.rejected += 1
        return False
    if compact_stress_validation_text(stressed) != compact_stress_validation_text(original):
        stats.rejected += 1
        return False
    if apply_ai_stress_to_chunk(chunk, stressed, source="grok"):
        stats.marked += 1
        return True
    stats.unchanged += 1
    return False


def retry_missing_stress_chunks_individually(
    missing_chunks: list[dict[str, Any]],
    api_key: str,
    *,
    model: str,
    attempts: int,
    stats: AiStressStats,
    errors: list[str],
    retry_base_delay_seconds: float = 1.5,
) -> None:
    for single in missing_chunks:
        stats.retried_individually += 1
        try:
            stressed_by_id = call_xai_stress_batch_with_retry([single], api_key, model=model, attempts=attempts, retry_base_delay_seconds=retry_base_delay_seconds)
        except Exception as single_exc:
            stats.errors += 1
            errors.append(str(single_exc))
            stats.rejected += 1
            continue
        apply_ai_stress_result_to_chunk(single, stressed_by_id, stats)


def add_ai_stress_to_chunks(
    project: dict[str, Any],
    chunks: list[dict[str, Any]],
    *,
    default_settings: dict[str, Any],
    resolve_xai_api_key: Callable[[dict[str, Any], str], str],
    safe_project_id: Callable[[str], str],
    active_project_id: Callable[[], str],
    retry_base_delay_seconds: float = 1.5,
) -> tuple[int, str]:
    ensure_chunk_stress_fields(chunks)
    settings = project.get("settings", {}) if isinstance(project.get("settings"), dict) else {}
    if not bool(settings.get("ai_add_russian_stress_marks", default_settings["ai_add_russian_stress_marks"])):
        return 0, "disabled"
    stress_model = resolve_xai_text_model_base(str(settings.get("ai_stress_model") or ""))
    api_key = resolve_xai_api_key(project, safe_project_id(str(project.get("id") or active_project_id())))
    if not api_key:
        return 0, f"Grok/xAI key not configured; kept original chunks (model would be {stress_model})"
    batch_chunks = bounded_int_setting(settings, "ai_stress_batch_chunks", int(default_settings["ai_stress_batch_chunks"]), min_value=1, max_value=12)
    max_request_chars = bounded_int_setting(settings, "ai_stress_max_request_chars", int(default_settings["ai_stress_max_request_chars"]), min_value=500, max_value=20000)
    configured_retries = bounded_int_setting(settings, "ai_stress_retries", int(default_settings["ai_stress_retries"]), min_value=0, max_value=5)
    attempts = max(1, configured_retries + 1)
    stats = AiStressStats(total=sum(1 for chunk in chunks if isinstance(chunk, dict) and str(chunk.get("id") or "")))
    errors: list[str] = []
    for batch in split_chunks_for_stress_batches(chunks, max_chunks=batch_chunks, max_chars=max_request_chars):
        try:
            stressed_by_id = call_xai_stress_batch_with_retry(batch, api_key, model=stress_model, attempts=attempts, retry_base_delay_seconds=retry_base_delay_seconds)
        except Exception as exc:
            stats.failed_batches += 1
            stats.errors += 1
            errors.append(str(exc))
            retry_missing_stress_chunks_individually(batch, api_key, model=stress_model, attempts=attempts, stats=stats, errors=errors, retry_base_delay_seconds=retry_base_delay_seconds)
            continue
        missing_ids = set(stress_response_missing_ids(stressed_by_id, batch))
        for chunk in batch:
            if str(chunk.get("id") or "") not in missing_ids:
                apply_ai_stress_result_to_chunk(chunk, stressed_by_id, stats)
        missing_chunks = [chunk for chunk in batch if str(chunk.get("id") or "") in missing_ids]
        if missing_chunks:
            retry_missing_stress_chunks_individually(missing_chunks, api_key, model=stress_model, attempts=attempts, stats=stats, errors=errors, retry_base_delay_seconds=retry_base_delay_seconds)
    unresolved = max(0, stats.total - stats.marked - stats.unchanged - stats.rejected)
    if unresolved:
        stats.rejected += unresolved
    note = (
        f"Grok stress: {stats.marked}/{stats.total} marked, {stats.unchanged} unchanged/skipped, "
        f"{stats.rejected} rejected, {stats.retried_individually} retried individually using {stress_model}"
    )
    if errors:
        note += f"; fallback kept originals for failed items ({stats.errors} error(s), {stats.failed_batches} failed batch(es))"
    return stats.marked, note


def add_ai_stress_to_chunks_safe(
    project: dict[str, Any],
    chunks: list[dict[str, Any]],
    *,
    default_settings: dict[str, Any],
    resolve_xai_api_key: Callable[[dict[str, Any], str], str],
    safe_project_id: Callable[[str], str],
    active_project_id: Callable[[], str],
    truncate_text: Callable[[Any, int], str],
    logger: logging.Logger,
    retry_base_delay_seconds: float = 1.5,
) -> tuple[int, str]:
    try:
        return add_ai_stress_to_chunks(
            project,
            chunks,
            default_settings=default_settings,
            resolve_xai_api_key=resolve_xai_api_key,
            safe_project_id=safe_project_id,
            active_project_id=active_project_id,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
    except Exception as exc:
        logger.warning("Optional Grok stress marking failed during chunk split; keeping original chunks: %s: %s", type(exc).__name__, exc)
        ensure_chunk_stress_fields(chunks, source="original")
        detail = truncate_text(str(exc), 220)
        return 0, f"Grok stress marking skipped after non-fatal error: {type(exc).__name__}: {detail}; kept original chunks"
