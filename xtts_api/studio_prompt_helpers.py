import re
from typing import Any


def truncate_text(value: Any, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def build_video_group_visual_context(title: Any, visual_prompt: Any, summary: Any, *, limit: int = 1400) -> str:
    """Return fallback shared visual continuity text for a normalized video group."""
    return truncate_text(
        f"Shared continuity for {title}: {visual_prompt or summary}. Keep character/subject identity, palette, camera, era, clothing, materials, and environment consistent across this group.",
        limit,
    )


def build_repaired_video_group_fields(raw_group: dict[str, Any], ids: list[str], number: int, *, source: str, repair_note: str) -> dict[str, Any]:
    """Return normalized raw fields for a repaired AI video group before final coverage normalization."""
    return {
        "id": f"video_group_{number:03d}",
        "title": truncate_text(raw_group.get("title") or f"Video group {number}", 120),
        "summary": truncate_text(raw_group.get("summary"), 600),
        "chunk_ids": ids,
        "visual_prompt": truncate_text(raw_group.get("visual_prompt"), 900),
        "visual_context": truncate_text(raw_group.get("visual_context") or raw_group.get("shared_visual_context"), 1400),
        "negative_prompt": truncate_text(raw_group.get("negative_prompt"), 500),
        "animation_positive_prompt": normalize_animation_positive_prompt(raw_group),
        "animation_negative_prompt": normalize_animation_negative_prompt(raw_group),
        "grok_video_prompt": normalize_grok_video_prompt(raw_group),
        "mood": truncate_text(raw_group.get("mood"), 80),
        "scene_type": truncate_text(raw_group.get("scene_type"), 80),
        "order": number - 1,
        "source": source,
        "repair_note": repair_note,
    }


def build_normalized_video_group_prompt_fields(raw_group: dict[str, Any], ids: list[str], number: int, *, source: str | None = None) -> dict[str, Any]:
    """Return normalized prompt/text fields for one video group without media or subtitle fields."""
    item = {
        "id": f"video_group_{number:03d}",
        "title": truncate_text(raw_group.get("title") or f"Video group {number}", 120),
        "summary": truncate_text(raw_group.get("summary"), 600),
        "chunk_ids": ids,
        "visual_prompt": truncate_text(raw_group.get("visual_prompt"), 900),
        "visual_context": truncate_text(raw_group.get("visual_context") or raw_group.get("shared_visual_context"), 1400),
        "negative_prompt": truncate_text(raw_group.get("negative_prompt"), 500),
        "animation_positive_prompt": normalize_animation_positive_prompt(raw_group),
        "animation_negative_prompt": normalize_animation_negative_prompt(raw_group),
        "grok_video_prompt": normalize_grok_video_prompt(raw_group),
        "mood": truncate_text(raw_group.get("mood"), 80),
        "scene_type": truncate_text(raw_group.get("scene_type"), 80),
        "order": number - 1,
        "source": source or truncate_text(raw_group.get("source") or "manual", 40),
    }
    if not item["visual_context"]:
        item["visual_context"] = build_video_group_visual_context(item["title"], item["visual_prompt"], item["summary"])
    return item


def build_repaired_video_group_note(scope_label: str, extra_ids: list[str], duplicate_ids: list[str], missing_ids: list[str]) -> str:
    """Return the user-facing note for repaired AI video-group chunk coverage."""
    removed_notes: list[str] = []
    if extra_ids:
        removed_notes.append(f"removed extra ids: {', '.join(extra_ids[:10])}{'…' if len(extra_ids) > 10 else ''}")
    if duplicate_ids:
        removed_notes.append(f"removed duplicate ids: {', '.join(duplicate_ids[:10])}{'…' if len(duplicate_ids) > 10 else ''}")
    if missing_ids:
        removed_notes.append(f"inserted missing ids: {', '.join(missing_ids[:10])}{'…' if len(missing_ids) > 10 else ''}")
    repair_note = f"{scope_label}: repaired Grok chunk coverage"
    if removed_notes:
        repair_note += f" ({'; '.join(removed_notes)})"
    return repair_note


def build_no_usable_video_group_ids_note(scope_label: str) -> str:
    """Return the repair note used when AI video groups contain no usable chunk ids."""
    return f"{scope_label}: no usable Grok chunk ids; used fallback groups"


def looks_like_ancient_prehistory_scene(*values: Any) -> bool:
    text = " ".join(str(value or "") for value in values).lower()
    if not text:
        return False
    return bool(re.search(
        r"\b(prehistoric|prehistory|stone age|paleolithic|palaeolithic|mesolithic|neolithic|hominid|hominin|early human|"
        r"caveman|cave people|animal hide|animal-hide|fur cloak|hide wrap|bronze age|iron age|"
        r"ancient villager|ancient village|hunter-gatherer|hunter gatherer)\b",
        text,
        flags=re.IGNORECASE,
    ))


def append_unique_csv_terms(base: str, extra: str, *, limit: int = 1500) -> str:
    seen: set[str] = set()
    terms: list[str] = []
    for source in (base, extra):
        for raw_term in str(source or "").split(","):
            term = re.sub(r"\s+", " ", raw_term).strip()
            if not term:
                continue
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(term)
    return truncate_text(", ".join(terms), limit)


DEFAULT_ANIMATION_POSITIVE_PROMPT = (
    "Calm seamless image-to-video loop, perfect loop, first and last frame match naturally, locked static camera and no camera movement. "
    "Animate only objects or scene elements inside the frame: gentle grass or leaves swaying, soft water ripples, "
    "faint smoke drifting, candle or fire flicker, slow cyclic clouds, floating dust motes, and light fabric movement. "
    "Keep motion subtle and continuous with no beginning or ending reveal; keep the original composition stable, peaceful, slow, realistic, and suitable for a quiet sleep documentary loop."
)
DEFAULT_ANIMATION_NEGATIVE_PROMPT = (
    "camera movement, camera pan, camera zoom, camera orbit, dolly, trucking shot, whole image moving, drifting frame, "
    "handheld camera, camera shake, tilt, fast action, cut, cuts, jump cut, scene transition, scene change, character movement, walking, running, talking, "
    "gestures, morphing, warping, new objects appearing, objects disappearing, disappearing objects, non-looping motion, one-way motion, sudden ending, start/end mismatch, object popping, text, subtitles, watermark, logo, "
    "flicker artifacts, jitter, strobe, abrupt lighting changes"
)
NO_PEOPLE_IMAGE_NEGATIVE = (
    "people, person, human, humans, face, faces, body, bodies, crowd, crowds, hands, fingers, arms, legs, "
    "characters, man, woman, child, clothing, portrait, selfie, skin, eyes, hair"
)
NO_PEOPLE_VISUAL_INSTRUCTION = (
    "No people, faces, bodies, crowds, hands, characters, portraits, clothing, or human silhouettes. "
    "Focus only on environment, landscape, objects, architecture, nature, artifacts, tools, textures, light, weather, and atmosphere. "
)
NO_TEXT_IMAGE_INSTRUCTION = (
    "No visible text anywhere in the image: no words, no letters, no subtitles, no captions, no UI, no signs, "
    "no labels, no watermark, no logo, no readable writing, and no glyph-like markings. "
)
NO_TEXT_IMAGE_NEGATIVE = "text, letters, words, captions, subtitles, UI, interface, signs, signboard, labels, readable writing, watermark, logo, signature, typography, calligraphy, numbers, glyphs"


def format_grok_imagine_video_prompt(group: dict[str, Any]) -> str:
    base = truncate_text(
        group.get("grok_video_prompt") or group.get("animation_positive_prompt") or group.get("visual_prompt") or group.get("summary") or group.get("title"),
        1200,
    )
    if not base:
        base = DEFAULT_ANIMATION_POSITIVE_PROMPT
    return truncate_text(
        f"{base}. Locked static camera, stable composition, preserve the source image scene and framing. "
        "Generate a seamless looping video / perfect loop: first and last frame match naturally, cyclic ambient motion, no beginning or ending reveal. "
        "Animate only subtle continuous natural object or environmental motion inside the frame: gentle cyclic leaves, grass, water, smoke, firelight, clouds, dust motes, or fabric where appropriate. "
        "For landscapes, make leaves, grass, water, and clouds move in a gentle cyclic pattern. "
        "No cuts, no jump cut, no scene transition, no zoom, no pan, no camera shake, no sudden camera movement, no new objects appearing, no objects disappearing, no object popping, no text, no start/end mismatch, calm realistic sleep-documentary motion.",
        1800,
    )


def format_animatediff_prompt(group: dict[str, Any]) -> dict[str, str]:
    """Return SD AnimateDiff positive/negative prompt strings for a visual group."""
    positive = append_unique_csv_terms(
        truncate_text(group.get("animation_positive_prompt") or group.get("visual_prompt") or group.get("summary"), 1200),
        "locked camera, static camera, stable composition, subtle natural ambient motion only, slow peaceful loop",
        limit=1400,
    )
    negative = append_unique_csv_terms(
        truncate_text(group.get("animation_negative_prompt") or group.get("negative_prompt"), 900),
        "camera pan, camera zoom, camera orbit, dolly, camera shake, whole image moving, drifting frame, fast action, cuts, scene change, morphing, warping, new objects, text, subtitles, watermark, flicker, jitter",
        limit=1100,
    )
    return {"positive_prompt": positive, "negative_prompt": negative}


def format_unsupported_grok_imagine_video_resolution_error(resolution: Any, allowed_resolutions: set[str]) -> str:
    """Return the user-facing error for an unsupported Grok Imagine Video resolution."""
    return f"Unsupported Grok Imagine Video resolution '{resolution}'. Confirmed options are: {', '.join(sorted(allowed_resolutions))}"


def format_grok_imagine_video_status_error(status: Any, detail: Any) -> str:
    """Return the user-facing error for a failed Grok Imagine Video poll status."""
    return f"xAI Imagine Video {status}: {truncate_text(detail, 700)}"


def format_grok_imagine_video_timeout_error(request_id: Any, timeout_seconds: float) -> str:
    """Return the user-facing error for a Grok Imagine Video polling timeout."""
    return f"Timed out waiting for xAI Imagine Video request {request_id} after {timeout_seconds:.0f}s"


def format_xai_image_missing_url_error(response: Any) -> str:
    """Return the user-facing error for an xAI image response without image data."""
    return f"xAI image response did not include a URL or b64_json: {truncate_text(response, 700)}"


def grok_imagine_video_api_key_blockers(api_key_configured: bool) -> list[str]:
    """Return diagnostics blockers for missing Grok Imagine Video API key configuration."""
    return [] if api_key_configured else ["Grok/xAI API key is not configured; set a project key in XTTS Studio settings or XAI_API_KEY."]


def grok_imagine_video_diagnostics_warnings() -> list[str]:
    """Return static diagnostics warnings for Grok Imagine Video generation."""
    return [
        "This backend calls a paid hosted xAI video endpoint when generation is queued.",
        "Generated xAI URLs are temporary; XTTS Studio downloads the result into project video storage immediately after polling returns done.",
    ]


def grok_imagine_video_diagnostics_docs() -> dict[str, str]:
    """Return static xAI documentation links for Grok Imagine Video diagnostics."""
    return {
        "video_generation": "https://docs.x.ai/developers/model-capabilities/video/generation",
        "image_to_video": "https://docs.x.ai/developers/model-capabilities/video/image-to-video",
    }


def grok_imagine_video_diagnostics_defaults(video_settings: dict[str, Any], poll_timeout_sec: float, poll_interval_sec: float) -> dict[str, Any]:
    """Return default Grok Imagine Video diagnostics values from normalized video settings."""
    return {
        "duration_sec": video_settings.get("grok_duration_sec"),
        "resolution": video_settings.get("grok_resolution"),
        "aspect_ratio_mode": video_settings.get("grok_aspect_ratio_mode"),
        "loop_postprocess": video_settings.get("grok_loop_postprocess"),
        "crossfade_sec": video_settings.get("grok_crossfade_sec"),
        "poll_timeout_sec": poll_timeout_sec,
        "poll_interval_sec": poll_interval_sec,
    }


def grok_imagine_video_diagnostics_quality_options(presets: Any, confirmed_resolutions: set[str]) -> dict[str, Any]:
    """Return Grok Imagine Video diagnostics quality options."""
    return {
        "presets": presets,
        "confirmed_resolutions": sorted(confirmed_resolutions),
        "note": "Docs/examples confirm 480p and 720p; 1080p is intentionally not exposed until official docs confirm it.",
    }


def grok_imagine_video_diagnostics_aspect_ratio_behavior(confirmed_aspect_ratios: set[str], sample_resolved_aspect_ratio: str) -> dict[str, Any]:
    """Return Grok Imagine Video diagnostics aspect ratio behavior."""
    return {
        "auto": "16:9 for landscape/source width >= height; 9:16 for portrait/source height > width; square/unknown defaults to 16:9.",
        "confirmed_aspect_ratios": sorted(confirmed_aspect_ratios),
        "sample_resolved_aspect_ratio": sample_resolved_aspect_ratio,
    }


def build_grok_imagine_video_request_payload(model: str, prompt: str, image_data_url: str, duration: int, aspect_ratio: str, resolution: str) -> dict[str, Any]:
    """Return the xAI Imagine Video request payload from normalized inputs."""
    return {
        "model": model,
        "prompt": prompt,
        "image": {"url": image_data_url},
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
    }


def normalize_grok_video_download_suffix(suffix: Any) -> str:
    """Return a safe file suffix for downloaded Grok Imagine Video assets."""
    normalized = str(suffix or "").lower()
    return normalized if normalized in {".mp4", ".webm", ".gif"} else ".mp4"


def normalize_grok_imagine_video_resolution(value: Any, allowed_resolutions: set[str]) -> str:
    """Return a normalized Grok Imagine Video resolution or raise a user-facing error."""
    resolution = str(value or "480p").strip().lower()
    if resolution not in allowed_resolutions:
        raise RuntimeError(format_unsupported_grok_imagine_video_resolution_error(resolution, allowed_resolutions))
    return resolution


def grok_imagine_video_resolution_options(allowed_resolutions: set[str]) -> list[str]:
    """Return sorted Grok Imagine Video resolution options for settings responses."""
    return sorted(allowed_resolutions)


def normalize_grok_imagine_video_duration(value: Any, *, default_duration: int = 5) -> int:
    """Return a Grok Imagine Video duration clamped to the API-supported range."""
    return max(1, min(30, int(value or default_duration)))


def build_animation_positive_prompt(summary: Any = "", visual_prompt: Any = "") -> str:
    scene_hint = truncate_text(summary or visual_prompt, 220)
    if scene_hint:
        return truncate_text(
            "Calm seamless image-to-video loop, perfect loop, first and last frame match naturally, locked camera, very subtle natural ambient motion only. "
            f"Preserve the scene inspired by: {scene_hint}. "
            "Animate cyclic gentle environmental details such as grass or leaves swaying in soft wind, water ripples, "
            "smoke or candle/fire flicker, drifting clouds, floating dust motes, and light fabric movement where appropriate. "
            "Keep the composition stable, slow, realistic, peaceful, continuous, with no cuts, no scene change, no object popping, and no beginning or ending reveal.",
            900,
        )
    return DEFAULT_ANIMATION_POSITIVE_PROMPT


def normalize_animation_positive_prompt(raw_group: dict[str, Any]) -> str:
    prompt = truncate_text(raw_group.get("animation_positive_prompt") or raw_group.get("loop_motion_prompt"), 900)
    if prompt:
        return prompt
    return build_animation_positive_prompt(raw_group.get("summary"), raw_group.get("visual_prompt"))


def normalize_animation_negative_prompt(raw_group: dict[str, Any]) -> str:
    prompt = truncate_text(raw_group.get("animation_negative_prompt"), 700)
    if prompt:
        return prompt
    return DEFAULT_ANIMATION_NEGATIVE_PROMPT


def normalize_grok_video_prompt(raw_group: dict[str, Any]) -> str:
    prompt = truncate_text(raw_group.get("grok_video_prompt"), 1800)
    if prompt:
        return prompt
    return format_grok_imagine_video_prompt(raw_group)


def no_text_images_enabled(project: dict[str, Any] | None = None, settings: dict[str, Any] | None = None) -> bool:
    raw = settings if isinstance(settings, dict) else ((project or {}).get("settings", {}) if isinstance((project or {}).get("settings"), dict) else {})
    return bool(raw.get("image_no_text", True))


def project_visual_context(project: dict[str, Any] | None = None) -> str:
    settings = (project or {}).get("settings", {}) if isinstance((project or {}).get("settings"), dict) else {}
    return truncate_text(settings.get("project_visual_context"), 1400)


def group_visual_context(group: dict[str, Any] | None = None) -> str:
    return truncate_text((group or {}).get("visual_context"), 1400)


def apply_no_text_to_prompts(positive: Any, negative: Any, *, enabled: bool = True, positive_limit: int = 3000, negative_limit: int = 1500) -> dict[str, str]:
    pos = truncate_text(positive, positive_limit)
    neg = truncate_text(negative, negative_limit)
    if not enabled:
        return {"positive_prompt": pos, "negative_prompt": neg}
    if NO_TEXT_IMAGE_INSTRUCTION.lower() not in pos.lower():
        pos = truncate_text(f"{NO_TEXT_IMAGE_INSTRUCTION}{pos}", positive_limit)
    neg = append_unique_csv_terms(neg, NO_TEXT_IMAGE_NEGATIVE, limit=negative_limit)
    return {"positive_prompt": pos, "negative_prompt": neg}


def image_orientation_phrase(settings: dict[str, Any]) -> str:
    """Return the short image prompt phrase for vertical or horizontal composition."""
    return "vertical portrait composition, 9:16 frame" if settings.get("aspect_ratio") == "vertical" else "wide horizontal composition, 16:9 frame"


def visual_context_prefix(project: dict[str, Any], group: dict[str, Any]) -> str:
    parts = []
    project_context = project_visual_context(project)
    group_context = group_visual_context(group)
    if project_context:
        parts.append(f"Project-wide visual continuity context: {project_context}")
    if group_context:
        parts.append(f"Group shared visual continuity context: {group_context}")
    if parts:
        parts.append("Keep the same visual style, palette, era, camera language, character/subject identity, clothing, materials, environment, and mood unless the narration explicitly requires a change.")
    return ". ".join(parts)


def grok_image_aspect_ratio_from_dimensions(width: int, height: int, orientation: str = "vertical") -> str:
    """Return the nearest Grok image aspect ratio for dimensions or orientation fallback."""
    if width > 0 and height > 0:
        ratio = width / max(1, height)
        candidates = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4}
        return min(candidates, key=lambda key: abs(candidates[key] - ratio))
    return "16:9" if orientation == "horizontal" else "9:16"


