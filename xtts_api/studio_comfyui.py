import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable


def animatediff_target_dimensions(settings: dict[str, Any], image_meta: dict[str, Any] | None, svd_source_dimensions: Callable[[dict[str, Any], dict[str, Any] | None], tuple[int, int]], animatediff_target_dimensions_for_source: Callable[[int, int], tuple[int, int]]) -> tuple[int, int]:
    width, height = svd_source_dimensions(settings, image_meta)
    return animatediff_target_dimensions_for_source(width, height)


def compile_animatediff_i2v_workflow(
    settings: dict[str, Any],
    video_settings: dict[str, Any],
    group: dict[str, Any],
    source_image_path: Path,
    output_prefix: str,
    sd15_checkpoint: str,
    motion_model: str,
    image_meta: dict[str, Any] | None,
    *,
    svd_source_dimensions: Callable[[dict[str, Any], dict[str, Any] | None], tuple[int, int]],
    animatediff_target_dimensions_for_source: Callable[[int, int], tuple[int, int]],
    format_animatediff_prompt: Callable[[dict[str, Any]], dict[str, str]],
) -> dict[str, Any]:
    width, height = animatediff_target_dimensions(settings, image_meta, svd_source_dimensions, animatediff_target_dimensions_for_source)
    frames = max(2, min(64, int(video_settings.get("frames") or 16)))
    fps = max(1, min(24, int(video_settings.get("fps") or 8)))
    prompt = format_animatediff_prompt(group)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": sd15_checkpoint}},
        "2": {"class_type": "LoadImage", "inputs": {"image": str(source_image_path)}},
        "3": {"class_type": "ImageScale", "inputs": {"image": ["2", 0], "upscale_method": "lanczos", "width": width, "height": height, "crop": "center"}},
        "4": {"class_type": "RepeatImageBatch", "inputs": {"image": ["3", 0], "amount": frames}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt["positive_prompt"], "clip": ["1", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt["negative_prompt"], "clip": ["1", 1]}},
        "8": {"class_type": "ADE_LoadAnimateDiffModel", "inputs": {"model_name": motion_model}},
        "9": {"class_type": "ADE_ApplyAnimateDiffModelSimple", "inputs": {"motion_model": ["8", 0]}},
        "10": {"class_type": "ADE_UseEvolvedSampling", "inputs": {"model": ["1", 0], "beta_schedule": "autoselect", "m_models": ["9", 0]}},
        "11": {"class_type": "KSampler", "inputs": {"seed": int(settings.get("seed") or 1), "steps": int(video_settings.get("steps") or 20), "cfg": float(video_settings.get("cfg") or 7.0), "sampler_name": str(video_settings.get("sampler") or "euler"), "scheduler": str(video_settings.get("scheduler") or "normal"), "denoise": 0.72, "model": ["10", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["1", 2]}},
        "13": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["12", 0], "frame_rate": fps, "loop_count": max(0, min(30, int(video_settings.get("loop_count") or 0))), "filename_prefix": output_prefix, "format": "video/h264-mp4", "pingpong": bool(video_settings.get("pingpong", True)), "save_output": True}},
    }


def animatediff_sdxl_target_dimensions(settings: dict[str, Any], image_meta: dict[str, Any] | None, svd_source_dimensions: Callable[[dict[str, Any], dict[str, Any] | None], tuple[int, int]], animatediff_sdxl_target_dimensions_for_source: Callable[[int, int], tuple[int, int]]) -> tuple[int, int]:
    width, height = svd_source_dimensions(settings, image_meta)
    return animatediff_sdxl_target_dimensions_for_source(width, height)


