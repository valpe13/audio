from typing import Any

try:
    from .studio_route_deps import dep
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep


def register_project_active_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register read-only active project routes for the studio API."""

    @app.get("/api/projects/active")
    def get_active_project() -> dict[str, Any]:
        project = dep(deps, "load_project")(dep(deps, "active_project_id")())
        return {"project": dep(deps, "enrich_project")(project), "project_id": project.get("id")}
