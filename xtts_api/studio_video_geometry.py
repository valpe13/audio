import copy
from pathlib import Path
from typing import Any


GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS = {"16:9", "9:16"}
VIDEO_SOURCE_SUFFIXES = {".mp4", ".webm", ".gif", ".mov", ".mkv"}
COMFYUI_VIDEO_OUTPUT_SUFFIXES = (".mp4", ".webm", ".gif")


def rounded_video_dimension(value: Any, fallback: int, *, multiple: int = 8, minimum: int = 64, maximum: int = 4096) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = int(fallback)
    number = max(minimum, min(maximum, number))
    return max(multiple, int(round(number / multiple)) * multiple)


def svd_source_dimensions(settings: dict[str, Any], image_meta: dict[str, Any] | None = None) -> tuple[int, int]:
    image_meta = image_meta if isinstance(image_meta, dict) else {}
    default_width = int(settings.get("width") or 1024)
    default_height = int(settings.get("height") or 576)
    width = rounded_video_dimension(image_meta.get("width"), default_width)
    height = rounded_video_dimension(image_meta.get("height"), default_height)
    aspect_ratio = str(image_meta.get("aspect_ratio") or settings.get("aspect_ratio") or "").lower()
    if aspect_ratio == "vertical" and width > height:
        width, height = height, width
    elif aspect_ratio == "horizontal" and height > width:
        width, height = height, width
    return width, height


def animatediff_target_dimensions_for_source(width: int, height: int) -> tuple[int, int]:
    """Return SD1.5 AnimateDiff target dimensions for an already-normalized source size."""
    return (512, 768) if height >= width else (768, 512)


def animatediff_sdxl_target_dimensions_for_source(width: int, height: int) -> tuple[int, int]:
    """Return SDXL AnimateDiff target dimensions for an already-normalized source size."""
    return (768, 1024) if height >= width else (1024, 768)


def animatediff_required_node_names() -> list[str]:
    """Return the shared required ComfyUI node names for AnimateDiff diagnostics."""
    return ["CheckpointLoaderSimple", "LoadImage", "ImageScale", "RepeatImageBatch", "VAEEncode", "CLIPTextEncode", "KSampler", "VAEDecode", "VHS_VideoCombine", "ADE_LoadAnimateDiffModel", "ADE_ApplyAnimateDiffModelSimple", "ADE_UseEvolvedSampling"]


def animatediff_sdxl_optional_node_names() -> list[str]:
    """Return optional SDXL AnimateDiff helper node names used for diagnostics."""
    return ["ADE_StandardUniformContextOptions", "ADE_LoopedUniformContextOptions", "ADE_PerBlock_SDXL_LowLevel", "ADE_PerBlock_SDXL_MidLevel"]


def animatediff_missing_node_names(object_info: dict[str, Any], node_names: list[str]) -> list[str]:
    """Return ComfyUI node names absent from object_info diagnostics."""
    return [node for node in node_names if node not in object_info]


def animatediff_combined_node_names(required_nodes: list[str], optional_nodes: list[str]) -> list[str]:
    """Return the combined AnimateDiff diagnostics node-name list."""
    return required_nodes + optional_nodes


def animatediff_motion_model_suffixes() -> tuple[str, ...]:
    """Return file suffixes considered for AnimateDiff motion-model discovery."""
    return (".safetensors", ".ckpt", ".pt", ".pth")


def comfyui_video_output_suffixes() -> tuple[str, ...]:
    """Return ComfyUI video output suffixes accepted by XTTS Studio."""
    return COMFYUI_VIDEO_OUTPUT_SUFFIXES


def source_image_aspect_ratio(settings: dict[str, Any], image_meta: dict[str, Any] | None = None, *, mode: str = "auto") -> str:
    requested = str(mode or "auto").strip().lower()
    if requested in GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS:
        return requested
    width, height = svd_source_dimensions(settings, image_meta)
    if height > width:
        return "9:16"
    return "16:9"


def video_i2v_loop_count(target_duration_sec: float, base_output_frames: int, fps: int, *, max_loop_count: int = 30) -> int:
    """Return the clamped extra loop count for generated image-to-video output."""
    base_duration = max(1, base_output_frames) / float(max(1, fps))
    return max(0, min(max_loop_count, int(max(1, round(target_duration_sec / max(0.001, base_duration)))) - 1))


