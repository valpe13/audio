import shutil
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable


def make_comfyui_runtime_helpers(ctx: dict[str, Any]) -> dict[str, Callable[..., Any]]:
    default_settings = ctx["DEFAULT_SETTINGS"]
    active_project_id = ctx["active_project_id"]
    comfyui_url = ctx["comfyui_url"]
    comfyui_video_output_suffixes = ctx["comfyui_video_output_suffixes"]
    http_json_request = ctx["http_json_request"]
    project_images_dir = ctx["project_images_dir"]
    project_videos_dir = ctx["project_videos_dir"]
    rel_path = ctx["rel_path"]
    resolve_user_path = ctx["resolve_user_path"]
    safe_project_id = ctx["safe_project_id"]
    svd_source_dimensions = ctx["svd_source_dimensions"]
    truncate_text = ctx["truncate_text"]

    def comfyui_submit_prompt(settings: dict[str, Any], workflow: dict[str, Any]) -> str:
        client_id = f"xtts-studio-{uuid.uuid4().hex[:12]}"
        response = http_json_request(f"{comfyui_url(settings)}/prompt", method="POST", payload={"prompt": workflow, "client_id": client_id}, timeout=20.0)
        prompt_id = str(response.get("prompt_id") or "") if isinstance(response, dict) else ""
        if not prompt_id:
            raise RuntimeError(f"ComfyUI /prompt did not return prompt_id: {truncate_text(response, 500)}")
        return prompt_id

    def comfyui_wait_history(settings: dict[str, Any], prompt_id: str, timeout: float = 240.0) -> dict[str, Any]:
        wait_timeout = max(1.0, float(timeout))
        started_at = time.time()
        deadline = started_at + wait_timeout
        last_error = ""
        while time.time() < deadline:
            try:
                history = http_json_request(f"{comfyui_url(settings)}/history/{urllib.parse.quote(prompt_id)}", timeout=10.0)
                item = history.get(prompt_id) if isinstance(history, dict) else None
                if isinstance(item, dict):
                    status = item.get("status") if isinstance(item.get("status"), dict) else {}
                    if status.get("status_str") == "error" or status.get("completed") is False and item.get("outputs"):
                        raise RuntimeError(f"ComfyUI prompt failed: {truncate_text(status, 700)}")
                    if item.get("outputs"):
                        return item
            except Exception as exc:
                last_error = str(exc)
            time.sleep(1.0)
        elapsed = time.time() - started_at
        raise RuntimeError(
            f"Timed out waiting {elapsed:.0f}s/{wait_timeout:.0f}s for ComfyUI prompt {prompt_id}: "
            f"{last_error or 'no history output'}"
        )

    def comfyui_first_output_image(history_item: dict[str, Any]) -> dict[str, str]:
        outputs = history_item.get("outputs") if isinstance(history_item.get("outputs"), dict) else {}
        for output in outputs.values():
            if not isinstance(output, dict):
                continue
            images = output.get("images") if isinstance(output.get("images"), list) else []
            for image in images:
                if isinstance(image, dict) and image.get("filename"):
                    return {
                        "filename": str(image.get("filename") or ""),
                        "subfolder": str(image.get("subfolder") or ""),
                        "type": str(image.get("type") or "output"),
                    }
        raise RuntimeError("ComfyUI history contains no output images")

    def comfyui_first_output_video(history_item: dict[str, Any]) -> dict[str, str]:
        outputs = history_item.get("outputs") if isinstance(history_item.get("outputs"), dict) else {}
        candidates: list[dict[str, str]] = []
        video_suffixes = comfyui_video_output_suffixes()

        def collect_item(item: Any) -> None:
            if not isinstance(item, dict):
                return
            filename = str(item.get("filename") or item.get("file") or item.get("name") or "")
            if not filename:
                url = str(item.get("url") or "")
                parsed_path = urllib.parse.urlparse(url).path if url else ""
                filename = Path(urllib.parse.unquote(parsed_path)).name if parsed_path else ""
            if not filename or not filename.lower().endswith(video_suffixes):
                return
            candidates.append({
                "filename": filename,
                "subfolder": str(item.get("subfolder") or ""),
                "type": str(item.get("type") or "output"),
            })

        for output in outputs.values():
            if not isinstance(output, dict):
                continue
            for key in ("gifs", "videos", "animated", "video", "files", "outputs"):
                items = output.get(key) if isinstance(output.get(key), list) else []
                for item in items:
                    collect_item(item)
            images = output.get("images") if isinstance(output.get("images"), list) else []
            for image in images:
                collect_item(image)
            for value in output.values():
                if isinstance(value, dict):
                    collect_item(value)
                elif isinstance(value, list):
                    for item in value:
                        collect_item(item)
        if candidates:
            candidates.sort(key=lambda item: 0 if item["filename"].lower().endswith(video_suffixes[0]) else 1)
            return candidates[0]
        output_keys = sorted({str(key) for output in outputs.values() if isinstance(output, dict) for key in output.keys()})
        raise RuntimeError(f"ComfyUI history contains no output video; output keys: {', '.join(output_keys) or 'none'}")

    def comfyui_download_image(settings: dict[str, Any], image_info: dict[str, str], out_path: Path) -> None:
        query = urllib.parse.urlencode({
            "filename": image_info.get("filename", ""),
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        })
        with urllib.request.urlopen(f"{comfyui_url(settings)}/view?{query}", timeout=60.0) as response:
            data = response.read()
        if not data:
            raise RuntimeError("ComfyUI returned an empty image")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)

    def comfyui_download_output(settings: dict[str, Any], output_info: dict[str, str], out_path: Path) -> None:
        query = urllib.parse.urlencode({
            "filename": output_info.get("filename", ""),
            "subfolder": output_info.get("subfolder", ""),
            "type": output_info.get("type", "output"),
        })
        with urllib.request.urlopen(f"{comfyui_url(settings)}/view?{query}", timeout=120.0) as response:
            data = response.read()
        if not data:
            raise RuntimeError("ComfyUI returned an empty output")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)

    def comfyui_output_dir(settings: dict[str, Any]) -> Path | None:
        comfy_root = resolve_user_path(str(settings.get("comfyui_path") or default_settings["image_comfyui_path"]))
        if not comfy_root:
            return None
        for candidate in (comfy_root / "ComfyUI" / "output", comfy_root / "output"):
            if candidate.exists():
                return candidate
        return None

    def comfyui_newest_video_by_prefix(settings: dict[str, Any], output_prefix: str, since: float = 0.0) -> Path | None:
        output_dir = comfyui_output_dir(settings)
        if not output_dir or not output_prefix:
            return None
        matches: list[Path] = []
        for suffix in ("*.mp4", "*.webm", "*.gif"):
            matches.extend(output_dir.rglob(f"{output_prefix}*{suffix[1:]}"))
        fresh = [path for path in matches if path.is_file() and path.stat().st_mtime >= since - 2.0]
        return max(fresh or matches, key=lambda path: path.stat().st_mtime, default=None)

    def copy_comfyui_prefix_video_to_project(project: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], group: dict[str, Any], output_prefix: str, source: Path, prompt_id: str = "", model_name: str | None = None, model_checkpoint: str | None = None, motion_model: str = "") -> dict[str, Any]:
        pid = safe_project_id(str(project.get("id") or active_project_id()))
        out_dir = project_videos_dir(pid)
        source_suffix = source.suffix.lower()
        suffix = source_suffix if source_suffix in comfyui_video_output_suffixes() else ".mp4"
        token = prompt_id[:10] if prompt_id else "recovered"
        out = out_dir / f"{output_prefix}_{token}{suffix}"
        if source.resolve() != out.resolve():
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, out)
        image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
        source_path = resolve_user_path(image_meta.get("path")) if image_meta.get("path") else None
        width, height = svd_source_dimensions(settings, image_meta)
        frames = int(video_settings.get("frames") or 0)
        fps = int(video_settings.get("fps") or 0)
        pingpong = bool(video_settings.get("pingpong", True))
        loop_count = max(0, int(video_settings.get("loop_count") or 0))
        output_fps = max(1, int(video_settings.get("output_fps") or fps or 1))
        single_loop_frames = max(0, frames * 2 - 2) if pingpong and frames > 1 else frames
        output_frames = single_loop_frames * (loop_count + 1)
        duration_sec = round(output_frames / float(output_fps), 3) if output_fps > 0 and output_frames > 0 else 0.0
        path = rel_path(out)
        now = time.time()
        return {
            "status": "ready",
            "provider": "comfyui",
            "model": model_name or ("svd_xt" if "xt" in str(video_settings.get("model_checkpoint") or "").lower() else "svd"),
            "model_checkpoint": model_checkpoint or video_settings.get("model_checkpoint", ""),
            "motion_model": motion_model,
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
            "source_image_path": rel_path(source_path) if source_path else str(image_meta.get("path") or ""),
            "path": path,
            "url": f"/api/video?path={path}&v={int(out.stat().st_mtime)}",
            "prompt_id": prompt_id,
            "recovered_from": rel_path(source),
            "created_at": now,
            "updated_at": now,
        }

    def copy_comfyui_animatediff_video_to_project(project: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], group: dict[str, Any], output_prefix: str, source: Path, prompt_id: str = "", model_checkpoint: str = "", motion_model: str = "", model_name: str = "animatediff_sd15") -> dict[str, Any]:
        return copy_comfyui_prefix_video_to_project(project, settings, video_settings, group, output_prefix, source, prompt_id, model_name=model_name, model_checkpoint=model_checkpoint, motion_model=motion_model)

    return {
        "comfyui_submit_prompt": comfyui_submit_prompt,
        "comfyui_wait_history": comfyui_wait_history,
        "comfyui_first_output_image": comfyui_first_output_image,
        "comfyui_first_output_video": comfyui_first_output_video,
        "comfyui_download_image": comfyui_download_image,
        "comfyui_download_output": comfyui_download_output,
        "comfyui_output_dir": comfyui_output_dir,
        "comfyui_newest_video_by_prefix": comfyui_newest_video_by_prefix,
        "copy_comfyui_prefix_video_to_project": copy_comfyui_prefix_video_to_project,
        "copy_comfyui_animatediff_video_to_project": copy_comfyui_animatediff_video_to_project,
    }
