import math
import re
from typing import Any, Iterable

try:
    from studio_prompt_helpers import truncate_text
except ImportError:  # pragma: no cover - package-style imports
    from .studio_prompt_helpers import truncate_text


DEFAULT_SUBTITLE_SETTINGS = {
    "position": "bottom",
    "font_family": "Arial",
    "font_size": 100,
    "color": "#ffffff",
    "background": "#000000",
    "background_opacity": 0.0,
    "outline": 2,
    "max_words": 5,
    "word_offset_sec": 0.0,
}
SUBTITLE_PREVIEW_REFERENCE_HEIGHT_PX = 1920
SUBTITLE_PREVIEW_REFERENCE_WIDTH_PX = 1080


def normalize_subtitle_defaults(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULT_SUBTITLE_SETTINGS)
    if str(data.get("position") or "").lower() in {"top", "center", "bottom"}:
        out["position"] = str(data.get("position")).lower()
    for key in ("font_family", "color", "background"):
        if data.get(key) is not None:
            out[key] = truncate_text(data.get(key), 120)
    for key, min_value, max_value in (("font_size", 8, 160), ("background_opacity", 0, 1), ("outline", 0, 12), ("max_words", 1, 40), ("word_offset_sec", -5, 5)):
        try:
            out[key] = max(min_value, min(max_value, float(data.get(key, out[key]))))
        except (TypeError, ValueError):
            pass
    out["max_words"] = int(round(float(out.get("max_words", 7))))
    return out


def normalize_subtitle_blocks(raw_blocks: Any, group: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    duration = 36000.0
    if isinstance(group, dict):
        try:
            duration = max(0.05, float(group.get("duration") or group.get("duration_sec") or duration))
        except (TypeError, ValueError):
            pass
    defaults = normalize_subtitle_defaults(group.get("subtitle_defaults") if isinstance(group, dict) else None)
    blocks: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_blocks if isinstance(raw_blocks, list) else []):
        if not isinstance(raw, dict):
            continue
        start = max(0.0, min(duration, float(raw.get("start_offset_sec") if raw.get("start_offset_sec") is not None else raw.get("start") or 0.0)))
        block_duration = max(0.05, min(duration - start if duration > start else duration, float(raw.get("duration_sec") if raw.get("duration_sec") is not None else raw.get("duration") or max(0.05, duration - start))))
        block_defaults = normalize_subtitle_defaults({**defaults, **raw})
        blocks.append({
            "id": str(raw.get("id") or f"subtitle_{idx + 1:03d}"),
            "enabled": bool(raw.get("enabled", True)),
            "text": truncate_text(raw.get("text"), 4000),
            "start_offset_sec": round(start, 3),
            "duration_sec": round(block_duration, 3),
            "position": block_defaults["position"],
            "font_family": block_defaults["font_family"],
            "font_size": block_defaults["font_size"],
            "color": block_defaults["color"],
            "background": block_defaults["background"],
            "background_opacity": block_defaults["background_opacity"],
            "outline": block_defaults["outline"],
            "max_words": block_defaults["max_words"],
            "word_offset_sec": block_defaults["word_offset_sec"],
            "order": int(raw.get("order") if str(raw.get("order", "")).isdigit() else idx),
        })
    return blocks


def build_normalized_video_group_subtitle_field_args(raw_group: dict[str, Any], subtitle_group: dict[str, Any]) -> dict[str, Any]:
    """Return normalized subtitle keyword arguments for a normalized video-group item."""
    subtitle_defaults = subtitle_group.get("subtitle_defaults")
    return {
        "subtitle_defaults": dict(subtitle_defaults) if isinstance(subtitle_defaults, dict) else None,
        "subtitle_blocks": normalize_subtitle_blocks(raw_group.get("subtitle_blocks"), subtitle_group),
    }


def ass_escape(text: Any) -> str:
    linebreak_token = "\uE000ASS_LINEBREAK\uE000"
    value = str(text or "").replace(r"\N", linebreak_token).replace(r"\n", linebreak_token)
    value = value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", r"\N")
    return value.replace(linebreak_token, r"\N")


