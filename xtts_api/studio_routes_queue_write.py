from typing import Any

from fastapi import HTTPException, Query

try:
    from xtts_api.studio_route_deps import dep
    from xtts_api.studio_schemas import ExportRequest, QueueRequest
except ImportError:  # pragma: no cover - script/direct execution fallback
    from studio_route_deps import dep
    from studio_schemas import ExportRequest, QueueRequest


def register_queue_write_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register queue mutation routes for the studio API."""

    @app.post("/api/queue/clear-completed")
    def clear_completed_queue_tasks(project_id: str | None = Query(default=None)) -> dict[str, Any]:
        pid = project_id or dep(deps, "active_project_id")()
        removed = dep(deps, "clear_completed_tasks")(pid)
        return dep(deps, "prepare_clear_completed_tasks_response")(
            removed,
            dep(deps, "queue_snapshot")(pid),
            dep(deps, "progress_snapshot")(),
        )

    @app.post("/api/queue/generate")
    def queue_generate(payload: QueueRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = project.get("id")
        valid = {c["id"] for c in project.get("chunks", [])}
        queued = []
        for chunk_id in payload.chunk_ids:
            if chunk_id in valid:
                queued.append(dep(deps, "enqueue_task")("generate_chunk", chunk_id, pid))
        dep(deps, "set_status")(project, f"Queued {len(queued)} generation task(s)", bool(queued))
        return dep(deps, "prepare_queued_tasks_plain_response")(
            queued,
            dep(deps, "queue_snapshot")(pid),
            dep(deps, "progress_snapshot")(),
            dep(deps, "enrich_project")(dep(deps, "load_project")(pid)),
        )

    @app.post("/api/queue/export")
    def queue_export(payload: ExportRequest | None = None, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        request = payload or ExportRequest()
        task = dep(deps, "enqueue_task")(
            "export",
            project_id=project.get("id"),
            payload=request.dict(),
            label="Export video" if str(request.export_type).startswith("video") else f"Export {request.audio_format.upper()}",
        )
        dep(deps, "set_status")(project, "Export queued", True)
        return dep(deps, "prepare_queued_task_response")(
            task,
            dep(deps, "queue_snapshot")(project.get("id")),
            dep(deps, "progress_snapshot")(),
            dep(deps, "enrich_project")(project),
        )

    @app.delete("/api/queue/{task_id}")
    def delete_queue_task(task_id: str) -> dict[str, Any]:
        if not dep(deps, "remove_task")(task_id):
            raise HTTPException(status_code=400, detail="Only queued tasks can be removed")
        return dep(deps, "prepare_queue_progress_response")(
            dep(deps, "queue_snapshot")(dep(deps, "active_project_id")()),
            dep(deps, "progress_snapshot")(),
        )

    @app.post("/api/queue/{task_id}/move/{direction}")
    def move_queue_task(task_id: str, direction: str) -> dict[str, Any]:
        if direction not in {"up", "down"}:
            raise HTTPException(status_code=400, detail="direction must be up or down")
        if not dep(deps, "move_task")(task_id, direction):
            raise HTTPException(status_code=400, detail="Task cannot be moved")
        return dep(deps, "prepare_queue_progress_response")(
            dep(deps, "queue_snapshot")(dep(deps, "active_project_id")()),
            dep(deps, "progress_snapshot")(),
        )
