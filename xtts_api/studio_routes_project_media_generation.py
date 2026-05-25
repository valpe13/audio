from typing import Any

from fastapi import HTTPException, Query

try:
    from .studio_route_deps import dep
    from .studio_schemas import (
        ChunkImageRequest,
        ChunkImagesRequest,
        ChunkVideoRequest,
        ChunkVideosRequest,
        GroupCreate,
        GroupImageRequest,
        GroupImagesRequest,
        GroupMoveRequest,
        GroupVideoRequest,
        GroupVideosRequest,
    )
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep
    from studio_schemas import (
        ChunkImageRequest,
        ChunkImagesRequest,
        ChunkVideoRequest,
        ChunkVideosRequest,
        GroupCreate,
        GroupImageRequest,
        GroupImagesRequest,
        GroupMoveRequest,
        GroupVideoRequest,
        GroupVideosRequest,
    )


def register_project_media_generation_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register project video-group media generation and group mutation routes."""

    @app.post("/api/project/groups/{group_id}/chunks/{chunk_id}/image")
    def generate_chunk_image_endpoint(group_id: str, chunk_id: str, payload: ChunkImageRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        task = dep(deps, "enqueue_chunk_image_task")(project, group_id, chunk_id, force=payload.force, replace=payload.replace, missing_only=payload.missing_only)
        dep(deps, "set_status")(project, f"Картинка чанка поставлена в очередь: {chunk_id}", bool(task))
        return dep(deps, "prepare_optional_queued_task_response")(task, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))


    @app.post("/api/project/groups/{group_id}/chunks/{chunk_id}/video")
    def generate_chunk_video_endpoint(group_id: str, chunk_id: str, payload: ChunkVideoRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        task = dep(deps, "enqueue_chunk_video_task")(project, group_id, chunk_id, force=payload.force, replace=payload.replace, missing_only=payload.missing_only)
        dep(deps, "set_status")(project, f"Видео чанка поставлено в очередь: {chunk_id}", bool(task))
        return dep(deps, "prepare_optional_queued_task_response")(task, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))


    @app.post("/api/project/groups/{group_id}/chunk-images")
    def generate_group_chunk_images_endpoint(group_id: str, payload: ChunkImagesRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        group = dep(deps, "find_video_group")(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        queued: list[dict[str, Any]] = []
        skipped = 0
        sequence_id = dep(deps, "group_chunk_sequence_id")(group)
        allow_auto_place = dep(deps, "auto_chunk_sequence_state")(project, group, sequence_id) in {"empty", "auto_images"}
        for chunk_id in dep(deps, "group_chunk_id_strings")(group):
            for image_index in range(1, max(1, int(payload.images_per_chunk or 1)) + 1):
                task = dep(deps, "enqueue_chunk_image_task")(project, group_id, chunk_id, force=payload.force, replace=payload.replace, missing_only=payload.missing_only, bulk_auto_place=allow_auto_place, auto_sequence_id=sequence_id, sequence_index=image_index, sequence_count=payload.images_per_chunk)
                if task:
                    queued.append(task)
                else:
                    skipped += 1
        dep(deps, "set_status")(project, f"Картинки чанков группы поставлены в очередь: {len(queued)}, пропущено: {skipped}", bool(queued))
        return dep(deps, "prepare_queued_tasks_response")(queued, skipped, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))


    @app.post("/api/project/groups/{group_id}/chunk-videos")
    def generate_group_chunk_videos_endpoint(group_id: str, payload: ChunkVideosRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        group = dep(deps, "find_video_group")(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        queued: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        sequence_id = dep(deps, "group_chunk_sequence_id")(group)
        allow_auto_replace = True
        for chunk_id in dep(deps, "group_chunk_id_strings")(group):
            try:
                sources = dep(deps, "auto_chunk_image_sources_for_video")(project, group, chunk_id, sequence_id)
                if not sources:
                    skipped.append({"chunk_id": chunk_id, "reason": "no scheduled timeline image"})
                    continue
                for source in sources:
                    task = dep(deps, "enqueue_chunk_video_task")(project, group_id, chunk_id, force=payload.force, replace=payload.replace, missing_only=payload.missing_only, bulk_auto_place=allow_auto_replace, auto_sequence_id=sequence_id, source_media_id=str(source.get("id") or "") if source else "")
                    if task:
                        queued.append(task)
                    else:
                        skipped.append({"chunk_id": chunk_id, "reason": "video already exists or active"})
            except HTTPException as exc:
                skipped.append({"chunk_id": chunk_id, "reason": str(exc.detail)})
                continue
        dep(deps, "set_status")(project, f"Видео чанков группы поставлены в очередь: {len(queued)}, пропущено: {len(skipped)}", bool(queued))
        return dep(deps, "prepare_queued_tasks_skipped_response")(queued, skipped, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))


    @app.post("/api/project/groups/chunk-images")
    def generate_all_chunk_images_endpoint(payload: ChunkImagesRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
        queued: list[dict[str, Any]] = []
        skipped = 0
        for group in groups:
            if not isinstance(group, dict) or not group.get("id"):
                continue
            group_id = str(group.get("id"))
            sequence_id = dep(deps, "group_chunk_sequence_id")(group)
            allow_auto_place = dep(deps, "auto_chunk_sequence_state")(project, group, sequence_id) in {"empty", "auto_images"}
            for chunk_id in dep(deps, "group_chunk_id_strings")(group):
                for image_index in range(1, max(1, int(payload.images_per_chunk or 1)) + 1):
                    task = dep(deps, "enqueue_chunk_image_task")(project, group_id, chunk_id, force=payload.force, replace=payload.replace, missing_only=payload.missing_only, bulk_auto_place=allow_auto_place, auto_sequence_id=sequence_id, sequence_index=image_index, sequence_count=payload.images_per_chunk)
                    if task:
                        queued.append(task)
                    else:
                        skipped += 1
        dep(deps, "set_status")(project, f"Картинки чанков всех групп поставлены в очередь: {len(queued)}, пропущено: {skipped}", bool(queued))
        return dep(deps, "prepare_queued_tasks_response")(queued, skipped, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))


    @app.post("/api/project/groups/chunk-videos")
    def generate_all_chunk_videos_endpoint(payload: ChunkVideosRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
        queued: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict) or not group.get("id"):
                continue
            group_id = str(group.get("id"))
            sequence_id = dep(deps, "group_chunk_sequence_id")(group)
            allow_auto_replace = True
            for chunk_id in dep(deps, "group_chunk_id_strings")(group):
                try:
                    sources = dep(deps, "auto_chunk_image_sources_for_video")(project, group, chunk_id, sequence_id)
                    if not sources:
                        skipped.append({"group_id": group_id, "chunk_id": chunk_id, "reason": "no scheduled timeline image"})
                        continue
                    for source in sources:
                        task = dep(deps, "enqueue_chunk_video_task")(project, group_id, chunk_id, force=payload.force, replace=payload.replace, missing_only=payload.missing_only, bulk_auto_place=allow_auto_replace, auto_sequence_id=sequence_id, source_media_id=str(source.get("id") or "") if source else "")
                        if task:
                            queued.append(task)
                        else:
                            skipped.append({"group_id": group_id, "chunk_id": chunk_id, "reason": "video already exists or active"})
                except HTTPException as exc:
                    skipped.append({"group_id": group_id, "chunk_id": chunk_id, "reason": str(exc.detail)})
                    continue
        dep(deps, "set_status")(project, f"Видео чанков всех групп поставлены в очередь: {len(queued)}, пропущено: {len(skipped)}", bool(queued))
        return dep(deps, "prepare_queued_tasks_skipped_response")(queued, skipped, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))


    @app.post("/api/project/groups")
    def create_group_endpoint(payload: GroupCreate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        video = project.setdefault("arrangement", {}).setdefault("video", {})
        groups = video.setdefault("groups", [])
        insert_at = len(groups)
        if payload.insert_after_group_id:
            existing_idx = next((idx for idx, group in enumerate(groups) if isinstance(group, dict) and group.get("id") == payload.insert_after_group_id), None)
            if existing_idx is not None:
                insert_at = existing_idx + 1
        valid_ids = set(dep(deps, "chunk_order_ids")(dep(deps, "ordered_project_chunks")(project)))
        chunk_ids = [str(chunk_id) for chunk_id in payload.chunk_ids if str(chunk_id) in valid_ids]
        group = dep(deps, "create_video_group_dict")(payload.title or f"Manual group {insert_at + 1}", payload.summary, chunk_ids, order=insert_at, source="manual")
        groups.insert(insert_at, group)
        video["groups"] = dep(deps, "renumber_video_groups")(groups)
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Group added: {group.get('title')}")
        return dep(deps, "enrich_project")(project)


    @app.delete("/api/project/groups/{group_id}")
    def delete_group_endpoint(group_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        video = project.setdefault("arrangement", {}).setdefault("video", {})
        groups = video.setdefault("groups", [])
        next_groups = [group for group in groups if not (isinstance(group, dict) and group.get("id") == group_id)]
        if len(next_groups) == len(groups):
            raise HTTPException(status_code=404, detail="Video group not found")
        video["groups"] = dep(deps, "renumber_video_groups")(next_groups)
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Group deleted: {group_id}")
        return dep(deps, "enrich_project")(project)


    @app.post("/api/project/groups/{group_id}/move")
    def move_group_endpoint(group_id: str, payload: GroupMoveRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        video = project.setdefault("arrangement", {}).setdefault("video", {})
        groups = list(video.setdefault("groups", []))
        idx = next((i for i, group in enumerate(groups) if isinstance(group, dict) and group.get("id") == group_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="Video group not found")
        if payload.order is not None:
            new_idx = max(0, min(len(groups) - 1, int(payload.order)))
        else:
            direction = str(payload.direction or "").strip().lower()
            new_idx = idx - 1 if direction == "up" else idx + 1 if direction == "down" else idx
            new_idx = max(0, min(len(groups) - 1, new_idx))
        item = groups.pop(idx)
        groups.insert(new_idx, item)
        video["groups"] = dep(deps, "renumber_video_groups")(groups)
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, "Group order updated")
        return dep(deps, "enrich_project")(project)


    @app.post("/api/project/groups/{group_id}/image")
    def generate_group_image_endpoint(group_id: str, payload: GroupImageRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        task = dep(deps, "enqueue_group_image_task")(project, group_id, force=payload.force)
        dep(deps, "set_status")(project, f"Image generation queued for {group_id}", True)
        return dep(deps, "prepare_optional_queued_tasks_response")(task, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))


    @app.post("/api/project/groups/{group_id}/video")
    def generate_group_video_endpoint(group_id: str, payload: GroupVideoRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        task = dep(deps, "enqueue_group_video_task")(project, group_id, force=payload.force, source_media_id=str(payload.source_media_id or ""))
        backend_label = dep(deps, "video_i2v_backend_label")(dep(deps, "video_i2v_settings")(project))
        dep(deps, "set_status")(project, f"{backend_label} video generation queued for {group_id}", True)
        return dep(deps, "prepare_optional_queued_tasks_response")(task, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))


    @app.post("/api/project/groups/images")
    def generate_group_images_endpoint(payload: GroupImagesRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
        queued: list[dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict) or not group.get("id"):
                continue
            image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
            has_ready_image = bool(image_meta.get("path")) and image_meta.get("status") == "ready"
            if payload.missing_only and has_ready_image and not payload.force:
                continue
            task = dep(deps, "enqueue_group_image_task")(project, str(group.get("id")), force=payload.force)
            if task:
                task.setdefault("payload", {})["bulk_auto_place"] = True
                task.setdefault("params", task["payload"])["bulk_auto_place"] = True
            if task:
                queued.append(task)
        dep(deps, "set_status")(project, f"Queued {len(queued)} image generation task(s); generated images will auto-place across each group timeline because this was an explicit bulk action", bool(queued))
        return dep(deps, "prepare_queued_tasks_empty_skipped_response")(queued, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))


    @app.post("/api/project/groups/videos")
    def generate_group_videos_endpoint(payload: GroupVideosRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
        queued: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, dict) or not group.get("id"):
                skipped.append({"group_id": str(group.get("id") if isinstance(group, dict) else ""), "reason": "invalid group"})
                continue
            group_id = str(group.get("id"))
            sources = dep(deps, "scheduled_group_image_items")(group)
            if not sources:
                skipped.append({"group_id": group_id, "reason": "no scheduled timeline image"})
                continue
            for source in sources:
                try:
                    task = dep(deps, "enqueue_group_video_task")(project, group_id, force=payload.force, source_media_id=str(source.get("id") or ""), bulk_auto_place=True)
                except HTTPException as exc:
                    skipped.append({"group_id": group_id, "source_media_id": str(source.get("id") or ""), "reason": str(exc.detail)})
                    continue
            if task:
                queued.append(task)
            else:
                skipped.append({"group_id": group_id, "source_media_id": str(source.get("id") or ""), "reason": "video already exists or active"})
        backend_label = dep(deps, "video_i2v_backend_label")(dep(deps, "video_i2v_settings")(project))
        dep(deps, "set_status")(project, f"Queued {len(queued)} {backend_label} video generation task(s), skipped {len(skipped)}; generated videos will auto-place across each group timeline because this was an explicit bulk action", bool(queued))
        return dep(deps, "prepare_queued_tasks_skipped_response")(queued, skipped, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))


