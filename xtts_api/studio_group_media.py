import copy
import time
import uuid
from typing import Any

from fastapi import HTTPException

try:
    from .studio_route_deps import dep
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep


def make_group_media_helpers(deps: dict[str, Any]) -> dict[str, Any]:
    """Build helpers for group media library, timeline, and chunk media source handling."""

    def append_group_media_library_item(group: dict[str, Any], media_type: str, meta: dict[str, Any]) -> dict[str, Any] | None:
        path = str(meta.get("path") or "").strip()
        url = str(meta.get("url") or "").strip()
        if not path and not url:
            return None
        group["media_items"] = dep(deps, "normalize_group_media_items")(group.get("media_items"), {})
        key = path or url
        existing = next((item for item in group["media_items"] if str(item.get("path") or item.get("url") or "") == key), None)
        if existing:
            existing.setdefault("scheduled", False)
            existing.setdefault("source", "generated")
            return existing
        item = dep(deps, "normalize_group_media_item")({
            "id": f"generated_{media_type}_{uuid.uuid4().hex[:10]}",
            "type": media_type,
            "path": path,
            "url": url,
            "label": f"Generated {media_type}",
            "role": "library",
            "duration_sec": float(meta.get("duration_sec") or 0.0),
            "scheduled": False,
            "source": "generated",
        }, len(group["media_items"]))
        if item:
            group["media_items"].append(item)
        return item

    def group_timeline_duration(project: dict[str, Any], group: dict[str, Any]) -> float:
        chunks_by_id = {str(chunk.get("id") or ""): chunk for chunk in dep(deps, "ordered_project_chunks")(project)}
        total = 0.0
        for chunk_id in group.get("chunk_ids", []):
            chunk = chunks_by_id.get(str(chunk_id))
            if not chunk:
                continue
            total += max(0.0, float(chunk.get("duration_sec") or 0.0)) + max(0.0, float(chunk.get("pause_after") or 0.0))
        return round(max(0.25, total), 3)

    def auto_place_generated_group_media(project: dict[str, Any], group_id: str, media_type: str) -> None:
        group = dep(deps, "find_video_group")(project, group_id)
        if not group:
            return
        duration = group_timeline_duration(project, group)
        items = dep(deps, "normalize_group_media_items")(group.get("media_items"), group)
        generated = [item for item in items if item.get("type") == media_type and item.get("source") == "generated"]
        if not generated:
            generated = [item for item in items if item.get("type") == media_type]
        if not generated:
            group["media_items"] = items
            return
        # Explicit bulk image/video generation is the only path that rewrites media scheduling.
        # Single regeneration and manual uploads stay library-only to avoid destroying user edits.
        step = duration / max(1, len(generated))
        generated_ids = {item.get("id") for item in generated}
        index_by_id = {item.get("id"): idx for idx, item in enumerate(generated)}
        for item in items:
            if item.get("id") in generated_ids:
                slot = index_by_id.get(item.get("id"), 0)
                item["scheduled"] = True
                item["start_offset_sec"] = round(step * slot, 3)
                item["duration_sec"] = round(duration - step * slot if len(generated) == 1 else step, 3)
                item["role"] = item.get("role") or "main"
            elif item.get("type") == media_type:
                item["scheduled"] = False
        group["media_items"] = items

    def scheduled_group_image_items(group: dict[str, Any]) -> list[dict[str, Any]]:
        items = dep(deps, "normalize_group_media_items")(group.get("media_items"), group)
        return dep(deps, "scheduled_visual_image_media_items")(items)

    def group_media_source_for_video(project: dict[str, Any], group: dict[str, Any], source_media_id: str = "") -> tuple[dict[str, Any], dict[str, Any] | None]:
        candidates = scheduled_group_image_items(group)
        source = next((item for item in candidates if str(item.get("id") or "") == str(source_media_id)), None) if source_media_id else None
        source = source or (candidates[0] if candidates else None)
        prompt_group = copy.deepcopy(group)
        if source:
            image_meta = prompt_group.get("image") if isinstance(prompt_group.get("image"), dict) else {}
            prompt_group["image"] = {
                **image_meta,
                "path": source.get("path", ""),
                "url": source.get("url", ""),
                "aspect_ratio": image_meta.get("aspect_ratio") or dep(deps, "image_settings")(project).get("aspect_ratio"),
            }
        return prompt_group, source

    def append_or_replace_group_video_media(project: dict[str, Any], group: dict[str, Any], video_meta: dict[str, Any], source_item: dict[str, Any] | None, *, bulk_auto_place: bool = False) -> dict[str, Any] | None:
        library_item = append_group_media_library_item(group, "video", video_meta)
        if not source_item:
            group["media_items"] = dep(deps, "normalize_group_media_items")(group.get("media_items"), group)
            return library_item
        items = dep(deps, "normalize_group_media_items")(group.get("media_items"), group)
        source_id = str(source_item.get("id") or "")
        replacement = dep(deps, "normalize_group_media_item")({
            "id": f"group_video_{uuid.uuid4().hex[:10]}",
            "type": "video",
            "path": video_meta.get("path", ""),
            "url": video_meta.get("url", ""),
            "label": "Generated video",
            "role": source_item.get("role") or "main",
            "source": "generated",
            "source_id": source_id,
            "scheduled": True,
            "start_offset_sec": source_item.get("start_offset_sec") or 0.0,
            "duration_sec": source_item.get("duration_sec") or group_timeline_duration(project, group),
            "fit": source_item.get("fit") or "cover",
            "kind": "timeline_block",
            "timeline_source": "auto_bulk_video" if bulk_auto_place else "single_video_replace",
            "auto_sequence_id": source_item.get("auto_sequence_id") or "",
            "chunk_id": source_item.get("chunk_id") or "",
            "prompt_scope": source_item.get("prompt_scope") or "group",
            "prompt_source": source_item.get("prompt_source") or "",
            "positive_prompt": video_meta.get("positive_prompt") or source_item.get("positive_prompt") or "",
            "negative_prompt": video_meta.get("negative_prompt") or source_item.get("negative_prompt") or "",
            "provider": video_meta.get("provider", ""),
            "model": video_meta.get("model", ""),
            "created_at": time.time(),
        }, len(items))
        if not replacement:
            group["media_items"] = items
            return library_item
        replaced = False
        next_items: list[dict[str, Any]] = []
        for item in items:
            if str(item.get("id") or "") == source_id:
                next_items.append(replacement)
                replaced = True
            else:
                next_items.append(item)
        if not replaced:
            next_items.append(replacement)
        group["media_items"] = dep(deps, "normalize_group_media_items")(next_items, group)
        return replacement

    def auto_chunk_sequence_state(project: dict[str, Any], group: dict[str, Any], sequence_id: str) -> str:
        items = dep(deps, "normalize_group_media_items")(group.get("media_items"), group)
        scheduled = dep(deps, "scheduled_group_media_items")(items)
        if not scheduled:
            return "empty"
        if sequence_id and all(item.get("timeline_source") == "auto_bulk_image" and item.get("auto_sequence_id") == sequence_id and item.get("type") == "image" and item.get("prompt_scope") == "chunk" for item in scheduled):
            return "auto_images"
        if sequence_id and all(item.get("timeline_source") in {"auto_bulk_image", "auto_bulk_video"} and item.get("auto_sequence_id") == sequence_id and item.get("prompt_scope") == "chunk" for item in scheduled):
            return "auto_sequence"
        return "manual_or_mixed"

    def auto_chunk_image_sources_for_video(project: dict[str, Any], group: dict[str, Any], chunk_id: str, sequence_id: str = "") -> list[dict[str, Any]]:
        items = dep(deps, "normalize_group_media_items")(group.get("media_items"), group)
        candidates = [
            item for item in dep(deps, "scheduled_group_media_items")(items)
            if item.get("type") == "image"
            and item.get("prompt_scope") == "chunk"
            and str(item.get("chunk_id") or "") == str(chunk_id)
            and item.get("path")
        ]
        if sequence_id:
            auto_candidates = [item for item in candidates if item.get("timeline_source") == "auto_bulk_image" and item.get("auto_sequence_id") == sequence_id]
            if auto_candidates:
                candidates = auto_candidates
        return sorted(candidates, key=lambda item: (float(item.get("start_offset_sec") or 0.0), int(item.get("sequence_index") or 1)))

    def chunk_timeline_span(project: dict[str, Any], group: dict[str, Any], chunk_id: str) -> tuple[float, float]:
        chunks_by_id = {str(chunk.get("id") or ""): chunk for chunk in dep(deps, "ordered_project_chunks")(project)}
        cursor = 0.0
        for current_id in group.get("chunk_ids", []):
            chunk = chunks_by_id.get(str(current_id))
            if not chunk:
                continue
            duration = max(0.05, float(chunk.get("duration_sec") or 0.5))
            pause = max(0.0, float(chunk.get("pause_after") or 0.0))
            if str(current_id) == str(chunk_id):
                return round(cursor, 3), round(duration + pause, 3)
            cursor += duration + pause
        raise RuntimeError("Chunk is not part of the selected group")

    def find_chunk_in_group(project: dict[str, Any], group: dict[str, Any], chunk_id: str) -> dict[str, Any]:
        if str(chunk_id) not in {str(item) for item in group.get("chunk_ids", [])}:
            raise HTTPException(status_code=404, detail="Chunk is not part of video group")
        chunk = next((item for item in project.get("chunks", []) if isinstance(item, dict) and str(item.get("id") or "") == str(chunk_id)), None)
        if not chunk:
            raise HTTPException(status_code=404, detail="Chunk not found")
        return chunk

    def group_subtitle_blocks_from_chunks(project: dict[str, Any], group: dict[str, Any]) -> list[dict[str, Any]]:
        chunks_by_id = {str(chunk.get("id") or ""): chunk for chunk in dep(deps, "ordered_project_chunks")(project)}
        cursor = 0.0
        blocks: list[dict[str, Any]] = []
        for idx, chunk_id in enumerate(group.get("chunk_ids", [])):
            chunk = chunks_by_id.get(str(chunk_id))
            if not chunk:
                continue
            duration = max(0.05, float(chunk.get("duration_sec") or 0.5))
            blocks.append({"id": f"subtitle_{idx + 1:03d}", "enabled": True, "text": str(chunk.get("text") or chunk.get("tts_text") or ""), "start_offset_sec": round(cursor, 3), "duration_sec": round(duration, 3), "order": idx})
            cursor += duration + max(0.0, float(chunk.get("pause_after") or 0.0))
        return dep(deps, "normalize_subtitle_blocks")(blocks, group)

    def group_with_chunk_video_source(project: dict[str, Any], group: dict[str, Any], chunk_id: str, source_item: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], tuple[float, float]]:
        chunk = find_chunk_in_group(project, group, chunk_id)
        start, duration = chunk_timeline_span(project, group, chunk_id)
        items = dep(deps, "normalize_group_media_items")(group.get("media_items"), group)
        source_item = source_item or next((item for item in items if item.get("type") == "image" and item.get("prompt_scope") == "chunk" and str(item.get("chunk_id") or "") == str(chunk_id) and item.get("path")), None)
        if not source_item:
            raise HTTPException(status_code=400, detail="Generate the chunk image before chunk video")
        prompt_group = copy.deepcopy(group)
        prompt_group["id"] = f"{group.get('id')}_{chunk_id}"
        prompt_group["title"] = f"{group.get('title') or group.get('id')} · чанк {int(chunk.get('order') or 0) + 1}"
        prompt_group["image"] = {"path": source_item.get("path", ""), "url": source_item.get("url", ""), "width": source_item.get("width") or group.get("image", {}).get("width"), "height": source_item.get("height") or group.get("image", {}).get("height"), "aspect_ratio": group.get("image", {}).get("aspect_ratio") or dep(deps, "image_settings")(project).get("aspect_ratio")}
        prompt_group["summary"] = dep(deps, "truncate_text")(chunk.get("text") or chunk.get("tts_text") or group.get("summary"), 900)
        prompt_group["visual_prompt"] = dep(deps, "truncate_text")(chunk.get("image_prompt") or source_item.get("positive_prompt") or group.get("visual_prompt"), 3000)
        prompt_group["negative_prompt"] = dep(deps, "truncate_text")(chunk.get("image_negative_prompt") or source_item.get("negative_prompt") or group.get("negative_prompt"), 1500)
        prompt_group["animation_positive_prompt"] = dep(deps, "truncate_text")(chunk.get("animation_positive_prompt") or chunk.get("grok_video_prompt") or group.get("animation_positive_prompt") or group.get("grok_video_prompt"), 3000)
        prompt_group["animation_negative_prompt"] = dep(deps, "truncate_text")(chunk.get("animation_negative_prompt") or group.get("animation_negative_prompt"), 1500)
        prompt_group["grok_video_prompt"] = dep(deps, "truncate_text")(chunk.get("grok_video_prompt") or chunk.get("animation_positive_prompt") or group.get("grok_video_prompt"), 3000)
        source_start = float(source_item.get("start_offset_sec") or start)
        source_duration = float(source_item.get("duration_sec") or duration)
        return prompt_group, chunk, (round(source_start, 3), round(max(0.05, source_duration), 3))

    return {
        "append_group_media_library_item": append_group_media_library_item,
        "append_or_replace_group_video_media": append_or_replace_group_video_media,
        "auto_chunk_image_sources_for_video": auto_chunk_image_sources_for_video,
        "auto_chunk_sequence_state": auto_chunk_sequence_state,
        "auto_place_generated_group_media": auto_place_generated_group_media,
        "chunk_timeline_span": chunk_timeline_span,
        "find_chunk_in_group": find_chunk_in_group,
        "group_media_source_for_video": group_media_source_for_video,
        "group_subtitle_blocks_from_chunks": group_subtitle_blocks_from_chunks,
        "group_timeline_duration": group_timeline_duration,
        "group_with_chunk_video_source": group_with_chunk_video_source,
        "scheduled_group_image_items": scheduled_group_image_items,
    }
