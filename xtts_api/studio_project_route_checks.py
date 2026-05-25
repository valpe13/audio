from typing import Any

from fastapi import HTTPException


def make_project_route_checks(deps: dict[str, Any]) -> dict[str, Any]:
    def project_has_active_tasks(project_id: str) -> bool:
        pid = deps["safe_project_id"](project_id)
        with deps["queue_lock"]:
            return any(
                task.get("project_id") == pid and deps["task_is_queued_or_running"](task)
                for task in deps["tasks"]
            )

    def validate_grok_groups_enqueue_request(project: dict[str, Any], payload: Any) -> None:
        chunks = deps["ordered_project_chunks"](project)
        if not chunks:
            raise HTTPException(status_code=400, detail="Project has no chunks to group")
        if not any(deps["clean_text"](chunk.get("text", "")) for chunk in chunks):
            raise HTTPException(status_code=400, detail="Project chunks are empty")
        project_id = deps["safe_project_id"](str(project.get("id") or deps["active_project_id"]()))
        if not deps["resolve_xai_api_key"](project, project_id) and not payload.fallback_on_error:
            raise HTTPException(status_code=400, detail="Grok/xAI API key is not configured")
        strategy = (payload.strategy or "auto").strip().lower()
        if strategy not in {"single", "batched", "auto"}:
            raise HTTPException(status_code=400, detail="strategy must be single, batched, or auto")

    return {
        "project_has_active_tasks": project_has_active_tasks,
        "validate_grok_groups_enqueue_request": validate_grok_groups_enqueue_request,
    }
