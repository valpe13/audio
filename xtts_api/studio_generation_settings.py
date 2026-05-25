from __future__ import annotations

import time
from typing import Any

try:
    from studio_json_helpers import bounded_float_setting, bounded_int_setting, preset_bounded_float_setting, preset_bounded_int_setting
    from studio_prompt_helpers import clamp_image_dimension, image_preset_dimensions, image_seed_value, normalize_grok_image_model, normalize_grok_image_resolution, normalize_image_dimensions_for_orientation, normalize_image_model, normalize_image_provider, truncate_text
    from studio_video_geometry import grok_imagine_video_aspect_ratio_mode, grok_imagine_video_loop_postprocess_mode, grok_imagine_video_resolution, video_i2v_enabled, video_i2v_grok_crossfade_sec, video_i2v_grok_duration_sec, video_i2v_grok_options, video_i2v_identity_options, video_i2v_loop_output_options, video_i2v_min_cfg_value, video_i2v_model_names, video_i2v_motion_style, video_i2v_pingpong_enabled, video_i2v_quality_preset, video_i2v_sampler_scheduler_options, video_i2v_style_numeric_options, video_i2v_svd_return_options, video_i2v_target_duration_sec, video_i2v_workflow_mode
except ImportError:  # pragma: no cover - package-style imports
    from .studio_json_helpers import bounded_float_setting, bounded_int_setting, preset_bounded_float_setting, preset_bounded_int_setting
    from .studio_prompt_helpers import clamp_image_dimension, image_preset_dimensions, image_seed_value, normalize_grok_image_model, normalize_grok_image_resolution, normalize_image_dimensions_for_orientation, normalize_image_model, normalize_image_provider, truncate_text
    from .studio_video_geometry import grok_imagine_video_aspect_ratio_mode, grok_imagine_video_loop_postprocess_mode, grok_imagine_video_resolution, video_i2v_enabled, video_i2v_grok_crossfade_sec, video_i2v_grok_duration_sec, video_i2v_grok_options, video_i2v_identity_options, video_i2v_loop_output_options, video_i2v_min_cfg_value, video_i2v_model_names, video_i2v_motion_style, video_i2v_pingpong_enabled, video_i2v_quality_preset, video_i2v_sampler_scheduler_options, video_i2v_style_numeric_options, video_i2v_svd_return_options, video_i2v_target_duration_sec, video_i2v_workflow_mode


def image_settings(
    project: dict[str, Any],
    *,
    default_settings: dict[str, Any],
    image_quality_presets: dict[str, Any],
    realvisxl_checkpoint: str,
    grok_image_model: str,
    legacy_grok_image_models: list[str],
    grok_image_resolutions: list[str],
) -> dict[str, Any]:
    raw = project.get("settings", {}) if isinstance(project.get("settings"), dict) else {}
    provider = normalize_image_provider(raw.get("image_provider"), str(default_settings["image_provider"]))
    model = normalize_image_model(raw.get("image_model"), provider, raw.get("image_model_checkpoint") or default_settings["image_model_checkpoint"], realvisxl_checkpoint, str(default_settings["image_model"]))
    quality_preset, aspect_ratio, default_width, default_height = image_preset_dimensions(
        raw.get("image_quality_preset") or default_settings["image_quality_preset"],
        raw.get("image_aspect_ratio") or default_settings["image_aspect_ratio"],
        image_quality_presets,
    )
    preset = image_quality_presets[quality_preset]
    try:
        width = int(raw.get("image_width") or default_width)
        height = int(raw.get("image_height") or default_height)
    except (TypeError, ValueError):
        width, height = default_width, default_height
    width, height = default_width, default_height
    width, height = normalize_image_dimensions_for_orientation(width, height, aspect_ratio)
    seed = image_seed_value(raw.get("image_seed"))
    if seed <= 0:
        seed = int(time.time() * 1000) % 2147483647
    workflow_mode = str(raw.get("image_workflow_mode") or default_settings["image_workflow_mode"]).strip().lower()
    if workflow_mode not in {"generated", "template", "disabled"}:
        workflow_mode = "generated"
    try:
        steps = int(raw.get("image_steps") or default_settings["image_steps"])
    except (TypeError, ValueError):
        steps = int(default_settings["image_steps"])
    try:
        cfg = float(raw.get("image_cfg") or default_settings["image_cfg"])
    except (TypeError, ValueError):
        cfg = float(default_settings["image_cfg"])
    steps = int(preset["steps"])
    cfg = float(preset["cfg"])
    sampler = str(preset["sampler"])
    scheduler = str(preset["scheduler"])
    return {
        "provider": provider,
        "model": model,
        "grok_model": normalize_grok_image_model(raw.get("image_grok_model") or default_settings["image_grok_model"], grok_image_model, legacy_grok_image_models),
        "grok_resolution": normalize_grok_image_resolution(raw.get("image_grok_resolution"), str(default_settings["image_grok_resolution"]), grok_image_resolutions),
        "quality_preset": quality_preset,
        "aspect_ratio": aspect_ratio,
        "width": clamp_image_dimension(width),
        "height": clamp_image_dimension(height),
        "style_preset": str(raw.get("image_style_preset") or default_settings["image_style_preset"]).strip(),
        "comfyui_url": str(raw.get("image_comfyui_url") or default_settings["image_comfyui_url"]).strip().rstrip("/"),
        "comfyui_path": str(raw.get("image_comfyui_path") or default_settings["image_comfyui_path"]).strip(),
        "comfyui_python": str(raw.get("image_comfyui_python") or default_settings["image_comfyui_python"]).strip(),
        "comfyui_launch_cmd": str(raw.get("image_comfyui_launch_cmd") or default_settings["image_comfyui_launch_cmd"]).strip(),
        "comfyui_autostart": bool(raw.get("image_comfyui_autostart", default_settings["image_comfyui_autostart"])),
        "workflow_mode": workflow_mode,
        "workflow_path": str(raw.get("image_workflow_path") or "").strip(),
        "model_checkpoint": str(raw.get("image_model_checkpoint") or default_settings["image_model_checkpoint"] or realvisxl_checkpoint).strip(),
        "negative_preset": str(raw.get("image_negative_preset") or default_settings["image_negative_preset"]).strip().lower(),
        "seed": seed,
        "exclude_people": bool(raw.get("image_exclude_people", default_settings["image_exclude_people"])),
        "no_text": bool(raw.get("image_no_text", default_settings["image_no_text"])),
        "project_visual_context": truncate_text(raw.get("project_visual_context"), 1400),
        "steps": max(1, min(150, steps)),
        "cfg": max(0.0, min(30.0, cfg)),
        "sampler": sampler,
        "scheduler": scheduler,
    }


