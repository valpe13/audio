from typing import Any

from fastapi import Query

try:
    from .studio_route_deps import dep
except ImportError:  # pragma: no cover - direct script/import compatibility
    from studio_route_deps import dep


def register_diagnostics_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register read-only diagnostics routes for the studio API."""

    @app.get("/api/comfyui/status")
    def get_comfyui_status(project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        settings = dep(deps, "image_settings")(project)
        return dep(deps, "comfyui_status")(settings)

    @app.get("/api/comfyui/animatediff/diagnostics")
    def get_comfyui_animatediff_diagnostics(project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        settings = dep(deps, "image_settings")(project)
        health = dep(deps, "comfyui_health")(settings)
        comfyui_url = dep(deps, "comfyui_url")
        comfyui_model_files = dep(deps, "comfyui_model_files")
        motion_model = dep(deps, "ANIMATEDIFF_MOTION_MODEL")
        diagnostics = dep(deps, "animatediff_environment_diagnostics")(settings) if health.get("running") else {
            "ready": False,
            "blockers": [f"ComfyUI is not reachable at {comfyui_url(settings)}: {health.get('error') or 'not running'}"],
            "selected_sd15_checkpoint": dep(deps, "find_sd15_checkpoint")(settings),
            "selected_motion_model": motion_model if motion_model in comfyui_model_files(settings, "animatediff_models", (".safetensors", ".ckpt", ".pt", ".pth")) else "",
            "checkpoints": comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt")),
            "motion_models": comfyui_model_files(settings, "animatediff_models", (".safetensors", ".ckpt", ".pt", ".pth")),
            "nodes": {"object_info_available": False, "object_info_error": health.get("error") or "ComfyUI is not running"},
        }
        return {"comfyui": {"running": bool(health.get("running")), "url": comfyui_url(settings)}, "animatediff": diagnostics}

    @app.get("/api/comfyui/animatediff-sdxl/diagnostics")
    def get_comfyui_animatediff_sdxl_diagnostics(project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        settings = dep(deps, "image_settings")(project)
        health = dep(deps, "comfyui_health")(settings)
        comfyui_url = dep(deps, "comfyui_url")
        comfyui_model_files = dep(deps, "comfyui_model_files")
        diagnostics = dep(deps, "animatediff_sdxl_environment_diagnostics")(settings) if health.get("running") else {
            "ready": False,
            "implemented": False,
            "blockers": [f"ComfyUI is not reachable at {comfyui_url(settings)}: {health.get('error') or 'not running'}"],
            "warnings": ["Start ComfyUI, then reload this endpoint to inspect live AnimateDiff-Evolved/HotshotXL node schemas."],
            "selected_sdxl_checkpoint": dep(deps, "find_sdxl_checkpoint")(settings),
            "selected_motion_model": dep(deps, "find_sdxl_motion_model")(settings),
            "motion_model_env": dep(deps, "ANIMATEDIFF_SDXL_ENV_MODEL"),
            "known_motion_model_candidates": list(dep(deps, "ANIMATEDIFF_SDXL_MODEL_CANDIDATES")),
            "checkpoints": comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt")),
            "motion_models": comfyui_model_files(settings, "animatediff_models", (".safetensors", ".ckpt", ".pt", ".pth")),
            "nodes": {"object_info_available": False, "object_info_error": health.get("error") or "ComfyUI is not running"},
        }
        return {"comfyui": {"running": bool(health.get("running")), "url": comfyui_url(settings)}, "animatediff_sdxl": diagnostics}

    @app.get("/api/xai/imagine-video/diagnostics")
    def get_xai_imagine_video_diagnostics(project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        return {"xai_imagine_video": dep(deps, "grok_imagine_video_diagnostics")(project)}
