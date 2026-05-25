from typing import Any

from fastapi import Query

try:
    from .studio_route_deps import dep
    from .studio_schemas import MusicArrangementUpdate, SettingsUpdate, VideoArrangementUpdate, VoiceArrangementUpdate
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep
    from studio_schemas import MusicArrangementUpdate, SettingsUpdate, VideoArrangementUpdate, VoiceArrangementUpdate


def register_project_settings_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register project settings and arrangement mutation routes for the studio API."""

    @app.post("/api/project/settings")
    def update_settings(payload: SettingsUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        data = payload.dict(exclude_unset=True)
        xai_secret_action = "kept"
        if "xai_api_key" in data:
            secrets = dep(deps, "load_project_secrets")(pid)
            xai_value = data.pop("xai_api_key")
            clean_key = str(xai_value or "").strip()
            if clean_key:
                secrets["xai_api_key"] = clean_key
                xai_secret_action = "saved"
            else:
                secrets.pop("xai_api_key", None)
                xai_secret_action = "cleared"
            dep(deps, "save_project_secrets")(pid, secrets)
        if "image_comfyui_autostart" in data:
            project.setdefault("settings", {})["image_comfyui_autostart_user_set"] = True
        if "image_provider" in data or "image_model" in data:
            default_settings = dep(deps, "DEFAULT_SETTINGS")
            provider = str(data.get("image_provider") or project.get("settings", {}).get("image_provider") or default_settings["image_provider"]).strip().lower()
            model = str(data.get("image_model") or project.get("settings", {}).get("image_model") or default_settings["image_model"]).strip().lower()
            if provider == "xai":
                provider = "grok"
            if provider not in {"placeholder", "comfyui", "grok"}:
                provider = "comfyui"
            if model == "grok":
                provider = "grok"
            if provider == "grok":
                model = "grok"
            if model not in {"realvisxl", "sdxl", "juggernautxl", "dreamshaperxl", "flux", "custom", "grok"}:
                model = "custom"
            data["image_provider"] = provider
            data["image_model"] = model
        if str(data.get("video_i2v_workflow_mode") or "").strip().lower() == "generated_grok_imagine_video":
            data["video_i2v_enabled"] = True
        for key, value in data.items():
            if value is not None:
                project["settings"][key] = value
        dep(deps, "apply_safe_secret_settings")(project, pid)
        dep(deps, "normalize_arrangement")(project)
        if xai_secret_action == "saved":
            status_message = f"Settings saved · Grok/xAI project key saved for {pid}"
        elif xai_secret_action == "cleared":
            status_message = f"Settings saved · Grok/xAI project key cleared for {pid}"
        else:
            status_message = "Settings saved · Grok/xAI project key unchanged"
        dep(deps, "set_status")(project, status_message)
        return dep(deps, "enrich_project")(project)

    @app.post("/api/project/arrangement/music")
    def update_music_arrangement(payload: MusicArrangementUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        music = project.setdefault("arrangement", {}).setdefault("music", {})
        data = payload.dict(exclude_unset=True)
        if "mode" in data and data["mode"] is not None:
            music["mode"] = data["mode"] if data["mode"] in {"loop", "once", "chain_loop"} else "loop"
        if "volume_envelope" in data and payload.volume_envelope is not None:
            music["volume_envelope"] = [point.dict() for point in payload.volume_envelope]
        for key in ("sources", "lanes", "tracks"):
            if key in data and data[key] is not None:
                music[key] = data[key]
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Music mode saved: {music['mode']} · automation saved")
        return dep(deps, "enrich_project")(project)

    @app.post("/api/project/arrangement/voice")
    def update_voice_arrangement(payload: VoiceArrangementUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        voice = project.setdefault("arrangement", {}).setdefault("voice", {})
        voice["volume_envelope"] = [point.dict() for point in payload.volume_envelope]
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, "Voice volume automation saved")
        return dep(deps, "enrich_project")(project)

    @app.post("/api/project/arrangement/video")
    def update_video_arrangement(payload: VideoArrangementUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        arrangement = project.setdefault("arrangement", {})
        video = arrangement.setdefault("video", {})
        speed_payload = payload.main_timeline_speed_envelope if payload.main_timeline_speed_envelope is not None else payload.speed_envelope
        if speed_payload is not None:
            speed_points = [point.dict() for point in speed_payload]
            arrangement["main_timeline_speed_envelope"] = speed_points
            video["speed_envelope"] = speed_points
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, "Main timeline speed automation saved")
        return dep(deps, "enrich_project")(project)
