from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CYRILLIC_WORD_BOUNDARY_LEFT = r"(?<![А-Яа-яЁё])"
CYRILLIC_WORD_BOUNDARY_RIGHT = r"(?![А-Яа-яЁё])"
COMBINING_ACUTE = "\u0301"
VOWELS_RU = "аеёиоуыэюяАЕЁИОУЫЭЮЯ"


def load_pronunciation_dictionary(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Pronunciation dictionary must be a JSON object: {path}")
    result: dict[str, str] = {}
    for key, value in data.items():
        source = str(key).strip()
        replacement = str(value).strip()
        if source and replacement:
            result[source] = replacement
    return result


def plus_stress_to_acute(text: str) -> str:
    """Convert Russian stress hints from `молок+о` or `мол+око` to `молоко́`/`моло́ко`.

    A plus is consumed only when it is immediately before or after a Russian vowel.
    Other plus signs are left untouched so mathematical text is not rewritten.
    """
    text = re.sub(rf"([{re.escape(VOWELS_RU)}])\+", rf"\1{COMBINING_ACUTE}", text)
    text = re.sub(rf"\+([{re.escape(VOWELS_RU)}])", rf"\1{COMBINING_ACUTE}", text)
    return text


def acute_to_plus_stress(text: str) -> str:
    return re.sub(rf"([{re.escape(VOWELS_RU)}]){COMBINING_ACUTE}", r"+\1", text)


def apply_pronunciation_dictionary(text: str, dictionary: dict[str, str]) -> str:
    if not dictionary:
        return text
    result = text
    for source in sorted(dictionary, key=len, reverse=True):
        replacement = dictionary[source]
        if re.search(r"[А-Яа-яЁё]", source):
            pattern = f"{CYRILLIC_WORD_BOUNDARY_LEFT}{re.escape(source)}{CYRILLIC_WORD_BOUNDARY_RIGHT}"
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        else:
            result = result.replace(source, replacement)
    return result


def preprocess_tts_text(
    text: str,
    dictionary: dict[str, str] | None = None,
    *,
    stress_mark_style: str = "acute",
    strip_unsupported_stress: bool = False,
) -> str:
    # Dictionary first lets manual inline stress (`мук+а`) override a broad
    # dictionary entry (`мука -> му́ка`) instead of producing two stress marks.
    processed = apply_pronunciation_dictionary(str(text or ""), dictionary or {})
    processed = plus_stress_to_acute(processed)
    style = (stress_mark_style or "acute").strip().lower()
    if strip_unsupported_stress or style == "plain":
        processed = processed.replace(COMBINING_ACUTE, "")
    elif style == "plus":
        processed = acute_to_plus_stress(processed)
    return processed


def preview_preprocessing(text: str, dictionary_path: Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    dictionary = load_pronunciation_dictionary(dictionary_path)
    processed = preprocess_tts_text(
        text,
        dictionary,
        stress_mark_style=str(options.get("stress_mark_style") or "acute"),
        strip_unsupported_stress=bool(options.get("strip_unsupported_stress", False)),
    )
    return {
        "input": text,
        "output": processed,
        "dictionary_path": str(dictionary_path),
        "dictionary_entries": len(dictionary),
        "stress_mark_style": str(options.get("stress_mark_style") or "acute"),
    }
