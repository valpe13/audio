import shutil
import time
from typing import Any

from fastapi import HTTPException, Query

try:
    from .studio_route_deps import dep
    from .studio_schemas import ProjectCreate, ProjectPatch, TextImportRequest, TextValue
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep
    from studio_schemas import ProjectCreate, ProjectPatch, TextImportRequest, TextValue


def register_project_write_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register project mutation/text routes for the studio API."""

    @app.post("/api/projects")
    def create_project(payload: ProjectCreate) -> dict[str, Any]:
        index = dep(deps, "load_projects_index")()
        existing = {item["id"] for item in index.get("projects", [])}
        base = dep(deps, "slugify_project_name")(payload.name)
        pid = base
        counter = 2
        while pid in existing:
            suffix = f"-{counter}"
            pid = f"{base[:64 - len(suffix)]}{suffix}"
            counter += 1
        project = dep(deps, "default_project")()
        project["id"] = pid
        project["name"] = payload.name.strip() or "New project"
        project["full_text"] = dep(deps, "repair_mojibake_text")(payload.initial_text or "")[0]
        project["created_at"] = time.time()
        project["updated_at"] = time.time()
        dep(deps, "create_project_storage")(pid, project)
        index = dep(deps, "prepare_project_create_index_update")(index, dep(deps, "project_metadata_from_project")(project, pid), pid)
        dep(deps, "save_projects_index")(index)
        return dep(deps, "prepare_created_project_response")(
            dep(deps, "enrich_project")(dep(deps, "load_project")(pid)),
            dep(deps, "load_projects_index")().get("projects", []),
            pid,
        )

    @app.post("/api/projects/active")
    def post_active_project(payload: dict[str, Any]) -> dict[str, Any]:
        pid = dep(deps, "safe_project_id")(str(payload.get("project_id") or ""))
        dep(deps, "set_active_project")(pid)
        return dep(deps, "prepare_active_project_response")(dep(deps, "enrich_project")(dep(deps, "load_project")(pid)), pid)

    @app.get("/api/projects/{project_id}")
    def open_project(project_id: str) -> dict[str, Any]:
        pid = dep(deps, "safe_project_id")(project_id)
        dep(deps, "set_active_project")(pid)
        return dep(deps, "enrich_project")(dep(deps, "load_project")(pid))

    @app.patch("/api/projects/{project_id}")
    def patch_project(project_id: str, payload: ProjectPatch) -> dict[str, Any]:
        pid = dep(deps, "safe_project_id")(project_id)
        project = dep(deps, "load_project")(pid)
        if payload.name is not None:
            project["name"] = payload.name.strip() or project.get("name") or pid
        dep(deps, "save_project")(project, pid)
        return dep(deps, "prepare_patched_project_response")(
            dep(deps, "enrich_project")(dep(deps, "load_project")(pid)),
            dep(deps, "load_projects_index")().get("projects", []),
        )

    @app.delete("/api/projects/{project_id}")
    def delete_project(project_id: str, confirm: str = Query(default="")) -> dict[str, Any]:
        pid = dep(deps, "safe_project_id")(project_id)
        if confirm != pid:
            raise HTTPException(status_code=400, detail="Deletion requires confirm query equal to project_id")
        index = dep(deps, "load_projects_index")()
        projects = index.get("projects", [])
        if len(projects) <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last project")
        if dep(deps, "project_has_active_tasks")(pid):
            raise HTTPException(status_code=400, detail="Cannot delete a project with queued/running tasks")
        path = dep(deps, "project_dir")(pid)
        if path.exists():
            shutil.rmtree(path)
        delete_index_update = dep(deps, "prepare_project_delete_index_update")(index, pid)
        active = delete_index_update.get("last_active_project_id")
        dep(deps, "save_projects_index")(delete_index_update)
        return dep(deps, "prepare_deleted_project_response")(dep(deps, "load_projects_index")().get("projects", []), active)

    @app.post("/api/projects/{project_id}/import-text")
    def import_project_text(project_id: str, payload: TextImportRequest) -> dict[str, Any]:
        pid = dep(deps, "safe_project_id")(project_id)
        if payload.mode not in {"replace", "append"}:
            raise HTTPException(status_code=400, detail="mode must be replace or append")
        project = dep(deps, "load_project")(pid)
        incoming = dep(deps, "repair_mojibake_text")(payload.text or "")[0]
        if payload.mode == "append" and project.get("full_text"):
            project["full_text"] = f"{project.get('full_text', '')}\n\n{incoming}" if incoming else project.get("full_text", "")
        else:
            project["full_text"] = incoming
        dep(deps, "set_status")(project, f"Text imported ({payload.mode})")
        return dep(deps, "enrich_project")(project)

    @app.post("/api/project/text")
    def save_full_text(payload: TextValue, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        project["full_text"] = dep(deps, "repair_mojibake_text")(payload.text)[0]
        dep(deps, "set_status")(project, "Text saved")
        return dep(deps, "enrich_project")(project)