def video_i2v_base_output_frames(frames: int, *, pingpong: bool) -> int:
    """Return the base generated frame count before extra loop repetitions."""
    return max(1, frames * 2 - 2) if pingpong and frames > 1 else max(1, frames)


def video_i2v_workflow_mode(value: Any, *, default: str = "generated_svd") -> str:
    """Return a supported image-to-video workflow mode."""
    mode = str(value or default).strip().lower()
    if mode not in {"generated_svd", "generated_animatediff", "generated_hotshotxl", "generated_grok_imagine_video", "disabled"}:
        return str(default)
    return mode


def video_i2v_motion_style(value: Any, motion_style_presets: dict[str, Any], *, default: str = "ambient_nature") -> str:
    """Return a supported image-to-video motion style key."""
    motion_style = str(value or default).strip().lower()
    if motion_style not in motion_style_presets:
        return default
    return motion_style


def video_i2v_quality_preset(value: Any, quality_presets: dict[str, Any], *, default: str = "balanced") -> str:
    """Return a supported image-to-video quality preset key."""
    quality_preset = str(value or default).strip().lower()
    if quality_preset not in quality_presets:
        return default
    return quality_preset


def video_i2v_checkpoint_name(value: Any, *, default: str) -> str:
    """Return the configured image-to-video checkpoint name with legacy fallback semantics."""
    return str(value or default).strip()


def video_i2v_grok_model_name(value: Any, *, default: str) -> str:
    """Return the configured Grok Imagine Video model name with legacy fallback semantics."""
    return str(value or default).strip() or default


def video_i2v_model_names(settings: dict[str, Any], *, default_checkpoint: str, default_grok_model: str) -> dict[str, str]:
    """Return normalized image-to-video backend model names."""
    return {
        "model_checkpoint": video_i2v_checkpoint_name(settings.get("video_i2v_model_checkpoint"), default=default_checkpoint),
        "grok_model": video_i2v_grok_model_name(settings.get("video_i2v_grok_model"), default=default_grok_model),
    }


def video_i2v_preset_option(preset: dict[str, Any], key: str, *, default: str) -> str:
    """Return a stripped string option from an image-to-video quality preset."""
    return str(preset.get(key) or default).strip()


def video_i2v_preset_string_options(preset: dict[str, Any], defaults: dict[str, str], keys: tuple[str, ...]) -> dict[str, str]:
    """Return stripped string options from an image-to-video quality preset."""
    return {
        key: video_i2v_preset_option(preset, key, default=str(defaults[key]))
        for key in keys
    }


def video_i2v_sampler_scheduler_options(preset: dict[str, Any], defaults: dict[str, Any]) -> dict[str, str]:
    """Return the normalized sampler and scheduler options from an image-to-video quality preset."""
    return video_i2v_preset_string_options(
        preset,
        {
            "sampler": str(defaults["video_i2v_sampler"]),
            "scheduler": str(defaults["video_i2v_scheduler"]),
        },
        ("sampler", "scheduler"),
    )


def video_i2v_grok_options(duration_sec: int, resolution: str, aspect_ratio_mode: str, loop_postprocess: str, crossfade_sec: float) -> dict[str, Any]:
    """Return grouped normalized Grok Imagine Video options."""
    return {
        "grok_duration_sec": duration_sec,
        "grok_resolution": resolution,
        "grok_aspect_ratio_mode": aspect_ratio_mode,
        "grok_loop_postprocess": loop_postprocess,
        "grok_crossfade_sec": crossfade_sec,
    }


def video_i2v_loop_output_options(target_duration_sec: float, frames: int, fps: int, *, pingpong: bool) -> dict[str, int]:
    """Return grouped normalized SVD loop-output options."""
    base_output_frames = video_i2v_base_output_frames(frames, pingpong=pingpong)
    return {
        "loop_count": video_i2v_loop_count(target_duration_sec, base_output_frames, fps),
        "output_fps": fps,
    }


def video_i2v_svd_numeric_options(
    frames: int,
    fps: int,
    motion_bucket_id: int,
    augmentation_level: float,
    cfg: float,
    steps: int,
) -> dict[str, Any]:
    """Return grouped normalized SVD numeric image-to-video options."""
    return {
        "frames": frames,
        "fps": fps,
        "motion_bucket_id": motion_bucket_id,
        "augmentation_level": augmentation_level,
        "cfg": cfg,
        "steps": steps,
    }