def video_i2v_settings(
    project: dict[str, Any],
    *,
    default_settings: dict[str, Any],
    video_i2v_quality_presets: dict[str, Any],
    video_i2v_motion_style_presets: dict[str, Any],
    grok_imagine_video_resolution_presets: dict[str, Any],
    grok_imagine_video_confirmed_resolutions: list[str],
    grok_imagine_video_model: str,
) -> dict[str, Any]:
    raw = project.get("settings", {}) if isinstance(project.get("settings"), dict) else {}
    workflow_mode = video_i2v_workflow_mode(raw.get("video_i2v_workflow_mode") or default_settings["video_i2v_workflow_mode"])
    quality_preset = video_i2v_quality_preset(raw.get("video_i2v_quality_preset") or default_settings["video_i2v_quality_preset"], video_i2v_quality_presets)
    preset = video_i2v_quality_presets[quality_preset]
    motion_style = video_i2v_motion_style(raw.get("video_i2v_motion_style") or default_settings["video_i2v_motion_style"], video_i2v_motion_style_presets)
    style_preset = video_i2v_motion_style_presets[motion_style]
    def int_setting(key: str, min_value: int, max_value: int) -> int:
        return preset_bounded_int_setting(raw, preset, key, int(default_settings[key]), min_value=min_value, max_value=max_value)
    def float_setting(key: str, min_value: float, max_value: float) -> float:
        return preset_bounded_float_setting(raw, preset, key, float(default_settings[key]), min_value=min_value, max_value=max_value)
    svd_numeric_options = video_i2v_style_numeric_options(style_preset, int_setting, float_setting)
    frames = svd_numeric_options["frames"]
    fps = svd_numeric_options["fps"]
    target_duration_sec = video_i2v_target_duration_sec(bounded_float_setting(raw, "video_i2v_target_duration_sec", float(default_settings["video_i2v_target_duration_sec"]), min_value=2.0, max_value=60.0))
    grok_options = video_i2v_grok_options(
        video_i2v_grok_duration_sec(bounded_int_setting(raw, "video_i2v_grok_duration_sec", int(default_settings["video_i2v_grok_duration_sec"]), min_value=1, max_value=30)),
        grok_imagine_video_resolution(raw.get("video_i2v_grok_resolution"), quality_preset, grok_imagine_video_resolution_presets, grok_imagine_video_confirmed_resolutions),
        grok_imagine_video_aspect_ratio_mode(raw.get("video_i2v_grok_aspect_ratio_mode"), default=str(default_settings["video_i2v_grok_aspect_ratio_mode"])),
        grok_imagine_video_loop_postprocess_mode(raw.get("video_i2v_grok_loop_postprocess"), default=str(default_settings["video_i2v_grok_loop_postprocess"])),
        video_i2v_grok_crossfade_sec(bounded_float_setting(raw, "video_i2v_grok_crossfade_sec", float(default_settings["video_i2v_grok_crossfade_sec"]), min_value=0.1, max_value=2.0)),
    )
    pingpong = video_i2v_pingpong_enabled(raw, default=bool(default_settings["video_i2v_pingpong"]))
    loop_output_options = video_i2v_loop_output_options(target_duration_sec, frames, fps, pingpong=pingpong)
    preset_string_options = video_i2v_sampler_scheduler_options(preset, default_settings)
    model_names = video_i2v_model_names(
        raw,
        default_checkpoint=str(default_settings["video_i2v_model_checkpoint"]),
        default_grok_model=grok_imagine_video_model,
    )
    svd_return_options = video_i2v_svd_return_options(
        svd_numeric_options,
        video_i2v_min_cfg_value(float_setting("video_i2v_min_cfg", 0.0, 30.0)),
        preset_string_options,
    )
    identity_options = video_i2v_identity_options(
        video_i2v_enabled(raw, default=bool(default_settings["video_i2v_enabled"])),
        quality_preset,
        motion_style,
        workflow_mode,
    )
    return {
        **identity_options,
        **model_names,
        **grok_options,
        "grok_resolution_options": grok_imagine_video_resolution_presets,
        **svd_return_options,
        "pingpong": pingpong,
        "target_duration_sec": target_duration_sec,
        **loop_output_options,
    }
