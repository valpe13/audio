import json
import math
import re
import unicodedata
from typing import Any


def compact_stress_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": str(chunk.get("id") or ""), "order": idx, "text": str(chunk.get("text") or "")}
        for idx, chunk in enumerate(chunks)
        if str(chunk.get("id") or "")
    ]


def stress_chunk_request_chars(chunk: dict[str, Any]) -> int:
    return len(json.dumps({"id": str(chunk.get("id") or ""), "text": str(chunk.get("text") or "")}, ensure_ascii=False)) + 80


def stress_response_token_budget(chunks: list[dict[str, Any]], *, max_tokens: int) -> int:
    text_chars = sum(len(str(chunk.get("text") or "")) for chunk in chunks if isinstance(chunk, dict))
    return max(1200, min(max_tokens, int(text_chars * 1.8) + 1200))


def split_chunks_for_stress_batches(
    chunks: list[dict[str, Any]],
    *,
    max_chunks: int,
    max_chars: int,
    long_chunk_chars: int,
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    max_chunks = max(1, int(max_chunks or 1))
    max_chars = max(500, int(max_chars or 500))
    long_chunk_chars = max(1, int(long_chunk_chars or 1))
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_chars = stress_chunk_request_chars(chunk)
        if current and (chunk_chars >= long_chunk_chars or len(current) >= max_chunks or current_chars + chunk_chars > max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(chunk)
        current_chars += chunk_chars
        if chunk_chars >= long_chunk_chars:
            batches.append(current)
            current = []
            current_chars = 0
    if current:
        batches.append(current)
    return batches


def stress_response_missing_ids(stressed_by_id: dict[str, str], chunks: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_id = str(chunk.get("id") or "")
        if chunk_id and chunk_id not in stressed_by_id:
            missing.append(chunk_id)
    return missing


def clean_text(text: str) -> str:
    text = text.replace("ё", "ё")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("--", " — ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_tts_backend(settings: dict[str, Any] | None, *, default_backend: str = "xtts") -> str:
    backend = str((settings or {}).get("tts_backend") or default_backend).strip().lower()
    return backend if backend in {"xtts", "silero"} else "xtts"


def chunk_tts_source_text(chunk: dict[str, Any]) -> str:
    return str(chunk.get("tts_text") or chunk.get("stressed_text") or chunk.get("text") or "")


MOJIBAKE_SUSPICIOUS_CHARS = set("\u0402\u0403\u0405\u0406\u0408\u0409\u040a\u040b\u040c\u040e\u040f\u0452\u0453\u0455\u0456\u0458\u0459\u045a\u045b\u045c\u045e\u045f\u0490\u0491\u201a\u201e\u2020\u2021\u2026\u2030\u2039\u203a\u20ac\u2116\ufffd")
MOJIBAKE_CP1251_ENCODE_FALLBACK = {
    "\u02dc": b"\x98",
}
RUSSIAN_COMMON_WORD_RE = re.compile(
    r"\b(представьте|себе|очень|воздух|становится|прошлом|когда|которые|можно|люди|время|земли|свет|тише|были)\b",
    flags=re.IGNORECASE,
)


def mojibake_score(text: str) -> int:
    if not text:
        return 0
    suspicious = sum(1 for char in text if char in MOJIBAKE_SUSPICIOUS_CHARS)
    suspicious += len(re.findall(r"[РС][\u00a0-\u00ff\u0400-\u040f\u0450-\u045f\u0490-\u0491\u2010-\u203a\u20ac\u2116]", text))
    suspicious += len(re.findall(r"[ÐÑ][\u0080-\u00ff]", text))
    return suspicious


def readable_russian_score(text: str) -> int:
    if not text:
        return 0
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", text))
    common_words = len(RUSSIAN_COMMON_WORD_RE.findall(text))
    return cyrillic + common_words * 25 - mojibake_score(text) * 3


def encode_mojibake_cp1251(text: str) -> bytes:
    parts: list[bytes] = []
    for char in text:
        try:
            parts.append(char.encode("cp1251"))
        except UnicodeEncodeError:
            fallback = MOJIBAKE_CP1251_ENCODE_FALLBACK.get(char)
            if fallback is None:
                raise
            parts.append(fallback)
    return b"".join(parts)


def repair_mojibake_text(text: str) -> tuple[str, bool]:
    """Conservatively repair UTF-8 Cyrillic text decoded through a single-byte codepage."""
    if not isinstance(text, str) or not text:
        return text, False
    before_mojibake = mojibake_score(text)
    if before_mojibake < max(6, min(80, len(text) // 200)):
        return text, False

    before_readable = readable_russian_score(text)
    best = text
    best_codec = ""
    best_mojibake = before_mojibake
    best_readable = before_readable
    for codec in ("cp1251", "cp1252", "latin1"):
        try:
            raw = encode_mojibake_cp1251(text) if codec == "cp1251" else text.encode(codec)
            candidate = raw.decode("utf-8")
        except UnicodeError:
            continue
        candidate_mojibake = mojibake_score(candidate)
        candidate_readable = readable_russian_score(candidate)
        if candidate_mojibake < best_mojibake and candidate_readable > best_readable:
            best = candidate
            best_codec = codec
            best_mojibake = candidate_mojibake
            best_readable = candidate_readable

    if not best_codec:
        return text, False
    if best_mojibake > max(2, before_mojibake // 10):
        return text, False
    if best_readable < before_readable + max(25, before_mojibake * 2):
        return text, False
    return best, True


def repair_project_mojibake_fields(project: dict[str, Any]) -> int:
    repaired = 0
    full_text, changed = repair_mojibake_text(str(project.get("full_text") or ""))
    if changed:
        project["full_text"] = full_text
        repaired += 1
    for chunk in project.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        text, changed = repair_mojibake_text(str(chunk.get("text") or ""))
        if changed:
            chunk["text"] = text
            repaired += 1
    return repaired


def strip_stress_marks_for_validation(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text or ""))
    return unicodedata.normalize("NFC", normalized.replace("\u0301", ""))


def compact_stress_validation_text(text: str) -> str:
    return re.sub(r"\s+", " ", strip_stress_marks_for_validation(text)).strip()


def normalize_ai_stress_items(raw_items: Any, chunks: list[dict[str, Any]]) -> dict[str, str]:
    if isinstance(raw_items, dict) and isinstance(raw_items.get("chunks"), list):
        raw_items = raw_items.get("chunks")
    if not isinstance(raw_items, list):
        raise ValueError("AI response field 'chunks' must be a list")
    original_by_id = {str(chunk.get("id") or ""): str(chunk.get("text") or "") for chunk in chunks if isinstance(chunk, dict)}
    normalized: dict[str, str] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("id") or "")
        if chunk_id not in original_by_id:
            continue
        stressed = unicodedata.normalize("NFC", str(item.get("stressed_text") or item.get("text") or "").strip())
        original = original_by_id[chunk_id]
        if not stressed:
            continue
        original_compact = compact_stress_validation_text(original)
        stressed_compact = compact_stress_validation_text(stressed)
        if stressed_compact != original_compact:
            # Do not accept rewrites; stress marks are allowed, content changes are not.
            continue
        normalized[chunk_id] = stressed
    return normalized


def apply_ai_stress_to_chunk(chunk: dict[str, Any], stressed: str, *, source: str = "grok") -> bool:
    if not isinstance(chunk, dict):
        return False
    original = str(chunk.get("text") or "")
    stressed_text = unicodedata.normalize("NFC", str(stressed or "").strip())
    if not original or not stressed_text or stressed_text == original:
        chunk.setdefault("tts_text", str(chunk.get("tts_text") or original))
        chunk.setdefault("stressed_text", str(chunk.get("stressed_text") or original))
        chunk.setdefault("stress_source", str(chunk.get("stress_source") or "original"))
        return False
    chunk["stressed_text"] = stressed_text
    chunk["tts_text"] = stressed_text
    chunk["stress_source"] = source
    return True


def ensure_chunk_stress_fields(chunks: list[dict[str, Any]], *, source: str = "original") -> None:
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        text = str(chunk.get("text") or "")
        chunk["text"] = text
        if chunk.get("stressed_text") in (None, ""):
            chunk["stressed_text"] = text
        if chunk.get("tts_text") in (None, ""):
            chunk["tts_text"] = str(chunk.get("stressed_text") or text)
        chunk["stress_source"] = str(chunk.get("stress_source") or source)


def sanitize_split_chunk_for_response(chunk: dict[str, Any]) -> None:
    """Keep split chunk data JSON-safe after optional post-processing."""
    if not isinstance(chunk, dict):
        return
    for key in ("id", "text", "boundary_type", "audio_path", "selected_version_id", "stressed_text", "tts_text", "stress_source"):
        chunk[key] = str(chunk.get(key) or "")
    try:
        chunk["order"] = int(chunk.get("order") or 0)
    except (TypeError, ValueError):
        chunk["order"] = 0
    for key in ("pause_after", "duration_sec"):
        try:
            value = float(chunk.get(key) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if not math.isfinite(value):
            value = 0.0
        chunk[key] = value
    if not isinstance(chunk.get("versions"), list):
        chunk["versions"] = []
    if chunk.get("generated_at") is not None:
        chunk["generated_at"] = str(chunk.get("generated_at") or "")


def split_paragraph_blocks(text: str) -> list[dict[str, Any]]:
    cleaned = re.sub(r"\r\n?", "\n", text).strip()
    if not cleaned:
        return []
    pieces = re.split(r"(\n\s*\n+)", cleaned)
    blocks: list[dict[str, Any]] = []
    for idx in range(0, len(pieces), 2):
        para = pieces[idx].strip()
        if not para:
            continue
        separator = pieces[idx + 1] if idx + 1 < len(pieces) else ""
        blank_lines = separator.count("\n")
        boundary_type = "section" if blank_lines >= 3 else ("paragraph" if separator else "sentence")
        blocks.append({"text": para, "boundary_type": boundary_type})
    return blocks


def looks_like_section_heading(paragraph: str) -> bool:
    compact = re.sub(r"\s+", " ", paragraph).strip()
    if not compact or len(compact) > 90:
        return False
    if re.match(r"^(#{1,6}\s+|(?:глава|часть|раздел|section|chapter)\b|\d{1,3}[.)]\s+)", compact, flags=re.IGNORECASE):
        return True
    return not re.search(r"[.!?…。！？]$", compact) and len(compact.split()) <= 9


def split_paragraph_sentences(paragraph: str) -> list[str]:
    normalized = re.sub(r"[ \t]*\n[ \t]*", " ", paragraph).strip()
    # Python's `re` requires look-behind assertions to be fixed width.  The
    # previous splitter used `(?<=[.!?…。！？][\"'»”’)]*)`, which is variable
    # width because of `*` inside the look-behind and fails at runtime.  Match
    # the whole boundary instead and split after the matched whitespace so the
    # sentence-ending punctuation and optional closing quotes stay with the
    # preceding sentence.
    parts: list[str] = []
    start = 0
    for match in re.finditer(r"[.!?…。！？][\"'»”’)]*\s+(?=[А-ЯЁA-Z0-9\"'«“(])", normalized):
        parts.append(normalized[start:match.end()].strip())
        start = match.end()
    parts.append(normalized[start:].strip())
    return [clean_text(part) for part in parts if clean_text(part)]


def split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    clause_parts = [part.strip() for part in re.split(r"(?<=[,;:—-])\s+", sentence) if part.strip()]
    current = ""
    for part in clause_parts:
        candidate = f"{current} {part}".strip()
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = part
        else:
            current = candidate
    if current:
        pieces.append(current)

    final: list[str] = []
    for piece in pieces or [sentence]:
        if len(piece) <= max_chars:
            final.append(piece)
            continue
        words = piece.split()
        word_piece = ""
        for word in words:
            candidate = f"{word_piece} {word}".strip()
            if word_piece and len(candidate) > max_chars:
                final.append(word_piece)
                word_piece = word
            else:
                word_piece = candidate
        if word_piece:
            final.append(word_piece)
    return [clean_text(piece) for piece in final if clean_text(piece)]


def split_text_into_chunks(text: str, max_chars: int) -> list[dict[str, Any]]:
    blocks = split_paragraph_blocks(text)
    units: list[dict[str, str]] = []
    for idx, block in enumerate(blocks):
        para = block["text"]
        boundary_type = str(block.get("boundary_type") or "sentence")
        if idx + 1 < len(blocks) and looks_like_section_heading(para):
            boundary_type = "section"
        sentences = split_paragraph_sentences(para)
        for sent_idx, sentence in enumerate(sentences):
            units.append({
                "text": sentence,
                "boundary_type": boundary_type if sent_idx == len(sentences) - 1 else "sentence",
            })

    chunks: list[dict[str, Any]] = []
    current = ""
    current_boundary = "sentence"

    def emit_current() -> None:
        nonlocal current, current_boundary
        if current:
            chunks.append({"text": current, "boundary_type": current_boundary})
            current = ""
            current_boundary = "sentence"

    for unit in units:
        sentence = unit["text"]
        boundary_type = unit["boundary_type"]
        if len(sentence) > max_chars:
            emit_current()
            long_pieces = split_long_sentence(sentence, max_chars)
            for piece_idx, piece in enumerate(long_pieces):
                piece_boundary = boundary_type if piece_idx == len(long_pieces) - 1 else "sentence"
                chunks.append({"text": piece, "boundary_type": piece_boundary})
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            emit_current()
            current = sentence
            current_boundary = boundary_type
        else:
            current = candidate
            current_boundary = boundary_type
    emit_current()
    return chunks