def video_i2v_style_numeric_options(
    style_preset: dict[str, Any],
    int_setting: Any,
    float_setting: Any,
) -> dict[str, Any]:
    """Return grouped SVD numeric options after motion-style overrides."""
    frames = video_i2v_style_capped_int_value(int_setting("video_i2v_frames", 2, 256), style_preset, "max_frames", fallback_cap=256)
    fps = video_i2v_style_capped_int_setting(style_preset, "max_fps", int_setting("video_i2v_fps", 1, 60), fallback_cap=60)
    motion_bucket_id = video_i2v_style_int_value(style_preset, "motion_bucket_id", int_setting("video_i2v_motion_bucket_id", 1, 1023), min_value=1, max_value=1023)
    augmentation_level = video_i2v_style_float_value(style_preset, "augmentation_level", float_setting("video_i2v_augmentation_level", 0.0, 1.0), min_value=0.0, max_value=1.0)
    cfg = video_i2v_style_float_value(style_preset, "cfg", float_setting("video_i2v_cfg", 0.0, 30.0), min_value=0.0, max_value=30.0)
    steps = video_i2v_style_delta_int_value(int_setting("video_i2v_steps", 1, 150), style_preset, "steps_delta", min_value=1, max_value=150)
    return video_i2v_svd_numeric_options(frames, fps, motion_bucket_id, augmentation_level, cfg, steps)


def video_i2v_svd_return_options(svd_numeric_options: dict[str, Any], min_cfg: float, preset_string_options: dict[str, str]) -> dict[str, Any]:
    """Return grouped normalized SVD options used in the image-to-video settings response."""
    return {
        **svd_numeric_options,
        "min_cfg": min_cfg,
        "sampler": preset_string_options["sampler"],
        "scheduler": preset_string_options["scheduler"],
    }


def video_i2v_style_int_value(style_preset: dict[str, Any], key: str, fallback: int, *, min_value: int, max_value: int) -> int:
    """Return a bounded integer style-preset override with legacy fallback semantics."""
    return max(min_value, min(max_value, int(style_preset.get(key) or fallback)))


def video_i2v_style_capped_int_value(value: int, style_preset: dict[str, Any], key: str, *, fallback_cap: int) -> int:
    """Return an integer value capped by a style-preset integer limit."""
    return min(int(value), int(style_preset.get(key) or fallback_cap))


def video_i2v_style_capped_int_setting(style_preset: dict[str, Any], key: str, fallback: int, *, fallback_cap: int) -> int:
    """Return a fallback integer constrained by a style-preset cap."""
    return video_i2v_style_capped_int_value(fallback, style_preset, key, fallback_cap=fallback_cap)


def video_i2v_style_delta_int_value(value: int, style_preset: dict[str, Any], key: str, *, min_value: int, max_value: int) -> int:
    """Return an integer adjusted by a style-preset delta and clamped to bounds."""
    return max(min_value, min(max_value, int(value) + int(style_preset.get(key) or 0)))


def video_i2v_style_float_value(style_preset: dict[str, Any], key: str, fallback: float, *, min_value: float, max_value: float) -> float:
    """Return a bounded float style-preset override with legacy fallback semantics."""
    return max(min_value, min(max_value, float(style_preset.get(key, fallback))))


def video_i2v_min_cfg_value(value: float) -> float:
    """Return the bounded SVD min_cfg value for image-to-video settings."""
    return max(0.0, min(30.0, float(value)))


def video_i2v_target_duration_sec(value: float) -> float:
    """Return the bounded target duration for image-to-video loop planning."""
    return max(2.0, min(60.0, float(value)))


def video_i2v_grok_duration_sec(value: int) -> int:
    """Return the bounded Grok Imagine Video duration setting."""
    return max(1, min(30, int(value)))


def video_i2v_grok_crossfade_sec(value: float) -> float:
    """Return the bounded Grok Imagine Video loop crossfade setting."""
    return max(0.1, min(2.0, float(value)))


def video_i2v_pingpong_enabled(settings: dict[str, Any], *, default: bool) -> bool:
    """Return whether image-to-video ping-pong output is enabled."""
    return bool(settings.get("video_i2v_pingpong", default))


def video_i2v_enabled(settings: dict[str, Any], *, default: bool) -> bool:
    """Return whether image-to-video generation is enabled."""
    return bool(settings.get("video_i2v_enabled", default))


