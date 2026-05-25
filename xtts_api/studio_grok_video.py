import os
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any

try:
    from .studio_defaults import image_data_uri
except ImportError:  # pragma: no cover - direct script imports
    from studio_defaults import image_data_uri


def make_grok_video_helpers(ctx: dict[str, Any]) -> dict[str, Any]:
    default_settings = ctx["DEFAULT_SETTINGS"]
    grok_imagine_video_confirmed_resolutions = ctx["GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS"]
    grok_imagine_video_model = ctx["GROK_IMAGINE_VIDEO_MODEL"]
    xai_imagine_video_poll_interval_seconds = ctx["XAI_IMAGINE_VIDEO_POLL_INTERVAL_SECONDS"]
    xai_imagine_video_poll_timeout_seconds = ctx["XAI_IMAGINE_VIDEO_POLL_TIMEOUT_SECONDS"]

    def grok_imagine_video_diagnostics(project: dict[str, Any]) -> dict[str, Any]:
        pid = ctx["safe_project_id"](str(project.get("id") or ctx["active_project_id"]()))
        api_key_configured = bool(ctx["resolve_xai_api_key"](project, pid))
        settings = ctx["image_settings"](project)
        video_settings = ctx["video_i2v_settings"](project)
        groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
        sample_group = next((group for group in groups if isinstance(group, dict)), {})
        sample_image_meta = sample_group.get("image") if isinstance(sample_group.get("image"), dict) else {}
        return {
            "ready": api_key_configured,
            "implemented": True,
            "api_key_configured": api_key_configured,
            "api_key_hint": ctx["xai_api_key_hint"](pid),
            "model": video_settings.get("grok_model") or grok_imagine_video_model,
            "endpoint": "/v1/videos/generations",
            "poll_endpoint": "/v1/videos/{request_id}",
            "docs": ctx["grok_imagine_video_diagnostics_docs"](),
            "defaults": ctx["grok_imagine_video_diagnostics_defaults"](
                video_settings,
                xai_imagine_video_poll_timeout_seconds,
                xai_imagine_video_poll_interval_seconds,
            ),
            "quality_options": ctx["grok_imagine_video_diagnostics_quality_options"](ctx["GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS"], grok_imagine_video_confirmed_resolutions),
            "aspect_ratio_behavior": ctx["grok_imagine_video_diagnostics_aspect_ratio_behavior"](
                ctx["GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS"],
                ctx["source_image_aspect_ratio"](settings, sample_image_meta, mode=str(video_settings.get("grok_aspect_ratio_mode") or "auto")),
            ),
            "blockers": ctx["grok_imagine_video_api_key_blockers"](api_key_configured),
            "warnings": ctx["grok_imagine_video_diagnostics_warnings"](),
        }

    def locate_ffprobe_for_ffmpeg(ffmpeg: str) -> str:
        ffmpeg_path = Path(ffmpeg) if ffmpeg else Path()
        if ffmpeg_path.name.lower() == "ffmpeg.exe":
            sibling = ffmpeg_path.with_name("ffprobe.exe")
            if sibling.exists():
                return str(sibling)
        if ffmpeg_path.name.lower() == "ffmpeg":
            sibling = ffmpeg_path.with_name("ffprobe")
            if sibling.exists():
                return str(sibling)
        return shutil.which("ffprobe") or ""

    def ffprobe_duration_sec(ffmpeg: str, source: Path) -> float:
        ffprobe = locate_ffprobe_for_ffmpeg(ffmpeg)
        if not ffprobe:
            return 0.0
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            return 0.0
        try:
            return max(0.0, float((proc.stdout or "").strip()))
        except (TypeError, ValueError):
            return 0.0

    def postprocess_grok_loop_video(project: dict[str, Any], source: Path, mode: str, *, crossfade_sec: float = 0.5) -> tuple[Path, dict[str, Any]]:
        safe_mode = str(mode or "pingpong").strip().lower()
        if safe_mode not in {"off", "pingpong", "crossfade"}:
            safe_mode = "pingpong"
        if safe_mode == "off":
            return source, {"loop_postprocess": "off", "loop": False}
        ffmpeg = ctx["locate_ffmpeg"](project)
        if not ffmpeg:
            raise RuntimeError("ffmpeg was not found; Grok loop post-processing requires ffmpeg on PATH or bundled with ComfyUI_windows_portable")
        out = source.with_name(f"{source.stem}_{safe_mode}_loop.mp4")
        if safe_mode == "pingpong":
            vf = "[0:v]fps=30,format=yuv420p,split=2[f][r];[r]reverse[rv];[f][rv]concat=n=2:v=1:a=0[v]"
            ctx["run_ffmpeg"]([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-filter_complex", vf, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-movflags", "+faststart", str(out)])
            duration = ffprobe_duration_sec(ffmpeg, out)
            return out, {"loop_postprocess": "pingpong", "loop": True, "pingpong": True, "duration_sec": duration or 0.0}
        source_duration = ffprobe_duration_sec(ffmpeg, source)
        if source_duration <= 0.25:
            raise RuntimeError("Could not determine Grok video duration for crossfade loop post-processing")
        fade = max(0.1, min(float(crossfade_sec or 0.5), min(2.0, source_duration / 2.5)))
        offset = max(0.0, source_duration - fade)
        vf = f"[0:v]fps=30,format=yuv420p,split=2[main][loop];[loop]trim=0:{fade:.3f},setpts=PTS-STARTPTS[first];[main][first]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f},trim=duration={source_duration:.3f},format=yuv420p[v]"
        ctx["run_ffmpeg"]([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-filter_complex", vf, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-movflags", "+faststart", str(out)])
        return out, {"loop_postprocess": "crossfade", "loop": True, "pingpong": False, "crossfade_sec": fade, "duration_sec": source_duration}

    def run_xai_grok_imagine_video_i2v_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], output_prefix: str) -> dict[str, Any]:
        image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
        source_path = ctx["resolve_user_path"](image_meta.get("path")) if image_meta.get("path") else None
        if not source_path or not source_path.exists():
            raise RuntimeError("Generate the group image before Grok Imagine Video image-to-video")
        project_id = ctx["safe_project_id"](str(project.get("id") or ctx["active_project_id"]()))
        api_key = ctx["resolve_xai_api_key"](project, project_id)
        if not api_key:
            raise RuntimeError("Grok/xAI API key is not configured; set a project key in XTTS Studio settings or XAI_API_KEY")
        model = str(video_settings.get("grok_model") or grok_imagine_video_model).strip() or grok_imagine_video_model
        duration = ctx["normalize_grok_imagine_video_duration"](video_settings.get("grok_duration_sec"), default_duration=5)
        resolution = ctx["normalize_grok_imagine_video_resolution"](video_settings.get("grok_resolution"), grok_imagine_video_confirmed_resolutions)
        aspect_ratio = ctx["source_image_aspect_ratio"](settings, image_meta, mode=str(video_settings.get("grok_aspect_ratio_mode") or "auto"))
        prompt = ctx["format_grok_imagine_video_prompt"](group)
        base_url = (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
        request_payload = ctx["build_grok_imagine_video_request_payload"](model, prompt, image_data_uri(source_path), duration, aspect_ratio, resolution)
        start_response = ctx["xai_json_request"](base_url, "/videos/generations", api_key, method="POST", payload=request_payload, timeout=120.0, operation_label="xAI Imagine Video request")
        request_id = str(start_response.get("request_id") or "") if isinstance(start_response, dict) else ""
        if not request_id:
            raise RuntimeError(f"xAI Imagine Video start response did not include request_id: {ctx['truncate_text'](start_response, 500)}")
        deadline = time.time() + xai_imagine_video_poll_timeout_seconds
        poll_response: dict[str, Any] = {}
        video_url = ""
        while time.time() < deadline:
            result = ctx["xai_json_request"](base_url, f"/videos/{urllib.parse.quote(request_id)}", api_key, timeout=60.0, operation_label="xAI Imagine Video poll request")
            poll_response = result if isinstance(result, dict) else {}
            status = str(poll_response.get("status") or "").strip().lower()
            if status == "done":
                video_info = poll_response.get("video") if isinstance(poll_response.get("video"), dict) else {}
                video_url = str(video_info.get("url") or "")
                if not video_url:
                    raise RuntimeError(f"xAI Imagine Video completed without video.url: {ctx['truncate_text'](poll_response, 700)}")
                break
            if status in {"failed", "expired"}:
                raise RuntimeError(ctx["format_grok_imagine_video_status_error"](status, poll_response.get("error") or poll_response))
            time.sleep(xai_imagine_video_poll_interval_seconds)
        if not video_url:
            raise RuntimeError(ctx["format_grok_imagine_video_timeout_error"](request_id, xai_imagine_video_poll_timeout_seconds))
        pid = ctx["safe_project_id"](str(project.get("id") or ctx["active_project_id"]()))
        out_dir = ctx["project_videos_dir"](pid)
        suffix = ctx["normalize_grok_video_download_suffix"](Path(urllib.parse.urlparse(video_url).path).suffix)
        raw_out = out_dir / f"{output_prefix}_{request_id[:10]}_grok_raw{suffix}"
        ctx["download_http_file"](video_url, raw_out, empty_label="Downloaded xAI video URL")
        loop_mode = str(video_settings.get("grok_loop_postprocess") or default_settings["video_i2v_grok_loop_postprocess"]).strip().lower()
        out, loop_meta = postprocess_grok_loop_video(project, raw_out, loop_mode, crossfade_sec=float(video_settings.get("grok_crossfade_sec") or default_settings["video_i2v_grok_crossfade_sec"]))
        width, height = ctx["svd_source_dimensions"](settings, image_meta)
        video_info = poll_response.get("video") if isinstance(poll_response.get("video"), dict) else {}
        path = ctx["rel_path"](out)
        now = time.time()
        return {
            "status": "ready",
            "provider": "xai",
            "model": model,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "duration_sec": float(loop_meta.get("duration_sec") or video_info.get("duration") or duration),
            "width": width,
            "height": height,
            "source_image_path": ctx["rel_path"](source_path),
            "original_path": ctx["rel_path"](raw_out),
            "path": path,
            "url": f"/api/video?path={path}&v={int(out.stat().st_mtime)}",
            "prompt_id": request_id,
            "request_id": request_id,
            "positive_prompt": prompt,
            "loop": bool(loop_meta.get("loop", False)),
            "pingpong": bool(loop_meta.get("pingpong", False)),
            "loop_postprocess": loop_meta.get("loop_postprocess", loop_mode),
            "crossfade_sec": loop_meta.get("crossfade_sec"),
            "created_at": now,
            "updated_at": now,
        }

    return {
        "grok_imagine_video_diagnostics": grok_imagine_video_diagnostics,
        "locate_ffprobe_for_ffmpeg": locate_ffprobe_for_ffmpeg,
        "ffprobe_duration_sec": ffprobe_duration_sec,
        "postprocess_grok_loop_video": postprocess_grok_loop_video,
        "run_xai_grok_imagine_video_i2v_workflow": run_xai_grok_imagine_video_i2v_workflow,
    }