def compile_animatediff_sdxl_i2v_workflow(
    settings: dict[str, Any],
    video_settings: dict[str, Any],
    group: dict[str, Any],
    source_image_path: Path,
    output_prefix: str,
    sdxl_checkpoint: str,
    motion_model: str,
    image_meta: dict[str, Any] | None,
    *,
    svd_source_dimensions: Callable[[dict[str, Any], dict[str, Any] | None], tuple[int, int]],
    animatediff_sdxl_target_dimensions_for_source: Callable[[int, int], tuple[int, int]],
    format_animatediff_prompt: Callable[[dict[str, Any]], dict[str, str]],
) -> dict[str, Any]:
    width, height = animatediff_sdxl_target_dimensions(settings, image_meta, svd_source_dimensions, animatediff_sdxl_target_dimensions_for_source)
    frames = max(2, min(32, int(video_settings.get("frames") or 16)))
    fps = max(1, min(16, int(video_settings.get("fps") or 8)))
    prompt = format_animatediff_prompt(group)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": sdxl_checkpoint}},
        "2": {"class_type": "LoadImage", "inputs": {"image": str(source_image_path)}},
        "3": {"class_type": "ImageScale", "inputs": {"image": ["2", 0], "upscale_method": "lanczos", "width": width, "height": height, "crop": "center"}},
        "4": {"class_type": "RepeatImageBatch", "inputs": {"image": ["3", 0], "amount": frames}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt["positive_prompt"], "clip": ["1", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt["negative_prompt"], "clip": ["1", 1]}},
        "8": {"class_type": "ADE_LoadAnimateDiffModel", "inputs": {"model_name": motion_model}},
        "9": {"class_type": "ADE_ApplyAnimateDiffModelSimple", "inputs": {"motion_model": ["8", 0]}},
        "10": {"class_type": "ADE_UseEvolvedSampling", "inputs": {"model": ["1", 0], "beta_schedule": "autoselect", "m_models": ["9", 0]}},
        "11": {"class_type": "KSampler", "inputs": {"seed": int(settings.get("seed") or 1), "steps": int(video_settings.get("steps") or 16), "cfg": min(6.0, float(video_settings.get("cfg") or 5.0)), "sampler_name": str(video_settings.get("sampler") or "euler"), "scheduler": str(video_settings.get("scheduler") or "normal"), "denoise": 0.68, "model": ["10", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["1", 2]}},
        "13": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["12", 0], "frame_rate": fps, "loop_count": max(0, min(30, int(video_settings.get("loop_count") or 0))), "filename_prefix": output_prefix, "format": "video/h264-mp4", "pingpong": bool(video_settings.get("pingpong", True)), "save_output": True}},
    }