def video_i2v_identity_options(enabled: bool, quality_preset: str, motion_style: str, workflow_mode: str) -> dict[str, Any]:
    """Return grouped image-to-video identity options for the settings response."""
    return {
        "enabled": enabled,
        "quality_preset": quality_preset,
        "motion_style": motion_style,
        "workflow_mode": workflow_mode,
    }


def video_i2v_backend_label(workflow_mode: Any, *, default_workflow_mode: str = "generated_svd") -> str:
    """Return the user-facing image-to-video backend label for a workflow mode or settings dict."""
    if isinstance(workflow_mode, dict):
        workflow_mode = workflow_mode.get("workflow_mode")
    mode = str(workflow_mode or default_workflow_mode).strip().lower()
    if mode == "generated_grok_imagine_video":
        return "Grok Imagine Video"
    if mode == "generated_animatediff":
        return "AnimateDiff SD1.5"
    if mode == "generated_hotshotxl":
        return "HotshotXL / AnimateDiff SDXL"
    return "SVD/SVD-XT"


def grok_imagine_video_resolution(value: Any, quality_preset: str, presets: dict[str, str], confirmed_resolutions: set[str]) -> str:
    """Return a confirmed Grok Imagine Video resolution for a quality preset."""
    fallback = presets.get(quality_preset, "480p")
    resolution = str(value or "").strip().lower()
    if not resolution:
        return fallback
    if resolution not in confirmed_resolutions:
        return fallback
    return resolution


def grok_imagine_video_aspect_ratio_mode(value: Any, *, default: str = "auto") -> str:
    """Return a supported Grok Imagine Video aspect-ratio mode."""
    mode = str(value or default).strip().lower()
    if mode not in {"auto", *GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS}:
        return "auto"
    return mode


def grok_imagine_video_loop_postprocess_mode(value: Any, *, default: str = "pingpong") -> str:
    """Return a supported Grok Imagine Video loop post-processing mode."""
    mode = str(value or default).strip().lower()
    if mode not in {"off", "pingpong", "crossfade"}:
        return str(default)
    return mode


def looks_like_sd15_checkpoint(name: Any) -> bool:
    """Return whether a checkpoint filename looks like an SD1.5 still-image checkpoint."""
    lower = Path(str(name)).name.lower()
    if any(token in lower for token in ("xl", "sdxl", "svd", "stable-video", "video", "flux")):
        return False
    return any(token in lower for token in ("sd15", "sd1.5", "sd_1.5", "v1-5", "v1_5", "dreamshaper", "realisticvision", "deliberate", "epicrealism", "majicmix", "revanimated"))


def looks_like_sdxl_checkpoint(name: Any) -> bool:
    """Return whether a checkpoint filename looks like an SDXL checkpoint."""
    lower = Path(str(name)).name.lower()
    return "xl" in lower or "sdxl" in lower


def looks_like_sdxl_motion_model(name: Any) -> bool:
    """Return whether a motion-model filename looks SDXL/HotshotXL-compatible."""
    lower = Path(str(name)).name.lower()
    return any(token in lower for token in ("hotshot", "hsxl", "sdxl", "animatediffxl", "adxl"))


def format_missing_comfyui_nodes_blocker(missing_nodes: Any) -> str:
    """Return the standard diagnostics blocker for missing ComfyUI node classes."""
    return f"Missing ComfyUI node class(es): {', '.join(missing_nodes)}"


def comfyui_node_inputs_for_object_info(object_info: dict[str, Any], node_names: list[str]) -> dict[str, Any]:
    """Return available ComfyUI node input metadata for diagnostics."""
    return {node: object_info.get(node, {}).get("input") for node in node_names if isinstance(object_info.get(node), dict)}


def format_comfyui_object_info_unavailable_blocker(error: Any) -> str:
    """Return the standard diagnostics blocker for unavailable ComfyUI object info."""
    return f"ComfyUI /object_info unavailable: {error or 'unknown error'}"


def format_missing_sd15_motion_model_blocker(motion_model: Any) -> str:
    """Return the SD1.5 diagnostics blocker for a missing motion model."""
    return f"Missing AnimateDiff SD1.5 motion model {motion_model} in ComfyUI/models/animatediff_models"


def format_missing_sd15_checkpoint_blocker(checkpoints: Any, expected_checkpoint: Any, motion_model: Any) -> str:
    """Return the SD1.5 diagnostics blocker for missing compatible checkpoints."""
    return f"No compatible SD1.5 checkpoint detected in ComfyUI/models/checkpoints. Installed checkpoints are: {', '.join(checkpoints) or 'none'}. Do not use {expected_checkpoint} with {motion_model}; RealVisXL is SDXL."


