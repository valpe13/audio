import mimetypes
import re
from typing import Any

from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse

try:
    from .studio_route_deps import dep
except ImportError:  # pragma: no cover - direct script/module imports
    from studio_route_deps import dep


def ensure_project_storage_media_path(resolved: Any, deps: dict[str, Any], media_label: str) -> None:
    allowed_roots = [dep(deps, "PROJECTS_ROOT").resolve(), dep(deps, "PROJECTS_DIR").resolve()]
    try:
        for root in allowed_roots:
            try:
                resolved.resolve().relative_to(root)
                break
            except ValueError:
                continue
        else:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=403, detail=f"{media_label} path is outside project storage")


def image_file_response(path: str, deps: dict[str, Any]) -> FileResponse:
    if not path:
        raise HTTPException(status_code=400, detail="Image path is required")
    resolved = dep(deps, "resolve_user_path")(path, must_exist=True)
    if not resolved or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")
    suffix = resolved.suffix.lower()
    if suffix not in {".svg", ".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported image file type")
    ensure_project_storage_media_path(resolved, deps, "Image")
    media_types = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    return FileResponse(str(resolved), media_type=media_types[suffix], filename=resolved.name)


def video_file_response(path: str, deps: dict[str, Any]) -> FileResponse:
    if not path:
        raise HTTPException(status_code=400, detail="Video path is required")
    resolved = dep(deps, "resolve_user_path")(path, must_exist=True)
    if not resolved or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    suffix = resolved.suffix.lower()
    if suffix not in {".mp4", ".webm", ".gif", ".mov"}:
        raise HTTPException(status_code=400, detail="Unsupported video file type")
    ensure_project_storage_media_path(resolved, deps, "Video")
    media_types = {".mp4": "video/mp4", ".webm": "video/webm", ".gif": "image/gif", ".mov": "video/quicktime"}
    return FileResponse(str(resolved), media_type=media_types[suffix], filename=resolved.name)


def register_media_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register direct media file serving routes."""

    @app.get("/api/audio")
    def audio(path: str) -> FileResponse:
        if re.match(r"^https?://", path or "", flags=re.IGNORECASE):
            return RedirectResponse(path)
        resolved = dep(deps, "resolve_user_path")(path, must_exist=True)
        if not resolved or not resolved.is_file():
            raise HTTPException(status_code=404, detail="Audio file not found")
        media_type = mimetypes.guess_type(str(resolved))[0] or "audio/wav"
        return FileResponse(str(resolved), media_type=media_type, filename=resolved.name)

    @app.get("/api/image")
    def image(path: str) -> FileResponse:
        return image_file_response(path, deps)

    @app.get("/api/video")
    def video(path: str) -> FileResponse:
        return video_file_response(path, deps)