def grok_image_aspect_ratio_from_settings(settings: dict[str, Any]) -> str:
    """Return the Grok image request aspect ratio from normalized image settings."""
    return "9:16" if str(settings.get("aspect_ratio")) == "vertical" else "16:9"


def grok_image_dimensions_from_settings(settings: dict[str, Any]) -> tuple[int, int]:
    """Return Grok image dimensions from normalized image settings."""
    return int(settings.get("width") or 1024), int(settings.get("height") or 1024)


def image_preset_dimensions(value: Any, aspect_value: Any, presets: dict[str, Any], *, default_quality: str = "balanced", default_aspect: str = "vertical") -> tuple[str, str, int, int]:
    """Return normalized image preset, aspect, and default dimensions."""
    quality_preset = str(value or default_quality).strip().lower()
    if quality_preset not in presets:
        quality_preset = "balanced"
    aspect_ratio = str(aspect_value or default_aspect).strip().lower()
    if aspect_ratio not in {"vertical", "horizontal"}:
        aspect_ratio = "vertical"
    preset_size = presets[quality_preset][aspect_ratio]
    return quality_preset, aspect_ratio, int(preset_size["width"]), int(preset_size["height"])


def image_seed_value(value: Any) -> int:
    """Return the configured image seed integer or zero for fallback selection."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_image_dimensions_for_orientation(width: int, height: int, aspect_ratio: str) -> tuple[int, int]:
    """Return dimensions with width/height ordered for the selected image orientation."""
    if aspect_ratio == "horizontal" and height > width:
        width, height = max(width, height), min(width, height)
    if aspect_ratio == "vertical" and width > height:
        width, height = min(width, height), max(width, height)
    return width, height


def clamp_image_dimension(value: Any, *, min_value: int = 64, max_value: int = 4096) -> int:
    """Return an image dimension clamped to the supported local workflow range."""
    return max(min_value, min(max_value, int(value)))


def grok_image_model_from_settings(settings: dict[str, Any], default_model: str) -> str:
    """Return the normalized Grok image model from image settings."""
    return str(settings.get("grok_model") or default_model).strip() or default_model


def normalize_image_provider(value: Any, default_provider: str) -> str:
    """Return a supported image provider, preserving the legacy xAI alias."""
    provider = str(value or default_provider).strip().lower()
    if provider not in {"placeholder", "comfyui", "grok", "xai"}:
        provider = "comfyui"
    if provider == "xai":
        provider = "grok"
    return provider


def normalize_image_model(value: Any, provider: str, checkpoint: Any, realvisxl_checkpoint: str, default_model: str) -> str:
    """Return the normalized image model for image settings."""
    model = str(value or default_model).strip().lower()
    if provider == "grok":
        model = "grok"
    if model not in {"realvisxl", "sdxl", "juggernautxl", "dreamshaperxl", "flux", "custom", "grok"}:
        model = "custom"
    if model == "sdxl" and str(checkpoint or "").strip() == realvisxl_checkpoint:
        model = "realvisxl"
    return model


def format_grok_image_generation_prompt(prompt: Any, width: int, height: int, *, no_text: bool = True) -> str:
    """Return a Grok image prompt with XTTS Studio composition constraints appended."""
    text = str(prompt or "")
    if width and height:
        text = f"{text}\n\nComposition request: render for approximately {width}x{height} pixels; preserve this aspect ratio.".strip()
    if no_text:
        text = f"{text}\n\nStrict content constraint: do not render any text, letters, readable writing, captions, subtitles, UI, signs, labels, watermark, logo, or numbers anywhere in the image unless explicitly requested by the user.".strip()
    return text


def format_grok_image_request_prompt(prompt_bundle: dict[str, str], width: int, height: int, *, no_text: bool = True) -> str:
    """Return the final Grok image request prompt from stored prompt fields and dimensions."""
    prompt = grok_image_positive_prompt_from_bundle(prompt_bundle, no_text=no_text)
    return format_grok_image_generation_prompt(prompt, width, height, no_text=no_text)


def build_grok_image_request_payload(settings: dict[str, Any], prompt: str, default_resolution: str, allowed_resolutions: set[str]) -> dict[str, Any]:
    """Return the xAI image-generation request payload from normalized image settings."""
    return {
        "model": str(settings.get("grok_model") or "").strip(),
        "prompt": prompt,
        "n": 1,
        "aspect_ratio": grok_image_aspect_ratio_from_settings(settings),
        "resolution": normalize_grok_image_resolution(settings.get("grok_resolution"), default_resolution, allowed_resolutions),
    }


def build_grok_image_request_metadata(width: int, height: int, reference_limitation_note: str) -> dict[str, Any]:
    """Return metadata describing the xAI image-generation request shape."""
    return {
        "endpoint": "/images/generations",
        "supported_parameters": ["model", "prompt", "n", "aspect_ratio", "resolution"],
        "dimensions_requested_via_prompt": bool(width and height),
        "reference_conditioning": "not implemented; prompt/context-based consistency only",
        "consistency_note": reference_limitation_note,
    }


def grok_image_negative_prompt_from_bundle(prompt_bundle: dict[str, str], *, no_text: bool = True) -> str:
    """Return the stored Grok image negative prompt after optional no-text normalization."""
    return apply_no_text_to_prompts("", prompt_bundle.get("negative_prompt", ""), enabled=no_text).get("negative_prompt", "")


def grok_image_positive_prompt_from_bundle(prompt_bundle: dict[str, str], *, no_text: bool = True) -> str:
    """Return the stored Grok image positive prompt after optional no-text normalization."""
    return apply_no_text_to_prompts(prompt_bundle.get("positive_prompt", ""), prompt_bundle.get("negative_prompt", ""), enabled=no_text).get("positive_prompt", "")


def normalize_grok_image_model(value: Any, default_model: str, legacy_models: set[str]) -> str:
    """Return a Grok image model, replacing blank or legacy values with the current default."""
    model = str(value or "").strip()
    if not model or model.lower() in legacy_models:
        return default_model
    return model


def normalize_grok_image_resolution(value: Any, default_resolution: str, allowed_resolutions: set[str]) -> str:
    """Return a supported Grok image resolution or the configured default."""
    resolution = str(value or default_resolution).strip().lower()
    return resolution if resolution in allowed_resolutions else default_resolution