def format_optional_sdxl_helper_nodes_warning(missing_optional_nodes: Any) -> str:
    """Return the SDXL diagnostics warning for unavailable optional helper nodes."""
    return f"Optional SDXL/context helper nodes unavailable: {', '.join(missing_optional_nodes)}; a minimal graph may still run, but long clips or fine control can be weaker."


def format_experimental_sdxl_path_warning() -> str:
    """Return the standard SDXL diagnostics warning for experimental backend use."""
    return "This path is experimental and usually needs substantially more VRAM than SVD-XT or SD1.5 AnimateDiff; start with Fast quality and short clips."


def format_missing_sdxl_checkpoint_blocker(expected_checkpoint: Any) -> str:
    """Return the SDXL diagnostics blocker for a missing checkpoint."""
    return f"No SDXL checkpoint detected in ComfyUI/models/checkpoints. Expected {expected_checkpoint} or another SDXL checkpoint."


def format_missing_sdxl_motion_model_blocker() -> str:
    """Return the SDXL diagnostics blocker for a missing compatible motion model."""
    return "No SDXL-compatible AnimateDiff/HotshotXL motion model detected in ComfyUI/models/animatediff_models. Expected a file such as hsxl_temporal_layers.safetensors, hotshotxl.safetensors, or mm_sdxl_v10_beta.safetensors; set XTTS_ANIMATEDIFF_SDXL_MOTION_MODEL if using a different filename."


def format_incompatible_sdxl_motion_model_blocker(motion_model: Any) -> str:
    """Return the SDXL diagnostics blocker for an incompatible motion model."""
    return f"Detected only the SD1.5 motion model {motion_model}; it is not compatible with SDXL/RealVisXL."


def resolve_export_dimensions(orientation: Any, resolution: Any, source_width: int, source_height: int, source_aspect_ratio: Any) -> tuple[int, int, str]:
    """Return export width, height, and normalized orientation from simple settings."""
    normalized_orientation = str(orientation or "auto").strip().lower()
    if normalized_orientation not in {"auto", "landscape", "portrait", "square"}:
        normalized_orientation = "auto"
    if normalized_orientation == "auto":
        if source_width > 0 and source_height > 0:
            normalized_orientation = "landscape" if source_width >= source_height else "portrait"
        else:
            normalized_orientation = "landscape" if source_aspect_ratio == "horizontal" else "portrait"
    normalized_resolution = str(resolution or "720p").strip().lower()
    if normalized_resolution in {"vertical_1080x1920", "portrait_1080x1920", "9:16_1080x1920", "1080x1920"}:
        return 1080, 1920, "portrait"
    if normalized_resolution in {"horizontal_1920x1080", "landscape_1920x1080", "16:9_1920x1080", "1920x1080"}:
        return 1920, 1080, "landscape"
    long_edge = 1080 if "1080" in normalized_resolution else 720
    if normalized_orientation == "square":
        return long_edge, long_edge, normalized_orientation
    if normalized_orientation == "portrait":
        return (1080, 1920, normalized_orientation) if long_edge >= 1080 else (720, 1280, normalized_orientation)
    return (1920, 1080, normalized_orientation) if long_edge >= 1080 else (1280, 720, normalized_orientation)


def format_ffmpeg_visual_filter(width: int, height: int, fit: str) -> str:
    """Return the FFmpeg scale/crop or scale/pad filter chain for visual export segments."""
    if str(fit or "cover").lower() == "contain":
        return f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    return f"scale=w={width}:h={height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"


def format_ffmpeg_video_segment_filter(visual_filter: str, fps: int, duration: float, speed: float) -> str:
    """Return the FFmpeg filter chain for a looped video visual export segment."""
    speed_filter = f"setpts=(PTS-STARTPTS)/{speed:.3f}"
    return f"{speed_filter},{visual_filter},fps={fps},trim=duration={duration:.3f},setpts=PTS-STARTPTS"


def format_ffmpeg_still_image_segment_filter(visual_filter: str, fps: int) -> str:
    """Return the FFmpeg filter chain for a looped still-image visual export segment."""
    return f"{visual_filter},fps={fps}"


def format_export_visual_segment_filename(segment_index: int) -> str:
    """Return the stable filename for an exported visual segment index."""
    return f"segment_{segment_index:04d}.mp4"


