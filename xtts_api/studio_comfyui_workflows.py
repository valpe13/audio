import time
from pathlib import Path
from typing import Any, Callable


def make_comfyui_workflow_helpers(ctx: dict[str, Any]) -> dict[str, Callable[..., Any]]:
    active_project_id = ctx["active_project_id"]
    animatediff_environment_diagnostics = ctx["animatediff_environment_diagnostics"]
    animatediff_sdxl_environment_diagnostics = ctx["animatediff_sdxl_environment_diagnostics"]
    animatediff_sdxl_target_dimensions_for_source = ctx["animatediff_sdxl_target_dimensions_for_source"]
    animatediff_target_dimensions_for_source = ctx["animatediff_target_dimensions_for_source"]
    ANIMATEDIFF_MOTION_MODEL = ctx["ANIMATEDIFF_MOTION_MODEL"]
    comfyui_download_image = ctx["comfyui_download_image"]
    comfyui_download_output = ctx["comfyui_download_output"]
    comfyui_first_output_image = ctx["comfyui_first_output_image"]
    comfyui_first_output_video = ctx["comfyui_first_output_video"]
    comfyui_newest_video_by_prefix = ctx["comfyui_newest_video_by_prefix"]
    comfyui_submit_prompt = ctx["comfyui_submit_prompt"]
    comfyui_video_output_suffixes = ctx["comfyui_video_output_suffixes"]
    comfyui_wait_history = ctx["comfyui_wait_history"]
    compile_animatediff_i2v_workflow_base = ctx["compile_animatediff_i2v_workflow_base"]
    compile_animatediff_sdxl_i2v_workflow_base = ctx["compile_animatediff_sdxl_i2v_workflow_base"]
    compile_svd_i2v_workflow_base = ctx["compile_svd_i2v_workflow_base"]
    copy_comfyui_animatediff_video_to_project = ctx["copy_comfyui_animatediff_video_to_project"]
    copy_comfyui_prefix_video_to_project = ctx["copy_comfyui_prefix_video_to_project"]
    format_animatediff_prompt = ctx["format_animatediff_prompt"]
    project_images_dir = ctx["project_images_dir"]
    project_videos_dir = ctx["project_videos_dir"]
    REALVISXL_CHECKPOINT = ctx["REALVISXL_CHECKPOINT"]
    rel_path = ctx["rel_path"]
    resolve_user_path = ctx["resolve_user_path"]
    run_xai_grok_imagine_video_i2v_workflow = ctx["run_xai_grok_imagine_video_i2v_workflow"]
    safe_project_id = ctx["safe_project_id"]
    SVD_HISTORY_WAIT_TIMEOUT_SECONDS = ctx["SVD_HISTORY_WAIT_TIMEOUT_SECONDS"]
    svd_source_dimensions = ctx["svd_source_dimensions"]
    truncate_text = ctx["truncate_text"]
    wait_for_comfyui = ctx["wait_for_comfyui"]

    def run_comfyui_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], prompt_bundle: dict[str, str], workflow: dict[str, Any], output_prefix: str) -> dict[str, Any]:
        wait_for_comfyui(settings, timeout=60.0)
        prompt_id = comfyui_submit_prompt(settings, workflow)
        history_item = comfyui_wait_history(settings, prompt_id, timeout=300.0)
        image_info = comfyui_first_output_image(history_item)
        pid = safe_project_id(str(project.get("id") or active_project_id()))
        out_dir = project_images_dir(pid)
        out = out_dir / f"{output_prefix}_{prompt_id[:10]}.png"
        comfyui_download_image(settings, image_info, out)
        path = rel_path(out)
        return {
            "status": "ready",
            "provider": "comfyui",
            "model": settings.get("model"),
            "model_checkpoint": settings.get("model_checkpoint", ""),
            "aspect_ratio": settings.get("aspect_ratio"),
            "width": int(settings.get("width") or 0),
            "height": int(settings.get("height") or 0),
            "seed": int(settings.get("seed") or 0),
            "path": path,
            "url": f"/api/image?path={path}&v={int(out.stat().st_mtime)}",
            "positive_prompt": prompt_bundle.get("positive_prompt", ""),
            "negative_prompt": prompt_bundle.get("negative_prompt", ""),
            "prompt_id": prompt_id,
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    def animatediff_missing_dependency_error(group: dict[str, Any], video_settings: dict[str, Any]) -> RuntimeError:
        positive = truncate_text(group.get("animation_positive_prompt") or group.get("visual_prompt") or group.get("summary"), 260)
        negative = truncate_text(group.get("animation_negative_prompt") or group.get("negative_prompt"), 220)
        frames = int(video_settings.get("frames") or 16)
        fps = int(video_settings.get("fps") or 8)
        steps = int(video_settings.get("steps") or 20)
        cfg = float(video_settings.get("cfg") or 7.0)
        return RuntimeError(
            "AnimateDiff backend is selectable as an experimental option, but generated output is guarded because XTTS Studio "
            "cannot safely infer the installed ComfyUI AnimateDiff-Evolved node class names, loader inputs, ControlNet/IPAdapter "
            "stack, and motion model names from this environment. Keep Workflow=generated_svd for the current working SVD-XT path, "
            "or install ComfyUI-AnimateDiff-Evolved and VideoHelperSuite, place a motion module such as mm_sd_v15_v2.ckpt or "
            "temporaldiff-v1-animatediff.ckpt under ComfyUI/models/animatediff_models, then validate a custom AnimateDiff "
            "workflow in ComfyUI before wiring it into XTTS Studio. For object motion, use prompts like locked camera, static camera, "
            "no camera movement, objects move naturally, leaves swaying, water ripples, smoke drifting; negative terms should include "
            "camera pan, camera zoom, camera orbit, dolly, drift, whole image moving. "
            f"Prepared AnimateDiff inputs from this group: frames={frames}, fps={fps}, steps={steps}, cfg={cfg}, "
            f"positive_prompt='{positive}', negative_prompt='{negative}'."
        )

    def run_comfyui_animatediff_i2v_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], output_prefix: str) -> dict[str, Any]:
        image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
        source_path = resolve_user_path(image_meta.get("path")) if image_meta.get("path") else None
        if not source_path or not source_path.exists():
            raise RuntimeError("Generate the group image before AnimateDiff image-to-video")
        wait_for_comfyui(settings, timeout=60.0)
        diagnostics = animatediff_environment_diagnostics(settings)
        if not diagnostics.get("ready"):
            raise RuntimeError("AnimateDiff is not ready: " + " | ".join(str(item) for item in diagnostics.get("blockers", [])))
        sd15_checkpoint = str(diagnostics.get("selected_sd15_checkpoint") or "")
        motion_model = str(diagnostics.get("selected_motion_model") or ANIMATEDIFF_MOTION_MODEL)
        workflow = compile_animatediff_i2v_workflow_base(settings, video_settings, group, source_path, output_prefix, sd15_checkpoint, motion_model, image_meta, svd_source_dimensions=svd_source_dimensions, animatediff_target_dimensions_for_source=animatediff_target_dimensions_for_source, format_animatediff_prompt=format_animatediff_prompt)
        submitted_at = time.time()
        prompt_id = comfyui_submit_prompt(settings, workflow)
        try:
            history_item = comfyui_wait_history(settings, prompt_id, timeout=SVD_HISTORY_WAIT_TIMEOUT_SECONDS)
        except RuntimeError:
            fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
            if fallback_output and fallback_output.exists():
                return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, fallback_output, prompt_id, sd15_checkpoint, motion_model)
            raise
        try:
            video_info = comfyui_first_output_video(history_item)
        except RuntimeError:
            fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
            if not fallback_output:
                raise
            video_info = {"filename": fallback_output.name, "subfolder": rel_path(fallback_output.parent), "type": "output"}
        pid = safe_project_id(str(project.get("id") or active_project_id()))
        out_dir = project_videos_dir(pid)
        suffix = Path(video_info.get("filename") or "").suffix.lower()
        out = out_dir / f"{output_prefix}_{prompt_id[:10]}{suffix if suffix in comfyui_video_output_suffixes() else '.mp4'}"
        try:
            comfyui_download_output(settings, video_info, out)
        except Exception:
            fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
            if not fallback_output or not fallback_output.exists():
                raise
            return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, fallback_output, prompt_id, sd15_checkpoint, motion_model)
        return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, out, prompt_id, sd15_checkpoint, motion_model)

    def run_comfyui_animatediff_sdxl_i2v_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], output_prefix: str) -> dict[str, Any]:
        image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
        source_path = resolve_user_path(image_meta.get("path")) if image_meta.get("path") else None
        if not source_path or not source_path.exists():
            raise RuntimeError("Generate the group image before HotshotXL / AnimateDiff SDXL image-to-video")
        wait_for_comfyui(settings, timeout=60.0)
        diagnostics = animatediff_sdxl_environment_diagnostics(settings)
        if not diagnostics.get("ready"):
            raise RuntimeError("HotshotXL / AnimateDiff SDXL is not ready: " + " | ".join(str(item) for item in diagnostics.get("blockers", [])))
        sdxl_checkpoint = str(diagnostics.get("selected_sdxl_checkpoint") or REALVISXL_CHECKPOINT)
        motion_model = str(diagnostics.get("selected_motion_model") or "")
        workflow = compile_animatediff_sdxl_i2v_workflow_base(settings, video_settings, group, source_path, output_prefix, sdxl_checkpoint, motion_model, image_meta, svd_source_dimensions=svd_source_dimensions, animatediff_sdxl_target_dimensions_for_source=animatediff_sdxl_target_dimensions_for_source, format_animatediff_prompt=format_animatediff_prompt)
        submitted_at = time.time()
        prompt_id = comfyui_submit_prompt(settings, workflow)
        try:
            history_item = comfyui_wait_history(settings, prompt_id, timeout=SVD_HISTORY_WAIT_TIMEOUT_SECONDS)
        except RuntimeError:
            fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
            if fallback_output and fallback_output.exists():
                return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, fallback_output, prompt_id, sdxl_checkpoint, motion_model, model_name="hotshotxl_sdxl")
            raise
        try:
            video_info = comfyui_first_output_video(history_item)
        except RuntimeError:
            fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
            if not fallback_output:
                raise
            video_info = {"filename": fallback_output.name, "subfolder": rel_path(fallback_output.parent), "type": "output"}
        pid = safe_project_id(str(project.get("id") or active_project_id()))
        out_dir = project_videos_dir(pid)
        suffix = Path(video_info.get("filename") or "").suffix.lower()
        out = out_dir / f"{output_prefix}_{prompt_id[:10]}{suffix if suffix in comfyui_video_output_suffixes() else '.mp4'}"
        try:
            comfyui_download_output(settings, video_info, out)
        except Exception:
            fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
            if not fallback_output or not fallback_output.exists():
                raise
            return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, fallback_output, prompt_id, sdxl_checkpoint, motion_model, model_name="hotshotxl_sdxl")
        return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, out, prompt_id, sdxl_checkpoint, motion_model, model_name="hotshotxl_sdxl")

    def run_comfyui_video_i2v_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], output_prefix: str) -> dict[str, Any]:
        workflow_mode = str(video_settings.get("workflow_mode") or "generated_svd").strip().lower()
        if workflow_mode == "generated_grok_imagine_video":
            return run_xai_grok_imagine_video_i2v_workflow(project, group, settings, video_settings, output_prefix)
        if workflow_mode == "generated_animatediff":
            return run_comfyui_animatediff_i2v_workflow(project, group, settings, video_settings, output_prefix)
        if workflow_mode == "generated_hotshotxl":
            return run_comfyui_animatediff_sdxl_i2v_workflow(project, group, settings, video_settings, output_prefix)
        return run_comfyui_svd_i2v_workflow(project, group, settings, video_settings, output_prefix)

    def run_comfyui_svd_i2v_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], output_prefix: str) -> dict[str, Any]:
        image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
        source_path = resolve_user_path(image_meta.get("path")) if image_meta.get("path") else None
        if not source_path or not source_path.exists():
            raise RuntimeError("Generate the group image before SVD/SVD-XT image-to-video")
        wait_for_comfyui(settings, timeout=60.0)
        width, height = svd_source_dimensions(settings, image_meta)
        workflow = compile_svd_i2v_workflow_base(settings, video_settings, source_path, output_prefix, image_meta, svd_source_dimensions=svd_source_dimensions)
        submitted_at = time.time()
        prompt_id = comfyui_submit_prompt(settings, workflow)
        try:
            history_item = comfyui_wait_history(settings, prompt_id, timeout=SVD_HISTORY_WAIT_TIMEOUT_SECONDS)
        except RuntimeError:
            fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
            if fallback_output and fallback_output.exists():
                return copy_comfyui_prefix_video_to_project(project, settings, video_settings, group, output_prefix, fallback_output, prompt_id)
            raise
        try:
            video_info = comfyui_first_output_video(history_item)
        except RuntimeError:
            fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
            if not fallback_output:
                raise
            video_info = {"filename": fallback_output.name, "subfolder": rel_path(fallback_output.parent), "type": "output"}
        pid = safe_project_id(str(project.get("id") or active_project_id()))
        out_dir = project_videos_dir(pid)
        source_suffix = Path(video_info.get("filename") or "").suffix.lower()
        suffix = source_suffix if source_suffix in {".mp4", ".webm", ".gif"} else ".mp4"
        out = out_dir / f"{output_prefix}_{prompt_id[:10]}{suffix}"
        fallback_source = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
        try:
            comfyui_download_output(settings, video_info, out)
        except Exception:
            if not fallback_source or not fallback_source.exists():
                raise
            return copy_comfyui_prefix_video_to_project(project, settings, video_settings, group, output_prefix, fallback_source, prompt_id)
        path = rel_path(out)
        frames = int(video_settings.get("frames") or 0)
        fps = int(video_settings.get("fps") or 0)
        pingpong = bool(video_settings.get("pingpong", True))
        loop_count = max(0, int(video_settings.get("loop_count") or 0))
        output_fps = max(1, int(video_settings.get("output_fps") or fps or 1))
        single_loop_frames = max(0, frames * 2 - 2) if pingpong and frames > 1 else frames
        output_frames = single_loop_frames * (loop_count + 1)
        duration_sec = round(output_frames / float(output_fps), 3) if output_fps > 0 and output_frames > 0 else 0.0
        return {
            "status": "ready",
            "provider": "comfyui",
            "model": "svd_xt" if "xt" in str(video_settings.get("model_checkpoint") or "").lower() else "svd",
            "model_checkpoint": video_settings.get("model_checkpoint", ""),
            "motion_style": str(video_settings.get("motion_style") or ""),
            "width": width,
            "height": height,
            "seed": int(settings.get("seed") or 0),
            "frames": frames,
            "fps": fps,
            "output_fps": output_fps,
            "output_frames": output_frames,
            "loop_count": loop_count,
            "target_duration_sec": float(video_settings.get("target_duration_sec") or 0.0),
            "duration_sec": duration_sec,
            "loop": True,
            "pingpong": pingpong,
            "motion_bucket_id": int(video_settings.get("motion_bucket_id") or 0),
            "augmentation_level": float(video_settings.get("augmentation_level") or 0.0),
            "min_cfg": float(video_settings.get("min_cfg") or 0.0),
            "cfg": float(video_settings.get("cfg") or 0.0),
            "steps": int(video_settings.get("steps") or 0),
            "source_image_path": rel_path(source_path),
            "path": path,
            "url": f"/api/video?path={path}&v={int(out.stat().st_mtime)}",
            "prompt_id": prompt_id,
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    return {
        "animatediff_missing_dependency_error": animatediff_missing_dependency_error,
        "run_comfyui_animatediff_i2v_workflow": run_comfyui_animatediff_i2v_workflow,
        "run_comfyui_animatediff_sdxl_i2v_workflow": run_comfyui_animatediff_sdxl_i2v_workflow,
        "run_comfyui_svd_i2v_workflow": run_comfyui_svd_i2v_workflow,
        "run_comfyui_video_i2v_workflow": run_comfyui_video_i2v_workflow,
        "run_comfyui_workflow": run_comfyui_workflow,
    }
