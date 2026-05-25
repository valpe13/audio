from typing import Any

from fastapi import HTTPException, Query

try:
    from .studio_route_deps import dep
    from .studio_schemas import (
        BulkPromptGenerationRequest,
        BulkSubtitlesRequest,
        ChunkPromptsUpdate,
        GroupSplitRequest,
        GroupUpdate,
        VideoGroupsAiRequest,
    )
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep
    from studio_schemas import (
        BulkPromptGenerationRequest,
        BulkSubtitlesRequest,
        ChunkPromptsUpdate,
        GroupSplitRequest,
        GroupUpdate,
        VideoGroupsAiRequest,
    )


def register_project_group_prompt_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register project video-group AI grouping, prompt, and subtitle routes."""

    def apply_generated_group_prompt(project: dict[str, Any], group: dict[str, Any], *, missing_only: bool = False) -> bool:
        prompt_keys = ("visual_prompt", "visual_context", "negative_prompt", "animation_positive_prompt", "grok_video_prompt")
        if missing_only and all(str(group.get(key) or "").strip() for key in prompt_keys):
            return False
        dep(deps, "generate_prompt_for_group")(project, group)
        return True

    @app.post("/api/project/groups/ai")
    def generate_ai_video_groups(payload: VideoGroupsAiRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        default_settings = dep(deps, "DEFAULT_SETTINGS")
        if payload.exclude_people_from_images is None:
            payload.exclude_people_from_images = bool(project.get("settings", {}).get("image_exclude_people", default_settings["image_exclude_people"]))
        project.setdefault("settings", {})["image_exclude_people"] = bool(payload.exclude_people_from_images)
        dep(deps, "validate_grok_groups_enqueue_request")(project, payload)
        existing = dep(deps, "active_task_by_kind_project")("grok_groups", pid)
        if existing:
            dep(deps, "set_status")(project, "Grok AI grouping already queued/running", True)
            return dep(deps, "prepare_queued_task_response")(existing, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))
        payload_data = payload.dict()
        task = dep(deps, "enqueue_task")(
            "grok_groups",
            project_id=pid,
            payload=payload_data,
            label="Grok AI grouping",
            stage="queued",
        )
        dep(deps, "set_status")(project, "Grok AI grouping queued", True)
        return dep(deps, "prepare_queued_task_response")(task, dep(deps, "queue_snapshot")(pid), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(pid)))

    @app.post("/api/project/groups/split")
    def split_video_groups(payload: GroupSplitRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        chunks = dep(deps, "ordered_project_chunks")(project)
        if not chunks:
            raise HTTPException(status_code=400, detail="No chunks available for group split")
        default_settings = dep(deps, "DEFAULT_SETTINGS")
        exclude_people = bool(project.get("settings", {}).get("image_exclude_people", default_settings["image_exclude_people"]))
        groups = dep(deps, "fallback_video_groups")(chunks, max_chunks_per_group=max(1, int(payload.chunks_per_group or 4)), exclude_people=exclude_people)
        video = project.setdefault("arrangement", {}).setdefault("video", {})
        video["groups"] = dep(deps, "renumber_video_groups")(groups)
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Normal group split into {len(video['groups'])} group(s)")
        return dep(deps, "enrich_project")(project)

    @app.patch("/api/project/groups/{group_id}")
    def update_group_endpoint(group_id: str, payload: GroupUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        group = dep(deps, "update_group_prompts")(project, group_id, payload)
        dep(deps, "set_status")(project, f"Group prompts saved for {group.get('title') or group_id}")
        return {"group": group, "project": dep(deps, "enrich_project")(dep(deps, "load_project")(pid))}

    @app.post("/api/project/groups/{group_id}/prompt")
    def generate_group_prompt_endpoint(group_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        group = dep(deps, "find_video_group")(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        dep(deps, "generate_prompt_for_group")(project, group)
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Generated prompt for {group.get('title') or group_id}")
        return {"group": dep(deps, "find_video_group")(project, group_id) or group, "project": dep(deps, "enrich_project")(dep(deps, "load_project")(pid))}

    @app.post("/api/project/groups/prompts")
    def generate_all_group_prompts_endpoint(payload: BulkPromptGenerationRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        groups = project.setdefault("arrangement", {}).setdefault("video", {}).setdefault("groups", [])
        updated = 0
        skipped = 0
        for group in groups:
            if not isinstance(group, dict):
                continue
            if apply_generated_group_prompt(project, group, missing_only=payload.missing_only):
                updated += 1
            else:
                skipped += 1
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Generated prompts for {updated} group(s), skipped {skipped}")
        return {"updated_count": updated, "skipped_count": skipped, "project": dep(deps, "enrich_project")(dep(deps, "load_project")(pid))}

    @app.patch("/api/project/groups/{group_id}/chunk-prompts")
    def update_chunk_prompts_endpoint(group_id: str, payload: ChunkPromptsUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        group = dep(deps, "find_video_group")(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        allowed = {str(chunk_id) for chunk_id in group.get("chunk_ids", [])}
        items = [item.dict(exclude_unset=True) for item in payload.chunks if str(item.id) in allowed]
        updated = dep(deps, "apply_chunk_prompt_items")(project, items, source="manual")
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Chunk prompts saved for {updated} chunk(s)")
        return {"updated_count": updated, "group": dep(deps, "find_video_group")(project, group_id) or group, "project": dep(deps, "enrich_project")(dep(deps, "load_project")(pid))}

    @app.post("/api/project/groups/{group_id}/chunk-prompts")
    def generate_chunk_prompts_endpoint(group_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        group = dep(deps, "find_video_group")(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        items, source, note = dep(deps, "generate_chunk_prompt_items")(project, group)
        updated = dep(deps, "apply_chunk_prompt_items")(project, items, source=source)
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Generated chunk prompts for {updated} chunk(s) via {source}")
        return {"updated_count": updated, "source": source, "note": note, "group": dep(deps, "find_video_group")(project, group_id) or group, "project": dep(deps, "enrich_project")(dep(deps, "load_project")(pid))}

    @app.post("/api/project/groups/chunk-prompts")
    def generate_all_chunk_prompts_endpoint(payload: BulkPromptGenerationRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
        updated = 0
        skipped = 0
        sources: dict[str, int] = {}
        group_count = 0
        notes: list[str] = []
        for group in groups:
            if not isinstance(group, dict) or not group.get("id"):
                continue
            if payload.missing_only:
                group_chunk_ids = {str(chunk_id) for chunk_id in group.get("chunk_ids", [])}
                has_missing_chunk = any(str(chunk.get("id") or "") in group_chunk_ids and dep(deps, "chunk_prompt_fields_are_empty")(chunk) for chunk in project.get("chunks", []) if isinstance(chunk, dict))
                if not has_missing_chunk:
                    skipped += len(group_chunk_ids)
                    continue
            group_count += 1
            try:
                items, source, note = dep(deps, "generate_chunk_prompt_items")(project, group)
            except Exception as exc:
                skipped += len(group.get("chunk_ids", []) or [])
                source = "error"
                note = dep(deps, "truncate_text")(f"Группа {group.get('title') or group.get('id')}: генерация промтов не удалась: {type(exc).__name__}: {exc}", 700)
                items = []
            count = dep(deps, "apply_chunk_prompt_items_missing_only")(project, items, source=source, missing_only=payload.missing_only)
            updated += count
            skipped += max(0, len(items) - count)
            sources[source] = sources.get(source, 0) + count
            if note and note not in notes:
                notes.append(note)
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Generated chunk prompts for {updated} chunk(s) across {group_count} group(s)")
        return {"updated_count": updated, "skipped_count": skipped, "group_count": group_count, "sources": sources, "notes": notes[:5], "project": dep(deps, "enrich_project")(dep(deps, "load_project")(pid))}

    @app.post("/api/project/groups/subtitles")
    def add_subtitles_to_groups_endpoint(payload: BulkSubtitlesRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        groups = project.setdefault("arrangement", {}).setdefault("video", {}).setdefault("groups", [])
        updated = 0
        for group in groups:
            if not isinstance(group, dict):
                continue
            if payload.missing_only and group.get("subtitle_blocks"):
                continue
            group["subtitle_defaults"] = dep(deps, "normalize_subtitle_defaults")({**dep(deps, "normalize_subtitle_defaults")(group.get("subtitle_defaults")), **dep(deps, "normalize_subtitle_defaults")(payload.subtitle_defaults)})
            group["subtitle_blocks"] = dep(deps, "group_subtitle_blocks_from_chunks")(project, group)
            updated += 1
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Added subtitles to {updated} group(s)")
        return {"updated_count": updated, "project": dep(deps, "enrich_project")(dep(deps, "load_project")(pid))}