def format_ffmpeg_executable_arg(ffmpeg: str) -> str:
    """Return an absolute executable path for an existing FFmpeg binary, preserving fallback names."""
    path = Path(ffmpeg)
    if ffmpeg and path.exists():
        return str(path.resolve())
    return ffmpeg


def group_time_ranges(project: dict[str, Any]) -> list[tuple[dict[str, Any], float, float]]:
    """Return video groups annotated with timeline ranges derived from chunk timing."""
    chunks = sorted(project.get("chunks", []), key=lambda c: c.get("order", 0))
    cursor = 0.0
    chunk_times: dict[str, tuple[float, float]] = {}
    for chunk in chunks:
        duration = float(chunk.get("duration_sec", 0.0) or 0.0)
        start = cursor
        end = start + duration
        if chunk.get("id"):
            chunk_times[str(chunk.get("id"))] = (start, end)
        cursor = end + float(chunk.get("pause_after", 0.0) or 0.0)
    groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
    ranges: list[tuple[dict[str, Any], float, float]] = []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        ids = [str(item) for item in (group.get("chunk_ids") or [])]
        spans = [chunk_times[item] for item in ids if item in chunk_times]
        if not spans:
            continue
        start = min(item[0] for item in spans)
        end = max(item[1] for item in spans)
        group_with_timing = copy.deepcopy(group)
        group_with_timing["start"] = round(start, 3)
        group_with_timing["end"] = round(end, 3)
        group_with_timing["duration"] = round(max(0.0, end - start), 3)
        group_with_timing["duration_sec"] = group_with_timing["duration"]
        ranges.append((group_with_timing, start, end))
    ranges.sort(key=lambda item: item[1])
    return ranges


def clamp_video_speed(value: Any) -> float:
    """Return a visual export playback speed constrained to the supported FFmpeg range."""
    try:
        return round(max(0.25, min(2.0, float(value))), 3)
    except (TypeError, ValueError):
        return 1.0


def normalize_speed_envelope_points(raw_points: Any) -> list[dict[str, float]]:
    """Return timeline speed envelope points normalized for project arrangement storage."""
    speed_points: list[dict[str, float]] = []
    for point in raw_points if isinstance(raw_points, list) else []:
        try:
            speed_points.append({
                "time": round(max(0.0, float(point.get("time", 0.0))), 3),
                "speed": round(max(0.25, min(2.0, float(point.get("speed", point.get("playback_rate", 1.0)) or 1.0))), 3),
            })
        except (AttributeError, TypeError, ValueError):
            continue
    return sorted(speed_points or [{"time": 0.0, "speed": 1.0}], key=lambda p: p["time"])


def main_timeline_speed_is_constant(points: list[dict[str, float]]) -> tuple[bool, float]:
    """Return whether a normalized timeline speed envelope has one effective speed."""
    normalized = points or [{"time": 0.0, "speed": 1.0}]
    first = clamp_video_speed(normalized[0].get("speed", 1.0))
    return all(abs(clamp_video_speed(point.get("speed", 1.0)) - first) <= 0.001 for point in normalized), first


def normalized_main_timeline_speed_envelope(project: dict[str, Any]) -> list[dict[str, float]]:
    """Return normalized main timeline speed envelope points for visual/audio export."""
    arrangement = project.get("arrangement", {}) if isinstance(project.get("arrangement"), dict) else {}
    raw_points = arrangement.get("main_timeline_speed_envelope", [])
    if not isinstance(raw_points, list):
        raw_points = arrangement.get("video", {}).get("speed_envelope", []) if isinstance(arrangement.get("video"), dict) else []
    points: list[dict[str, float]] = []
    if isinstance(raw_points, list):
        for point in raw_points:
            if not isinstance(point, dict):
                continue
            try:
                points.append({
                    "time": round(max(0.0, float(point.get("time", 0.0))), 3),
                    "speed": clamp_video_speed(point.get("speed", point.get("playback_rate", 1.0))),
                })
            except (TypeError, ValueError):
                continue
    points = sorted(points or [{"time": 0.0, "speed": 1.0}], key=lambda item: item["time"])
    if points[0]["time"] > 0.001:
        points.insert(0, {"time": 0.0, "speed": points[0]["speed"]})
    return points


