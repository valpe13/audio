import os
from typing import Any

from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse

try:
    from .studio_route_deps import dep
except ImportError:  # pragma: no cover - script/direct execution fallback
    from studio_route_deps import dep


def route_availability_summary(app: Any) -> dict[str, Any]:
    """Return a compact availability map for health/startup diagnostics."""

    expected = {
        "GET /api/projects": ("GET", "/api/projects"),
        "GET /api/queue": ("GET", "/api/queue"),
        "POST /api/queue/generate": ("POST", "/api/queue/generate"),
        "POST /api/queue/export": ("POST", "/api/queue/export"),
        "POST /api/project/arrangement/video": ("POST", "/api/project/arrangement/video"),
        "POST /api/project/groups/ai": ("POST", "/api/project/groups/ai"),
        "PATCH /api/project/groups/{group_id}": ("PATCH", "/api/project/groups/{group_id}"),
        "POST /api/project/groups/{group_id}/image": ("POST", "/api/project/groups/{group_id}/image"),
        "POST /api/project/groups/{group_id}/video": ("POST", "/api/project/groups/{group_id}/video"),
        "POST /api/project/groups/{group_id}/chunks/{chunk_id}/video": ("POST", "/api/project/groups/{group_id}/chunks/{chunk_id}/video"),
        "POST /api/project/groups/images": ("POST", "/api/project/groups/images"),
        "POST /api/project/groups/videos": ("POST", "/api/project/groups/videos"),
        "POST /api/project/groups/chunk-videos": ("POST", "/api/project/groups/chunk-videos"),
        "GET /api/comfyui/status": ("GET", "/api/comfyui/status"),
        "GET /api/xai/imagine-video/diagnostics": ("GET", "/api/xai/imagine-video/diagnostics"),
        "GET /api/image": ("GET", "/api/image"),
        "GET /api/video": ("GET", "/api/video"),
        "GET /api/health": ("GET", "/api/health"),
    }
    registered: dict[str, set[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = set(getattr(route, "methods", []) or [])
        if path:
            registered.setdefault(path, set()).update(methods)
    return {
        name: {"available": method in registered.get(path, []), "path": path, "method": method}
        for name, (method, path) in expected.items()
    } | {"registered_api_paths": {path: sorted(methods) for path, methods in registered.items() if path.startswith("/api/")}}


def register_basic_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register basic studio entrypoint and health routes."""

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse("/studio/")

    @app.get("/favicon.ico")
    def favicon() -> FileResponse:
        icon = dep(deps, "STATIC_DIR") / "favicon.ico"
        if icon.exists():
            return FileResponse(str(icon))
        raise HTTPException(status_code=204, detail="No favicon")

    @app.get("/robots.txt")
    def robots() -> dict[str, str]:
        return {"User-agent": "*", "Disallow": "/"}

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        project = dep(deps, "load_project")()
        return {
            "ok": True,
            "build": dep(deps, "STUDIO_BUILD"),
            "api_version": app.version,
            "pid": os.getpid(),
            "server_file": dep(deps, "server_file"),
            "module": dep(deps, "module_name"),
            "project": dep(deps, "rel_path")(dep(deps, "project_path")(project.get("id", "default"))),
            "active_project_id": project.get("id"),
            "model_loaded": bool(dep(deps, "is_tts_model_loaded")()),
            "status": project.get("status", {}),
            "queue_route": "/api/queue",
            "queue_routes": dep(deps, "route_availability_summary")(),
        }
