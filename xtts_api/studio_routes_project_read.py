from typing import Any

from fastapi import Query

try:
    from .studio_route_deps import dep
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep


def register_project_read_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register read-only project/chunk retrieval routes for the studio API."""

    def enriched_chunk_response(chunk_id: str, project_id: str | None = None) -> dict[str, Any]:
        project = dep(deps, "enrich_project")(dep(deps, "load_project")(project_id))
        chunk = next((c for c in project.get("chunks", []) if c.get("id") == chunk_id), None)
        if not chunk:
            raise dep(deps, "HTTPException")(status_code=404, detail="Chunk not found")
        return {
            "chunk": chunk,
            "settings": project.get("settings", {}),
            "timeline_duration_sec": project.get("timeline_duration_sec", 0.0),
            "status": project.get("status", {}),
            "export": project.get("export"),
        }

    @app.get("/api/project")
    def get_project(project_id: str | None = Query(default=None)) -> dict[str, Any]:
        return dep(deps, "enrich_project")(dep(deps, "load_project")(project_id))

    @app.get("/api/chunks/{chunk_id}")
    def get_chunk(chunk_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        return enriched_chunk_response(chunk_id, project_id)