def main_timeline_speed_at(points: list[dict[str, float]], time_sec: float) -> float:
    """Return interpolated speed at a time from an already-normalized timeline speed envelope."""
    if not points:
        return 1.0
    time_value = max(0.0, float(time_sec or 0.0))
    for idx in range(1, len(points)):
        prev = points[idx - 1]
        next_point = points[idx]
        if time_value <= next_point["time"]:
            span = max(0.0001, next_point["time"] - prev["time"])
            ratio = max(0.0, min(1.0, (time_value - prev["time"]) / span))
            return clamp_video_speed(prev["speed"] + (next_point["speed"] - prev["speed"]) * ratio)
    return clamp_video_speed(points[-1]["speed"])


def export_visual_segment_timing(start: float, end: float, speed_points: list[dict[str, float]]) -> tuple[float, float]:
    """Return clamped export segment duration and midpoint timeline speed."""
    duration = max(0.1, end - start)
    speed = main_timeline_speed_at(speed_points, start + duration / 2.0)
    return duration, speed


def split_range_by_speed_envelope(start: float, end: float, points: list[dict[str, float]]) -> list[tuple[float, float]]:
    """Split a timeline range at normalized speed-envelope point times."""
    if end <= start:
        return []
    cuts = [start]
    for point in points:
        point_time = float(point.get("time", 0.0))
        if start + 0.001 < point_time < end - 0.001:
            cuts.append(point_time)
    cuts.append(end)
    cuts = sorted(set(round(cut, 3) for cut in cuts))
    return [(cuts[idx], cuts[idx + 1]) for idx in range(len(cuts) - 1) if cuts[idx + 1] - cuts[idx] > 0.01]


def ordered_cuts_to_segments(cuts: list[float] | set[float]) -> list[tuple[float, float]]:
    """Return adjacent positive-length segments from rounded timeline cuts."""
    ordered = sorted(cuts)
    return [(ordered[idx], ordered[idx + 1]) for idx in range(len(ordered) - 1) if ordered[idx + 1] - ordered[idx] > 0.01]


def visual_group_duration_seconds(group: dict[str, Any], fallback: float = 0.0) -> float:
    """Return a minimum visual group duration from duration fields or a fallback."""
    try:
        return max(0.25, float(group.get("duration") or group.get("duration_sec") or fallback))
    except (TypeError, ValueError):
        return max(0.25, fallback)


def scheduled_group_media_items(items: Any) -> list[dict[str, Any]]:
    """Return media items that participate in an explicit group timeline."""
    return [item for item in items if isinstance(item, dict) and item.get("scheduled") is not False and (item.get("kind") == "timeline_block" or item.get("start_offset_sec") is not None or item.get("duration_sec") is not None)]


