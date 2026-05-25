from typing import Any

from fastapi import Query

try:
    from xtts_api.studio_route_deps import dep
except ImportError:  # pragma: no cover - script/direct execution fallback
    from studio_route_deps import dep


def register_queue_read_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register read-only queue/status routes for the studio API."""

    @app.get("/api/queue")
    def get_queue(project_id: str | None = Query(default=None)) -> dict[str, Any]:
        pid = project_id or dep(deps, "active_project_id")()
        return {"queue": dep(deps, "queue_snapshot")(pid), "progress": dep(deps, "progress_snapshot")()}
