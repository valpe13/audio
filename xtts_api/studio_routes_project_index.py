from typing import Any

try:
    from .studio_route_deps import dep
except ImportError:  # pragma: no cover - script/direct execution fallback
    from studio_route_deps import dep


def register_project_index_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register read-only project index routes for the studio API."""

    @app.get("/api/projects")
    def list_projects() -> dict[str, Any]:
        index = dep(deps, "load_projects_index")()
        return {"projects": index.get("projects", []), "last_active_project_id": index.get("last_active_project_id", "")}