def scheduled_visual_media_items(media_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return scheduled visual media items with usable local or remote sources."""
    return sorted(
        [
            item for item in scheduled_group_media_items(media_items)
            if visual_media_item_has_source(item)
        ],
        key=visual_media_timeline_sort_key,
    )


def scheduled_visual_image_media_items(media_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return scheduled image media items with usable local or remote sources."""
    return [item for item in scheduled_visual_media_items(media_items) if item.get("type") == "image"]


def active_visual_media_at(scheduled_items: list[dict[str, Any]], group_duration: float, local_start_sec: float) -> tuple[dict[str, Any] | None, bool]:
    """Return the scheduled visual media item active at a local group time."""
    local_start = max(0.0, float(local_start_sec or 0.0))
    for item in scheduled_items:
        start, end = group_media_item_local_bounds(item, group_duration)
        if start <= local_start + 0.001 and local_start < end - 0.001:
            return item, True
    return None, bool(scheduled_items)


def active_visual_group_media_at(group: dict[str, Any], media_items: list[dict[str, Any]], local_start_sec: float) -> tuple[dict[str, Any] | None, bool]:
    """Return the scheduled visual media item active at a local group time for normalized group media."""
    group_duration = visual_group_duration_seconds(group)
    return active_visual_media_at(scheduled_visual_media_items(media_items), group_duration, local_start_sec)


def group_media_item_duration(item: dict[str, Any], group_duration: float) -> float:
    """Return a scheduled media item's explicit or group-relative visual duration."""
    try:
        explicit = float(item.get("duration_sec") or item.get("visual_duration_sec") or 0.0)
    except (TypeError, ValueError):
        explicit = 0.0
    if explicit > 0:
        return explicit
    try:
        start = float(item.get("start_offset_sec") or 0.0)
    except (TypeError, ValueError):
        start = 0.0
    return max(0.25, max(0.0, group_duration) - max(0.0, start))


def group_media_item_local_bounds(item: dict[str, Any], group_duration: float) -> tuple[float, float]:
    """Return a scheduled media item's local start/end clamped to the group duration."""
    try:
        item_start = max(0.0, min(group_duration, float(item.get("start_offset_sec") or 0.0)))
    except (TypeError, ValueError):
        item_start = 0.0
    item_end = min(group_duration, item_start + group_media_item_duration(item, group_duration))
    return item_start, item_end


def group_media_local_boundary_absolute_cut(local_cut: float, group_start: float, segment_start: float, segment_end: float) -> float | None:
    """Return a rounded absolute split cut when a local media boundary is strictly inside a segment."""
    absolute_cut = group_start + local_cut
    if segment_start + 0.001 < absolute_cut < segment_end - 0.001:
        return round(absolute_cut, 3)
    return None


def group_media_timeline_boundary_cuts(items: list[dict[str, Any]], group_duration: float, group_start: float, segment_start: float, segment_end: float) -> list[float]:
    """Return absolute segment split cuts for scheduled media item local boundaries."""
    cuts: list[float] = []
    for item in items:
        item_start, item_end = group_media_item_local_bounds(item, group_duration)
        for local_cut in (item_start, item_end):
            absolute_cut = group_media_local_boundary_absolute_cut(local_cut, group_start, segment_start, segment_end)
            if absolute_cut is not None:
                cuts.append(absolute_cut)
    return cuts


def split_range_by_group_media_timeline(start: float, end: float, group: dict[str, Any], group_start: float, points: list[dict[str, float]], media_items: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """Split an export range by speed-envelope and scheduled group-media boundaries."""
    if end <= start:
        return []
    cuts = {round(start, 3), round(end, 3)}
    for seg_start, seg_end in split_range_by_speed_envelope(start, end, points):
        cuts.add(round(seg_start, 3))
        cuts.add(round(seg_end, 3))
    group_duration = visual_group_duration_seconds(group, end - group_start)
    cuts.update(group_media_timeline_boundary_cuts(scheduled_visual_media_items(media_items), group_duration, group_start, start, end))
    return ordered_cuts_to_segments(cuts)


def is_video_source_path(source_path: Any) -> bool:
    """Return whether a visual source path should be treated as looped video input."""
    suffix = getattr(source_path, "suffix", "")
    return str(suffix).lower() in VIDEO_SOURCE_SUFFIXES


def calculate_video_source_offset(selected_media: dict[str, Any] | None, local_start: float) -> float:
    """Return the unwrapped source offset for a selected video media item."""
    if not selected_media:
        return 0.0
    try:
        block_start = float(selected_media.get("start_offset_sec") or 0.0)
    except (TypeError, ValueError):
        block_start = 0.0
    try:
        source_offset = max(0.0, float(selected_media.get("offset_sec") or selected_media.get("source_offset_sec") or 0.0))
    except (TypeError, ValueError):
        source_offset = 0.0
    return source_offset + max(0.0, local_start - block_start)


def parse_video_source_duration(selected_media: dict[str, Any] | None) -> float:
    """Return the explicit source duration for a selected video media item, if available."""
    if not selected_media:
        return 0.0
    try:
        return float(selected_media.get("source_duration_sec") or selected_media.get("video_duration_sec") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def wrap_video_source_offset(source_offset: float, source_duration: float) -> float:
    """Return a loop-safe video source offset when a positive source duration is known."""
    if source_duration > 0.05:
        return source_offset % source_duration
    return source_offset


def visual_segment_source_value(selected_media: dict[str, Any] | None, video_meta: dict[str, Any], image_meta: dict[str, Any]) -> Any:
    """Return the preferred configured source value for a visual export segment."""
    return (selected_media or {}).get("path") or video_meta.get("path") or image_meta.get("path") or ""


def fallback_visual_media_item(media_items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the preferred unscheduled media item for a visual export segment."""
    return next((item for item in media_items if item.get("type") == "video" and item.get("path")), None) or next((item for item in media_items if item.get("path")), None)


def visual_media_item_has_source(item: dict[str, Any]) -> bool:
    """Return whether a media timeline item has a usable local or remote visual source."""
    return bool(item.get("path") or item.get("url"))


def visual_media_timeline_sort_key(item: dict[str, Any]) -> tuple[float, int]:
    """Return the stable ordering key for visual media timeline items."""
    return float(item.get("start_offset_sec") or 0.0), int(item.get("order") or 0)