def subtitle_export_layout(width: int, height: int, settings: dict[str, Any]) -> dict[str, float | int]:
    normalized = normalize_subtitle_defaults(settings)
    preview_font_size = max(8.0, min(160.0, float(normalized.get("font_size") or DEFAULT_SUBTITLE_SETTINGS["font_size"])))
    is_landscape = int(width or 0) > int(height or 0)
    reference_height = SUBTITLE_PREVIEW_REFERENCE_WIDTH_PX if is_landscape else SUBTITLE_PREVIEW_REFERENCE_HEIGHT_PX
    reference_width = SUBTITLE_PREVIEW_REFERENCE_HEIGHT_PX if is_landscape else SUBTITLE_PREVIEW_REFERENCE_WIDTH_PX
    preview_to_video_scale = max(0.1, float(height or reference_height) / reference_height)
    font_size = max(8, min(480, int(round(preview_font_size * preview_to_video_scale))))
    outline = max(0, min(48, int(round(float(normalized.get("outline") or 2) * preview_to_video_scale))))
    base_margin_h = max(8, int(round(reference_width * 0.05 * preview_to_video_scale)))
    base_margin_v = max(8, int(round(reference_height * 0.05 * preview_to_video_scale)))
    edge_gutter = max(8, int(round((preview_font_size * 0.18 + float(normalized.get("outline") or 2) * 2.0) * preview_to_video_scale)))
    frame_width = max(1, int(width or reference_width))
    frame_height = max(1, int(height or reference_height))
    margin_h = max(8, min(frame_width // 3, base_margin_h + edge_gutter))
    margin_v = max(8, min(frame_height // 3, base_margin_v + edge_gutter))
    return {
        "font_size": font_size,
        "outline": outline,
        "margin_h": margin_h,
        "margin_v": margin_v,
        "preview_to_video_scale": preview_to_video_scale,
        "reference_width": reference_width,
        "reference_height": reference_height,
    }


def estimate_ass_word_width(word: str, font_size: float) -> float:
    width = 0.0
    for char in str(word or ""):
        if char.isspace():
            width += font_size * 0.32
        elif re.match(r"[ilI1.,:;!|'`’]", char):
            width += font_size * 0.28
        elif re.match(r"[mwMWШЩЮЖФ@%#]", char):
            width += font_size * 0.82
        elif re.match(r"[А-Яа-яЁё]", char):
            width += font_size * 0.66
        elif re.match(r"[A-Za-z0-9]", char):
            width += font_size * 0.56
        else:
            width += font_size * 0.62
    return width


def wrap_ass_subtitle_text(text: Any, width: int, height: int, settings: dict[str, Any]) -> str:
    r"""Wrap ASS dialogue text with explicit \N line breaks to mirror preview CSS wrapping.

    Browser preview uses a 5% safe-area box plus inline text padding and
    `overflow-wrap:anywhere`.  libass auto-wrap is renderer-dependent and can
    leave progressive 5-word captions as one over-wide line, so export inserts
    deterministic breaks based on estimated rendered width.
    """
    plain = re.sub(r"\s+", " ", str(text or "")).strip()
    if not plain:
        return ""
    layout = subtitle_export_layout(width, height, settings)
    font_size = float(layout["font_size"])
    frame_width = max(1, int(width or layout["reference_width"]))
    css_safe_width = frame_width * 0.90
    text_padding = font_size * 0.90
    available_width = max(font_size * 1.5, css_safe_width - text_padding)
    # ASS style margins include an extra rasterization gutter beyond preview's
    # 5% safe area, so keep explicit wrapping inside the stricter of both boxes.
    available_width = min(available_width, max(font_size * 1.5, frame_width - (2 * float(layout["margin_h"])) - text_padding))
    space_width = estimate_ass_word_width(" ", font_size)
    lines: list[str] = []
    current_words: list[str] = []
    current_width = 0.0
    for word in plain.split(" "):
        word_width = estimate_ass_word_width(word, font_size)
        candidate_width = word_width if not current_words else current_width + space_width + word_width
        if current_words and candidate_width > available_width:
            lines.append(" ".join(current_words))
            current_words = [word]
            current_width = word_width
        else:
            current_words.append(word)
            current_width = candidate_width
    if current_words:
        lines.append(" ".join(current_words))
    return r"\N".join(lines)


def ass_time(seconds: float) -> str:
    value = max(0.0, float(seconds or 0.0))
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = int(value % 60)
    centis = int(round((value - int(value)) * 100))
    if centis >= 100:
        secs += 1
        centis = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def build_ass_dialogue_line(event: dict[str, Any], width: int, height: int, style_name: str) -> str:
    """Return one formatted ASS dialogue line for a normalized subtitle event."""
    position = str(event.get("position") or "bottom")
    align = 8 if position == "top" else 5 if position == "center" else 2
    wrapped_text = wrap_ass_subtitle_text(event.get("text"), width, height, event)
    text = ass_escape(wrapped_text)
    return f"Dialogue: 0,{ass_time(float(event.get('start') or 0.0))},{ass_time(float(event.get('end') or 0.0))},{style_name},,0,0,0,,{{\\an{align}}}{text}"


def build_ass_dialogue_lines(styled_events: Iterable[tuple[dict[str, Any], str]], width: int, height: int) -> list[str]:
    """Return ASS dialogue lines from caller-finalized events and style names."""
    return [build_ass_dialogue_line(event, width, height, style_name) for event, style_name in styled_events]


def format_ffmpeg_subtitles_filter_arg(path: Any) -> str:
    """Return an FFmpeg subtitles filter argument for a caller-selected subtitle path."""
    value = str(path).replace("\\", "/").replace("'", r"\'").replace(":", r"\:")
    return f"subtitles='{value}'"


def ass_style_key(settings: dict[str, Any]) -> tuple[Any, ...]:
    """Return the ASS style identity key for normalized subtitle style settings."""
    normalized = normalize_subtitle_defaults(settings)
    return (
        normalized.get("font_family"),
        normalized.get("font_size"),
        normalized.get("color"),
        normalized.get("background"),
        normalized.get("background_opacity"),
        normalized.get("outline"),
    )


def ass_color(hex_color: Any, alpha: int = 0) -> str:
    value = re.sub(r"[^0-9A-Fa-f]", "", str(hex_color or "ffffff"))
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    value = value.ljust(6, "0")[:6]
    rr, gg, bb = value[0:2], value[2:4], value[4:6]
    return f"&H{max(0, min(255, int(alpha))):02X}{bb}{gg}{rr}"


def progressive_subtitle_text(block: dict[str, Any], time_sec: float) -> str:
    if not isinstance(block, dict) or block.get("enabled") is False:
        return ""
    text = re.sub(r"\s+", " ", str(block.get("text") or "")).strip()
    if not text:
        return ""
    words = [word for word in text.split(" ") if word]
    if not words:
        return ""
    try:
        start = float(block.get("start_offset_sec") or 0.0)
    except (TypeError, ValueError):
        start = 0.0
    try:
        duration = max(0.05, float(block.get("duration_sec") or 0.05))
    except (TypeError, ValueError):
        duration = 0.05
    try:
        offset = max(-5.0, min(5.0, float(block.get("word_offset_sec") or 0.0)))
    except (TypeError, ValueError):
        offset = 0.0
    adjusted_time = float(time_sec or 0.0) - start + offset
    if adjusted_time < 0:
        return ""
    word_duration = duration / max(1, len(words))
    visible_count = int(math.floor(adjusted_time / max(0.001, word_duration))) + 1
    visible_count = max(0, min(len(words), visible_count))
    if visible_count <= 0:
        return ""
    try:
        max_words = int(round(max(1, min(40, float(block.get("max_words") or DEFAULT_SUBTITLE_SETTINGS["max_words"])))))
    except (TypeError, ValueError):
        max_words = int(DEFAULT_SUBTITLE_SETTINGS["max_words"])
    chunk_start = ((visible_count - 1) // max_words) * max_words
    return " ".join(words[chunk_start:visible_count])


def progressive_subtitle_segments(block: dict[str, Any], group_start: float) -> list[tuple[float, float, str]]:
    text = re.sub(r"\s+", " ", str(block.get("text") or "")).strip()
    words = [word for word in text.split(" ") if word]
    if not words:
        return []
    try:
        start_offset = float(block.get("start_offset_sec") or 0.0)
    except (TypeError, ValueError):
        start_offset = 0.0
    try:
        duration = max(0.05, float(block.get("duration_sec") or 0.05))
    except (TypeError, ValueError):
        duration = 0.05
    try:
        offset = max(-5.0, min(5.0, float(block.get("word_offset_sec") or 0.0)))
    except (TypeError, ValueError):
        offset = 0.0
    word_duration = duration / max(1, len(words))
    segments: list[tuple[float, float, str]] = []
    previous_text = ""
    block_global_start = float(group_start or 0.0) + start_offset
    block_global_end = block_global_start + duration
    for word_index in range(len(words)):
        local_start = start_offset + (word_index * word_duration) - offset
        next_local = start_offset + ((word_index + 1) * word_duration) - offset
        start = max(0.0, float(group_start or 0.0) + local_start)
        end = min(block_global_end, float(group_start or 0.0) + next_local)
        if end - start <= 0.001:
            continue
        current_text = progressive_subtitle_text(block, start - float(group_start or 0.0) + 0.0005)
        if not current_text:
            continue
        if segments and current_text == previous_text and abs(segments[-1][1] - start) <= 0.02:
            segments[-1] = (segments[-1][0], end, current_text)
        else:
            segments.append((start, end, current_text))
        previous_text = current_text
    return segments


def subtitle_event_model_for_block(block: dict[str, Any], group_start: float, group_end: float | None = None) -> list[dict[str, Any]]:
    """Shared export subtitle event model mirrored by GroupSubtitleTimeline.buildEvents().

    Event fields are deliberately JSON-like so preview and export can stay aligned:
    start/end are timeline seconds, text is the progressive visible text, and the
    remaining fields are the normalized visual style/position for the event.
    """
    if not isinstance(block, dict) or block.get("enabled") is False or not str(block.get("text") or "").strip():
        return []
    try:
        clamp_end = float(group_end) if group_end is not None else None
    except (TypeError, ValueError):
        clamp_end = None
    events: list[dict[str, Any]] = []
    for start, end, text_value in progressive_subtitle_segments(block, group_start):
        if clamp_end is not None:
            if start >= clamp_end - 0.001:
                continue
            end = min(end, clamp_end)
        if end - start <= 0.001:
            continue
        events.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text_value,
            "full_text": str(block.get("text") or ""),
            "position": block.get("position") or DEFAULT_SUBTITLE_SETTINGS["position"],
            "font_family": block.get("font_family") or DEFAULT_SUBTITLE_SETTINGS["font_family"],
            "font_size": block.get("font_size") or DEFAULT_SUBTITLE_SETTINGS["font_size"],
            "color": block.get("color") or DEFAULT_SUBTITLE_SETTINGS["color"],
            "background": block.get("background") or DEFAULT_SUBTITLE_SETTINGS["background"],
            "background_opacity": block.get("background_opacity", DEFAULT_SUBTITLE_SETTINGS["background_opacity"]),
            "outline": block.get("outline", DEFAULT_SUBTITLE_SETTINGS["outline"]),
            "max_words": block.get("max_words", DEFAULT_SUBTITLE_SETTINGS["max_words"]),
            "word_offset_sec": block.get("word_offset_sec", DEFAULT_SUBTITLE_SETTINGS["word_offset_sec"]),
            "block_id": block.get("id", ""),
        })
    return events


def clamp_subtitle_events_to_duration(raw_events: list[dict[str, Any]], duration: float) -> tuple[list[dict[str, Any]], int]:
    """Return subtitle events clamped to an export duration plus an outside-event count."""
    export_duration = max(0.0, float(duration or 0.0))
    clamped: list[dict[str, Any]] = []
    outside = 0
    for raw in raw_events:
        try:
            start = float(raw.get("start") or 0.0)
            end = float(raw.get("end") or 0.0)
        except (AttributeError, TypeError, ValueError):
            outside += 1
            continue
        if end <= 0.001 or start >= export_duration - 0.001:
            outside += 1
            continue
        event = dict(raw)
        event["start"] = round(max(0.0, start), 3)
        event["end"] = round(min(export_duration, end), 3)
        if float(event["end"]) - float(event["start"]) <= 0.001:
            outside += 1
            continue
        clamped.append(event)
    return clamped, outside


def build_subtitle_export_diagnostics(
    raw_events: list[dict[str, Any]],
    clamped_events: list[dict[str, Any]],
    outside_count: int,
    duration: float,
    export_scope: Any = "full",
    export_timeline_offset_sec: Any = 0.0,
) -> dict[str, Any]:
    """Return export subtitle timing diagnostics for a prepared event set."""
    return {
        "raw_event_count": len(raw_events),
        "events_outside_export_duration": outside_count,
        "event_time_min": round(min((float(event.get("start") or 0.0) for event in clamped_events), default=0.0), 3),
        "event_time_max": round(max((float(event.get("end") or 0.0) for event in clamped_events), default=0.0), 3),
        "export_duration_sec": round(max(0.0, float(duration or 0.0)), 3),
        "export_scope": export_scope or "full",
        "export_timeline_offset_sec": export_timeline_offset_sec,
    }


def ass_style_from_defaults(defaults: dict[str, Any], width: int, height: int, name: str = "Default") -> str:
    settings = normalize_subtitle_defaults(defaults)
    layout = subtitle_export_layout(width, height, settings)
    font_size = int(layout["font_size"])
    outline = int(layout["outline"])
    margin_h = int(layout["margin_h"])
    margin_v = int(layout["margin_v"])
    background_alpha = int(round(255 * (1.0 - max(0.0, min(1.0, float(settings.get("background_opacity", 0.45)))))))
    return ",".join([
        f"Style: {name}",
        str(settings.get("font_family") or "Arial"),
        str(font_size),
        ass_color(settings.get("color"), 0),
        ass_color(settings.get("color"), 0),
        ass_color(settings.get("background"), background_alpha),
        ass_color("000000", 0),
        "0", "0", "0", "0", "100", "100", "0", "0",
        "3" if float(settings.get("background_opacity", 0.45)) > 0 else "1",
        str(outline), "0", "2", str(margin_h), str(margin_h), str(margin_v), "1",
    ])


def build_ass_style_lines(style_registry_values: Iterable[tuple[str, dict[str, Any]]], width: int, height: int) -> list[str]:
    """Return ASS style lines from caller-finalized style registry values."""
    return [ass_style_from_defaults(settings, width, height, name) for name, settings in style_registry_values]


def prepare_styled_ass_events(subtitle_events: Iterable[dict[str, Any]]) -> tuple[list[tuple[dict[str, Any], str]], list[tuple[str, dict[str, Any]]]]:
    """Assign stable ASS style names to subtitle events and return style registry values."""
    styled_events: list[tuple[dict[str, Any], str]] = []
    styles: dict[tuple[Any, ...], tuple[str, dict[str, Any]]] = {}

    for event in subtitle_events:
        normalized = normalize_subtitle_defaults(event)
        key = ass_style_key(normalized)
        existing = styles.get(key)
        if existing:
            style_name = existing[0]
        else:
            style_name = "Default" if not styles else f"Subtitle{len(styles) + 1}"
            styles[key] = (style_name, normalized)
        styled_events.append((event, style_name))
    return styled_events, list(styles.values())


def format_ass_document(width: int, height: int, style_lines: list[str], dialogue_lines: list[str]) -> str:
    """Return static ASS document sections with caller-prepared styles and dialogues."""
    return "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,BackColour,OutlineColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        *style_lines,
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
        *dialogue_lines,
        "",
    ])
