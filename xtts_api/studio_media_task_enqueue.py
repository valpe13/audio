from typing import Any

from fastapi import HTTPException

try:
    from .studio_route_deps import dep
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep


def make_media_task_enqueue_helpers(deps: dict[str, Any]) -> dict[str, Any]:
    """Build queue helper functions for project/group image and video generation tasks."""

    def task_is_queued_or_running(task: dict[str, Any]) -> bool:
        return task.get("status") in {"queued", "running"}

    def active_image_task_for_group(project_id: str, group_id: str) -> dict[str, Any] | None:
        pid = dep(deps, "safe_project_id")(project_id)
        with dep(deps, "queue_lock"):
            for task in dep(deps, "tasks"):
                payload = task.get("payload") or task.get("params") or {}
                if task.get("kind") == "image_group" and task.get("project_id") == pid and payload.get("group_id") == group_id and task_is_queued_or_running(task):
                    return dict(task)
        return None

    def active_video_task_for_group(project_id: str, group_id: str) -> dict[str, Any] | None:
        pid = dep(deps, "safe_project_id")(project_id)
        with dep(deps, "queue_lock"):
            for task in dep(deps, "tasks"):
                payload = task.get("payload") or task.get("params") or {}
                if task.get("kind") == "video_group" and task.get("project_id") == pid and payload.get("group_id") == group_id and task_is_queued_or_running(task):
                    return dict(task)
        return None

    def enqueue_group_image_task(project: dict[str, Any], group_id: str, *, force: bool = False) -> dict[str, Any] | None:
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        group = dep(deps, "find_video_group")(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        existing = active_image_task_for_group(pid, group_id)
        if existing and not force:
            return existing
        task = dep(deps, "enqueue_task")(
            "image_group",
            project_id=pid,
            payload={"group_id": group_id},
            label=f"Image: {group.get('title') or group_id}",
            stage="queued",
        )
        return task

    def active_chunk_image_task(project_id: str, group_id: str, chunk_id: str, sequence_index: int | None = None) -> dict[str, Any] | None:
        pid = dep(deps, "safe_project_id")(project_id)
        with dep(deps, "queue_lock"):
            for task in dep(deps, "tasks"):
                payload = task.get("payload") or task.get("params") or {}
                index_matches = sequence_index is None or int(payload.get("sequence_index") or 1) == int(sequence_index)
                if index_matches and task.get("kind") == "chunk_image" and task.get("project_id") == pid and payload.get("group_id") == group_id and payload.get("chunk_id") == chunk_id and task_is_queued_or_running(task):
                    return dict(task)
        return None

    def active_chunk_video_task(project_id: str, group_id: str, chunk_id: str, source_media_id: str = "") -> dict[str, Any] | None:
        pid = dep(deps, "safe_project_id")(project_id)
        with dep(deps, "queue_lock"):
            for task in dep(deps, "tasks"):
                payload = task.get("payload") or task.get("params") or {}
                source_matches = not source_media_id or str(payload.get("source_media_id") or "") == str(source_media_id)
                if source_matches and task.get("kind") == "chunk_video" and task.get("project_id") == pid and payload.get("group_id") == group_id and payload.get("chunk_id") == chunk_id and task_is_queued_or_running(task):
                    return dict(task)
        return None

    def group_chunk_image_count(group: dict[str, Any], chunk_id: str) -> int:
        items = dep(deps, "normalize_group_media_items")(group.get("media_items"), group)
        return len(dep(deps, "group_chunk_media_items")(items, chunk_id, "image"))

    def group_has_chunk_image(group: dict[str, Any], chunk_id: str) -> bool:
        return group_chunk_image_count(group, chunk_id) > 0

    def group_has_chunk_video(group: dict[str, Any], chunk_id: str) -> bool:
        items = dep(deps, "normalize_group_media_items")(group.get("media_items"), group)
        return bool(dep(deps, "group_chunk_media_items")(items, chunk_id, "video"))

    def enqueue_chunk_image_task(project: dict[str, Any], group_id: str, chunk_id: str, *, force: bool = False, replace: bool = False, missing_only: bool = True, bulk_auto_place: bool = False, auto_sequence_id: str = "", sequence_index: int = 1, sequence_count: int = 1) -> dict[str, Any] | None:
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        group = dep(deps, "find_video_group")(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        chunk = dep(deps, "find_chunk_in_group")(project, group, chunk_id)
        if missing_only and not force and group_chunk_image_count(group, chunk_id) >= max(1, int(sequence_count or 1)):
            return None
        existing = active_chunk_image_task(pid, group_id, chunk_id, sequence_index)
        if existing and not force:
            return existing
        return dep(deps, "enqueue_task")(
            "chunk_image",
            project_id=pid,
            payload={"group_id": group_id, "chunk_id": chunk_id, "replace": bool(replace), "bulk_auto_place": bool(bulk_auto_place), "auto_sequence_id": auto_sequence_id or "", "sequence_index": int(sequence_index or 1), "sequence_count": int(sequence_count or 1)},
            label=f"Картинка чанка #{int(chunk.get('order') or 0) + 1} · {int(sequence_index or 1)}/{int(sequence_count or 1)}",
            stage="queued",
        )

    def enqueue_chunk_video_task(project: dict[str, Any], group_id: str, chunk_id: str, *, force: bool = False, replace: bool = False, missing_only: bool = True, bulk_auto_place: bool = False, auto_sequence_id: str = "", source_media_id: str = "") -> dict[str, Any] | None:
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        group = dep(deps, "find_video_group")(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        chunk = dep(deps, "find_chunk_in_group")(project, group, chunk_id)
        if missing_only and not force and not source_media_id and group_has_chunk_video(group, chunk_id):
            return None
        if not group_has_chunk_image(group, chunk_id):
            raise HTTPException(status_code=400, detail="Generate the chunk image before chunk video")
        existing = active_chunk_video_task(pid, group_id, chunk_id, source_media_id)
        if existing and not force:
            return existing
        return dep(deps, "enqueue_task")(
            "chunk_video",
            project_id=pid,
            payload={"group_id": group_id, "chunk_id": chunk_id, "replace": bool(replace), "bulk_auto_place": bool(bulk_auto_place), "auto_sequence_id": auto_sequence_id or "", "source_media_id": source_media_id or ""},
            label=f"Видео чанка #{int(chunk.get('order') or 0) + 1}",
            stage="queued",
        )

    def enqueue_group_video_task(project: dict[str, Any], group_id: str, *, force: bool = False, source_media_id: str = "", bulk_auto_place: bool = False) -> dict[str, Any] | None:
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        group = dep(deps, "find_video_group")(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        scheduled_sources = dep(deps, "scheduled_group_image_items")(group)
        if not scheduled_sources and (not isinstance(group.get("image"), dict) or not group.get("image", {}).get("path")):
            backend_label = dep(deps, "video_i2v_backend_label")(dep(deps, "video_i2v_settings")(project))
            raise HTTPException(status_code=400, detail=f"Place a group image on the timeline before {backend_label} video")
        existing = active_video_task_for_group(pid, group_id)
        if existing and not force:
            return existing
        task = dep(deps, "enqueue_task")(
            "video_group",
            project_id=pid,
            payload={"group_id": group_id, "source_media_id": source_media_id or "", "bulk_auto_place": bool(bulk_auto_place)},
            label=f"{dep(deps, 'video_i2v_backend_label')(dep(deps, 'video_i2v_settings')(project))} video: {group.get('title') or group_id}",
            stage="queued",
        )
        return task

    return {
        "active_image_task_for_group": active_image_task_for_group,
        "active_chunk_image_task": active_chunk_image_task,
        "active_chunk_video_task": active_chunk_video_task,
        "active_video_task_for_group": active_video_task_for_group,
        "enqueue_chunk_image_task": enqueue_chunk_image_task,
        "enqueue_chunk_video_task": enqueue_chunk_video_task,
        "enqueue_group_image_task": enqueue_group_image_task,
        "enqueue_group_video_task": enqueue_group_video_task,
        "group_chunk_image_count": group_chunk_image_count,
        "group_has_chunk_image": group_has_chunk_image,
        "group_has_chunk_video": group_has_chunk_video,
        "task_is_queued_or_running": task_is_queued_or_running,
    }