def compile_svd_i2v_workflow(
    settings: dict[str, Any],
    video_settings: dict[str, Any],
    source_image_path: Path,
    output_prefix: str,
    image_meta: dict[str, Any] | None = None,
    *,
    svd_source_dimensions: Callable[[dict[str, Any], dict[str, Any] | None], tuple[int, int]],
) -> dict[str, Any]:
    checkpoint = str(video_settings.get("model_checkpoint") or "").strip()
    if not checkpoint:
        raise RuntimeError("SVD/SVD-XT checkpoint is not configured; set video_i2v_model_checkpoint")
    width, height = svd_source_dimensions(settings, image_meta)
    pingpong = bool(video_settings.get("pingpong", True))
    output_fps = max(1, int(video_settings.get("output_fps") or video_settings.get("fps") or 6))
    loop_count = max(0, min(30, int(video_settings.get("loop_count") or 0)))
    return {
        "1": {"class_type": "ImageOnlyCheckpointLoader", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "LoadImage", "inputs": {"image": str(source_image_path)}},
        "3": {"class_type": "SVD_img2vid_Conditioning", "inputs": {
            "width": width,
            "height": height,
            "video_frames": int(video_settings.get("frames") or 25),
            "motion_bucket_id": int(video_settings.get("motion_bucket_id") or 127),
            "fps": int(video_settings.get("fps") or 6),
            "augmentation_level": float(video_settings.get("augmentation_level") or 0.02),
            "clip_vision": ["1", 1],
            "init_image": ["2", 0],
            "vae": ["1", 2],
        }},
        "4": {"class_type": "KSampler", "inputs": {
            "seed": int(settings.get("seed") or 1),
            "steps": int(video_settings.get("steps") or 20),
            "cfg": float(video_settings.get("cfg") or 2.5),
            "sampler_name": str(video_settings.get("sampler") or "euler"),
            "scheduler": str(video_settings.get("scheduler") or "normal"),
            "denoise": 1.0,
            "model": ["1", 0],
            "positive": ["3", 0],
            "negative": ["3", 1],
            "latent_image": ["3", 2],
        }},
        "5": {"class_type": "VAEDecode", "inputs": {"samples": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "VHS_VideoCombine", "inputs": {
            "images": ["5", 0],
            "frame_rate": output_fps,
            "loop_count": loop_count,
            "filename_prefix": output_prefix,
            "format": "video/h264-mp4",
            "pingpong": pingpong,
            "save_output": True,
        }},
    }


def make_comfyui_helpers(ctx: dict[str, Any]) -> dict[str, Callable[..., Any]]:
    root = ctx["ROOT"]
    default_settings = ctx["DEFAULT_SETTINGS"]
    realvisxl_checkpoint = ctx["REALVISXL_CHECKPOINT"]
    animatediff_motion_model = ctx["ANIMATEDIFF_MOTION_MODEL"]
    animatediff_sdxl_env_model = ctx["ANIMATEDIFF_SDXL_ENV_MODEL"]
    animatediff_sdxl_model_candidates = ctx["ANIMATEDIFF_SDXL_MODEL_CANDIDATES"]
    resolve_user_path = ctx["resolve_user_path"]
    rel_path = ctx["rel_path"]
    truncate_text = ctx["truncate_text"]
    animatediff_motion_model_suffixes = ctx["animatediff_motion_model_suffixes"]
    animatediff_required_node_names = ctx["animatediff_required_node_names"]
    animatediff_sdxl_optional_node_names = ctx["animatediff_sdxl_optional_node_names"]
    animatediff_missing_node_names = ctx["animatediff_missing_node_names"]
    animatediff_combined_node_names = ctx["animatediff_combined_node_names"]
    comfyui_node_inputs_for_object_info = ctx["comfyui_node_inputs_for_object_info"]
    looks_like_sd15_checkpoint = ctx["looks_like_sd15_checkpoint"]
    looks_like_sdxl_checkpoint = ctx["looks_like_sdxl_checkpoint"]
    looks_like_sdxl_motion_model = ctx["looks_like_sdxl_motion_model"]
    format_missing_comfyui_nodes_blocker = ctx["format_missing_comfyui_nodes_blocker"]
    format_comfyui_object_info_unavailable_blocker = ctx["format_comfyui_object_info_unavailable_blocker"]
    format_missing_sd15_motion_model_blocker = ctx["format_missing_sd15_motion_model_blocker"]
    format_missing_sd15_checkpoint_blocker = ctx["format_missing_sd15_checkpoint_blocker"]
    format_missing_sdxl_checkpoint_blocker = ctx["format_missing_sdxl_checkpoint_blocker"]
    format_missing_sdxl_motion_model_blocker = ctx["format_missing_sdxl_motion_model_blocker"]
    format_incompatible_sdxl_motion_model_blocker = ctx["format_incompatible_sdxl_motion_model_blocker"]
    format_optional_sdxl_helper_nodes_warning = ctx["format_optional_sdxl_helper_nodes_warning"]
    format_experimental_sdxl_path_warning = ctx["format_experimental_sdxl_path_warning"]

    def comfyui_url(settings: dict[str, Any]) -> str:
        return str(settings.get("comfyui_url") or default_settings["image_comfyui_url"]).strip().rstrip("/")

    def http_json_request(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 10.0) -> Any:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}

    def comfyui_health(settings: dict[str, Any]) -> dict[str, Any]:
        base_url = comfyui_url(settings)
        last_error = ""
        for endpoint in ("/system_stats", "/queue"):
            try:
                data = http_json_request(f"{base_url}{endpoint}", timeout=2.0)
                return {"running": True, "url": base_url, "endpoint": endpoint, "data": data, "error": ""}
            except Exception as exc:
                last_error = str(exc)
        return {"running": False, "url": base_url, "endpoint": "", "data": None, "error": last_error}

    def comfyui_model_check(settings: dict[str, Any]) -> dict[str, str]:
        checkpoint = str(settings.get("model_checkpoint") or "").strip()
        if not checkpoint:
            return {"model_checkpoint": "", "model_check": "unknown", "note": "Checkpoint is not configured"}
        comfy_root = resolve_user_path(str(settings.get("comfyui_path") or default_settings["image_comfyui_path"]))
        if not comfy_root:
            return {"model_checkpoint": checkpoint, "model_check": "configured", "note": "Checkpoint name configured; path not resolved"}
        exact_path = comfy_root / "ComfyUI" / "models" / "checkpoints" / checkpoint
        alt_path = comfy_root / "models" / "checkpoints" / checkpoint
        if exact_path.exists() or alt_path.exists():
            return {"model_checkpoint": checkpoint, "model_check": "configured", "note": "Checkpoint exact path exists"}
        return {"model_checkpoint": checkpoint, "model_check": "missing_exact_path", "note": "Checkpoint configured but exact expected path was not found; no directory scan performed"}

    def comfyui_models_dir(settings: dict[str, Any], subdir: str) -> Path | None:
        comfy_root = resolve_user_path(str(settings.get("comfyui_path") or default_settings["image_comfyui_path"]))
        if not comfy_root:
            return None
        for candidate in (comfy_root / "ComfyUI" / "models" / subdir, comfy_root / "models" / subdir):
            if candidate.exists():
                return candidate
        return comfy_root / "ComfyUI" / "models" / subdir

    def comfyui_model_files(settings: dict[str, Any], subdir: str, suffixes: tuple[str, ...]) -> list[str]:
        models_dir = comfyui_models_dir(settings, subdir)
        if not models_dir or not models_dir.exists():
            return []
        return sorted([str(path.relative_to(models_dir)).replace("\\", "/") for path in models_dir.rglob("*") if path.is_file() and path.suffix.lower() in suffixes], key=str.lower)

    def find_sd15_checkpoint(settings: dict[str, Any]) -> str:
        checkpoints = comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt"))
        configured = str(settings.get("animatediff_sd15_checkpoint") or os.environ.get("XTTS_ANIMATEDIFF_SD15_CHECKPOINT") or "").strip()
        if configured and configured in checkpoints:
            return configured
        return next((checkpoint for checkpoint in checkpoints if looks_like_sd15_checkpoint(checkpoint)), "")

    def find_sdxl_checkpoint(settings: dict[str, Any]) -> str:
        checkpoints = comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt"))
        configured = str(settings.get("model_checkpoint") or os.environ.get("XTTS_ANIMATEDIFF_SDXL_CHECKPOINT") or realvisxl_checkpoint).strip()
        if configured and configured in checkpoints:
            return configured
        return next((checkpoint for checkpoint in checkpoints if looks_like_sdxl_checkpoint(checkpoint)), "")

    def find_sdxl_motion_model(settings: dict[str, Any]) -> str:
        motion_models = comfyui_model_files(settings, "animatediff_models", animatediff_motion_model_suffixes())
        configured = str(os.environ.get(animatediff_sdxl_env_model) or "").strip()
        if configured and configured in motion_models:
            return configured
        for candidate in animatediff_sdxl_model_candidates:
            if candidate in motion_models:
                return candidate
        return next((model for model in motion_models if looks_like_sdxl_motion_model(model)), "")

    def animatediff_node_diagnostics(settings: dict[str, Any]) -> dict[str, Any]:
        required_nodes = animatediff_required_node_names()
        try:
            object_info = http_json_request(f"{comfyui_url(settings)}/object_info", timeout=5.0)
            return {"object_info_available": True, "object_info_error": "", "required_nodes": required_nodes, "missing_nodes": animatediff_missing_node_names(object_info, required_nodes), "node_inputs": comfyui_node_inputs_for_object_info(object_info, required_nodes)}
        except Exception as exc:
            return {"object_info_available": False, "object_info_error": str(exc), "required_nodes": required_nodes, "missing_nodes": required_nodes, "node_inputs": {}}

    def animatediff_environment_diagnostics(settings: dict[str, Any]) -> dict[str, Any]:
        checkpoints = comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt"))
        motion_models = comfyui_model_files(settings, "animatediff_models", animatediff_motion_model_suffixes())
        selected_sd15 = find_sd15_checkpoint(settings)
        selected_motion = animatediff_motion_model if animatediff_motion_model in motion_models else ""
        nodes = animatediff_node_diagnostics(settings)
        blockers: list[str] = []
        if nodes.get("object_info_available") and nodes.get("missing_nodes"):
            blockers.append(format_missing_comfyui_nodes_blocker(nodes["missing_nodes"]))
        elif not nodes.get("object_info_available"):
            blockers.append(format_comfyui_object_info_unavailable_blocker(nodes.get("object_info_error")))
        if not selected_motion:
            blockers.append(format_missing_sd15_motion_model_blocker(animatediff_motion_model))
        if not selected_sd15:
            blockers.append(format_missing_sd15_checkpoint_blocker(checkpoints, realvisxl_checkpoint, animatediff_motion_model))
        return {"ready": not blockers, "blockers": blockers, "selected_sd15_checkpoint": selected_sd15, "selected_motion_model": selected_motion, "checkpoints": checkpoints, "motion_models": motion_models, "nodes": nodes}

    def animatediff_sdxl_node_diagnostics(settings: dict[str, Any]) -> dict[str, Any]:
        required_nodes = animatediff_required_node_names()
        optional_nodes = animatediff_sdxl_optional_node_names()
        try:
            object_info = http_json_request(f"{comfyui_url(settings)}/object_info", timeout=5.0)
            return {
                "object_info_available": True,
                "object_info_error": "",
                "required_nodes": required_nodes,
                "optional_nodes": optional_nodes,
                "missing_nodes": animatediff_missing_node_names(object_info, required_nodes),
                "missing_optional_nodes": animatediff_missing_node_names(object_info, optional_nodes),
                "node_inputs": comfyui_node_inputs_for_object_info(object_info, animatediff_combined_node_names(required_nodes, optional_nodes)),
            }
        except Exception as exc:
            return {"object_info_available": False, "object_info_error": str(exc), "required_nodes": required_nodes, "optional_nodes": optional_nodes, "missing_nodes": required_nodes, "missing_optional_nodes": optional_nodes, "node_inputs": {}}

    def animatediff_sdxl_environment_diagnostics(settings: dict[str, Any]) -> dict[str, Any]:
        checkpoints = comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt"))
        motion_models = comfyui_model_files(settings, "animatediff_models", animatediff_motion_model_suffixes())
        selected_sdxl = find_sdxl_checkpoint(settings)
        selected_motion = find_sdxl_motion_model(settings)
        nodes = animatediff_sdxl_node_diagnostics(settings)
        blockers: list[str] = []
        warnings: list[str] = []
        if nodes.get("object_info_available") and nodes.get("missing_nodes"):
            blockers.append(format_missing_comfyui_nodes_blocker(nodes["missing_nodes"]))
        elif not nodes.get("object_info_available"):
            blockers.append(format_comfyui_object_info_unavailable_blocker(nodes.get("object_info_error")))
        if not selected_sdxl:
            blockers.append(format_missing_sdxl_checkpoint_blocker(realvisxl_checkpoint))
        if not selected_motion:
            blockers.append(format_missing_sdxl_motion_model_blocker())
        if selected_motion and selected_motion == animatediff_motion_model:
            blockers.append(format_incompatible_sdxl_motion_model_blocker(animatediff_motion_model))
        if nodes.get("missing_optional_nodes"):
            warnings.append(format_optional_sdxl_helper_nodes_warning(nodes["missing_optional_nodes"]))
        warnings.append(format_experimental_sdxl_path_warning())
        return {
            "ready": not blockers,
            "implemented": bool(not blockers),
            "blockers": blockers,
            "warnings": warnings,
            "selected_sdxl_checkpoint": selected_sdxl,
            "selected_motion_model": selected_motion,
            "motion_model_env": animatediff_sdxl_env_model,
            "known_motion_model_candidates": list(animatediff_sdxl_model_candidates),
            "checkpoints": checkpoints,
            "motion_models": motion_models,
            "nodes": nodes,
        }

    def comfyui_default_launch_candidates(settings: dict[str, Any]) -> dict[str, Any]:
        configured_path = resolve_user_path(str(settings.get("comfyui_path") or default_settings["image_comfyui_path"]))
        checked: list[str] = []
        if not configured_path:
            return {"candidate": None, "checked": checked, "note": "ComfyUI path is not configured"}
        portable_root = configured_path

        nvidia_bat = portable_root / "run_nvidia_gpu.bat"
        checked.append(rel_path(nvidia_bat))
        if nvidia_bat.exists():
            return {
                "candidate": {"kind": "bat", "path": str(nvidia_bat), "cwd": str(portable_root), "label": rel_path(nvidia_bat)},
                "checked": checked,
                "note": f"Default launch candidate found: {rel_path(nvidia_bat)}",
            }

        cpu_bat = portable_root / "run_cpu.bat"
        checked.append(rel_path(cpu_bat))
        if cpu_bat.exists():
            return {
                "candidate": {"kind": "bat", "path": str(cpu_bat), "cwd": str(portable_root), "label": rel_path(cpu_bat)},
                "checked": checked,
                "note": f"Default launch candidate found: {rel_path(cpu_bat)}",
            }

        embedded_python = portable_root / "python_embeded" / "python.exe"
        main_py = portable_root / "ComfyUI" / "main.py"
        checked.extend([rel_path(embedded_python), rel_path(main_py)])
        if embedded_python.exists() and main_py.exists():
            comfyui_cwd = portable_root / "ComfyUI"
            return {
                "candidate": {
                    "kind": "python",
                    "python": str(embedded_python),
                    "main_py": str(main_py),
                    "cwd": str(comfyui_cwd),
                    "label": f"{rel_path(embedded_python)} + {rel_path(main_py)}",
                },
                "checked": checked,
                "note": f"Default launch candidate found: {rel_path(embedded_python)} + {rel_path(main_py)}",
            }

        return {"candidate": None, "checked": checked, "note": f"No default ComfyUI launch candidate found; checked: {', '.join(checked)}"}

    def launch_comfyui_candidate(candidate: dict[str, Any]) -> None:
        kind = str(candidate.get("kind") or "")
        cwd = str(candidate.get("cwd") or root)
        if kind == "bat":
            bat_path = str(candidate.get("path") or "")
            subprocess.Popen(f'start "ComfyUI" "{bat_path}"', cwd=cwd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        if kind == "python":
            python_path = str(candidate.get("python") or "")
            main_py = str(candidate.get("main_py") or "")
            subprocess.Popen([python_path, main_py, "--listen", "127.0.0.1", "--port", "8188"], cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        raise RuntimeError(f"Unsupported ComfyUI launch candidate type: {kind or 'unknown'}")

    def start_comfyui_if_needed(settings: dict[str, Any]) -> dict[str, Any]:
        health = comfyui_health(settings)
        if health.get("running"):
            return health | {"started": False, "note": "ComfyUI is already running"}
        if not settings.get("comfyui_autostart"):
            return health | {"started": False, "note": "Autostart is disabled"}
        launch_cmd = str(settings.get("comfyui_launch_cmd") or "").strip()
        configured_path = resolve_user_path(str(settings.get("comfyui_path") or default_settings["image_comfyui_path"]))
        cwd = configured_path if configured_path and configured_path.exists() else root
        if launch_cmd:
            subprocess.Popen(launch_cmd, cwd=str(cwd), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return health | {"started": True, "note": f"ComfyUI launch command started with cwd={rel_path(cwd)}"}
        candidate_info = comfyui_default_launch_candidates(settings)
        candidate = candidate_info.get("candidate")
        if not isinstance(candidate, dict):
            return health | {"started": False, "note": candidate_info.get("note") or "No launch command or default ComfyUI launch candidate found", "checked_paths": candidate_info.get("checked", [])}
        launch_comfyui_candidate(candidate)
        return health | {"started": True, "note": f"ComfyUI default launch started: {candidate.get('label')}", "checked_paths": candidate_info.get("checked", []), "default_launch_candidate": candidate.get("label")}

    def wait_for_comfyui(settings: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        start_info = start_comfyui_if_needed(settings)
        deadline = time.time() + max(0.1, timeout)
        last = comfyui_health(settings)
        while time.time() < deadline:
            last = comfyui_health(settings)
            if last.get("running"):
                return last
            time.sleep(1.0)
        start_note = str(start_info.get("note") or "")
        checked = start_info.get("checked_paths") if isinstance(start_info.get("checked_paths"), list) else []
        detail = last.get("error") or "timeout"
        if start_note:
            detail = f"{detail}; {start_note}"
        if checked:
            detail = f"{detail}; checked paths: {', '.join(str(item) for item in checked)}"
        raise RuntimeError(f"ComfyUI is not reachable at {comfyui_url(settings)}: {detail}")

    def comfyui_status(settings: dict[str, Any]) -> dict[str, Any]:
        health = comfyui_health(settings)
        model_info = comfyui_model_check(settings)
        default_launch = comfyui_default_launch_candidates(settings)
        return {
            "running": bool(health.get("running")),
            "url": comfyui_url(settings),
            "autostart_enabled": bool(settings.get("comfyui_autostart")),
            "launch_command_configured": bool(str(settings.get("comfyui_launch_cmd") or "").strip()),
            "default_launch_candidate": (default_launch.get("candidate") or {}).get("label") if isinstance(default_launch.get("candidate"), dict) else "",
            "default_launch_checked_paths": default_launch.get("checked", []),
            "workflow_mode": settings.get("workflow_mode"),
            "model": settings.get("model"),
            "model_checkpoint": model_info.get("model_checkpoint", ""),
            "model_check": model_info.get("model_check", "unknown"),
            "note": model_info.get("note") if health.get("running") else (health.get("error") or default_launch.get("note") or model_info.get("note") or "ComfyUI is not reachable"),
        }

    return {
        "comfyui_url": comfyui_url,
        "http_json_request": http_json_request,
        "comfyui_health": comfyui_health,
        "comfyui_model_check": comfyui_model_check,
        "comfyui_models_dir": comfyui_models_dir,
        "comfyui_model_files": comfyui_model_files,
        "find_sd15_checkpoint": find_sd15_checkpoint,
        "find_sdxl_checkpoint": find_sdxl_checkpoint,
        "find_sdxl_motion_model": find_sdxl_motion_model,
        "animatediff_node_diagnostics": animatediff_node_diagnostics,
        "animatediff_environment_diagnostics": animatediff_environment_diagnostics,
        "animatediff_sdxl_node_diagnostics": animatediff_sdxl_node_diagnostics,
        "animatediff_sdxl_environment_diagnostics": animatediff_sdxl_environment_diagnostics,
        "comfyui_default_launch_candidates": comfyui_default_launch_candidates,
        "launch_comfyui_candidate": launch_comfyui_candidate,
        "start_comfyui_if_needed": start_comfyui_if_needed,
        "wait_for_comfyui": wait_for_comfyui,
        "comfyui_status": comfyui_status,
    }
