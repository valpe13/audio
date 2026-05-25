import re
import time
import uuid
from typing import Any


def make_chunk_media_generation_helpers(deps: dict[str, Any]) -> dict[str, Any]:
    HTTPException = deps["HTTPException"]
    active_project_id = deps["active_project_id"]
    auto_chunk_image_sources_for_video = deps["auto_chunk_image_sources_for_video"]
    auto_chunk_sequence_state = deps["auto_chunk_sequence_state"]
    chunk_timeline_span = deps["chunk_timeline_span"]
    find_chunk_in_group = deps["find_chunk_in_group"]
    find_video_group = deps["find_video_group"]
    format_chunk_image_prompt = deps["format_chunk_image_prompt"]
    generate_group_image = deps["generate_group_image"]
    group_chunk_sequence_id = deps["group_chunk_sequence_id"]
    group_with_chunk_video_source = deps["group_with_chunk_video_source"]
    image_settings = deps["image_settings"]
    normalize_group_image_meta = deps["normalize_group_image_meta"]
    normalize_group_media_item = deps["normalize_group_media_item"]
    normalize_group_media_items = deps["normalize_group_media_items"]
    normalize_group_video_meta = deps["normalize_group_video_meta"]
    run_comfyui_video_i2v_workflow = deps["run_comfyui_video_i2v_workflow"]
    safe_project_id = deps["safe_project_id"]
    video_i2v_settings = deps["video_i2v_settings"]

    def update_video_group_image(project: dict[str, Any], group_id: str, image_meta: dict[str, Any]) -> dict[str, Any]:
        group = find_video_group(project, group_id)
        if not group:
            raise RuntimeError("Video group not found")
        group["image"] = normalize_group_image_meta(image_meta)
        group["media_items"] = normalize_group_media_items(group.get("media_items"), group)
        return group["image"]

    def update_video_group_video(project: dict[str, Any], group_id: str, video_meta: dict[str, Any]) -> dict[str, Any]:
        group = find_video_group(project, group_id)
        if not group:
            raise RuntimeError("Video group not found")
        group["video"] = normalize_group_video_meta(video_meta)
        group["media_items"] = normalize_group_media_items(group.get("media_items"), group)
        return group["video"]

    def generate_chunk_video_now(project: dict[str, Any], group_id: str, chunk_id: str, *, replace: bool = False, bulk_auto_place: bool = False, auto_sequence_id: str = "", source_media_id: str = "") -> dict[str, Any]:
        group = find_video_group(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        sequence_id = auto_sequence_id or group_chunk_sequence_id(group)
        source_candidates = auto_chunk_image_sources_for_video(project, group, chunk_id, sequence_id)
        source_item = next((item for item in source_candidates if str(item.get("id") or "") == str(source_media_id)), None) if source_media_id else (source_candidates[0] if source_candidates else None)
        pseudo_group, chunk, (start, duration) = group_with_chunk_video_source(project, group, chunk_id, source_item)
        settings = image_settings(project)
        vsettings = video_i2v_settings(project)
        output_prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", f"xtts_i2v_{safe_project_id(str(project.get('id') or active_project_id()))}_{group_id}_{chunk_id}").strip("_")
        video_meta = run_comfyui_video_i2v_workflow(project, pseudo_group, settings, vsettings, output_prefix)
        video_meta["status"] = "ready"
        items = normalize_group_media_items(group.get("media_items"), group)
        allow_auto_replace = bool(bulk_auto_place and source_item)
        if replace:
            items = [item for item in items if not (item.get("type") == "video" and str(item.get("chunk_id") or "") == str(chunk_id) and item.get("prompt_scope") == "chunk" and item.get("source") == "generated")]
        if allow_auto_replace:
            source_item = source_item or next((item for item in items if item.get("type") == "image" and str(item.get("chunk_id") or "") == str(chunk_id) and item.get("prompt_scope") == "chunk" and item.get("timeline_source") == "auto_bulk_image" and item.get("auto_sequence_id") == sequence_id), None)
        media_item = normalize_group_media_item({
            "id": f"chunk_video_{chunk_id}_{uuid.uuid4().hex[:8]}",
            "type": "video",
            "path": video_meta.get("path", ""),
            "url": video_meta.get("url", ""),
            "label": f"Видео чанка #{int(chunk.get('order') or 0) + 1}",
            "role": "chunk",
            "source": "generated",
            "scheduled": allow_auto_replace,
            "start_offset_sec": start,
            "duration_sec": duration,
            "fit": "cover",
            "kind": "timeline_block" if allow_auto_replace else "media_asset",
            "timeline_source": "auto_bulk_video" if allow_auto_replace else "",
            "auto_sequence_id": sequence_id if allow_auto_replace else "",
            "chunk_id": str(chunk_id),
            "prompt_scope": "chunk",
            "sequence_index": source_item.get("sequence_index") if source_item else 1,
            "sequence_count": source_item.get("sequence_count") if source_item else 1,
            "prompt_source": str(chunk.get("prompt_source") or "fallback"),
            "positive_prompt": pseudo_group.get("grok_video_prompt") or pseudo_group.get("animation_positive_prompt") or "",
            "negative_prompt": pseudo_group.get("animation_negative_prompt") or "",
            "provider": video_meta.get("provider", ""),
            "model": video_meta.get("model", ""),
            "created_at": time.time(),
        }, len(items))
        if not media_item:
            raise RuntimeError("Generated video did not produce a media item")
        replaced = False
        if allow_auto_replace and source_item:
            next_items: list[dict[str, Any]] = []
            source_id = str(source_item.get("id") or "")
            for item in items:
                if str(item.get("id") or "") == source_id:
                    next_items.append(media_item)
                    replaced = True
                else:
                    next_items.append(item)
            items = next_items
        if not replaced:
            items.append(media_item)
        group["media_items"] = normalize_group_media_items(items, group)
        return media_item

    def generate_chunk_image_now(project: dict[str, Any], group_id: str, chunk_id: str, *, replace: bool = False, bulk_auto_place: bool = False, auto_sequence_id: str = "", sequence_index: int = 1, sequence_count: int = 1) -> dict[str, Any]:
        group = find_video_group(project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        chunk = find_chunk_in_group(project, group, chunk_id)
        settings = image_settings(project)
        prompt_bundle = format_chunk_image_prompt(project, group, chunk, settings)
        pseudo_group = dict(group)
        pseudo_group["id"] = f"{group_id}_{chunk_id}"
        pseudo_group["title"] = f"{group.get('title') or group_id} · чанк {int(chunk.get('order') or 0) + 1}"
        pseudo_group["visual_prompt"] = prompt_bundle.get("positive_prompt", "")
        pseudo_group["negative_prompt"] = prompt_bundle.get("negative_prompt", "")
        safe_sequence_count = max(1, min(100, int(sequence_count or 1)))
        safe_sequence_index = max(1, min(safe_sequence_count, int(sequence_index or 1)))
        image_meta = generate_group_image(project, pseudo_group, settings, prompt_bundle)
        start, duration = chunk_timeline_span(project, group, chunk_id)
        if safe_sequence_count > 1:
            slot = duration / safe_sequence_count
            start = start + slot * (safe_sequence_index - 1)
            duration = slot
        items = normalize_group_media_items(group.get("media_items"), group)
        sequence_id = auto_sequence_id or group_chunk_sequence_id(group)
        allow_auto_place = bool(bulk_auto_place and sequence_id and auto_chunk_sequence_state(project, group, sequence_id) in {"empty", "auto_images"})
        if replace:
            items = [item for item in items if not (str(item.get("chunk_id") or "") == str(chunk_id) and item.get("prompt_scope") == "chunk" and item.get("source") == "generated")]
        media_item = normalize_group_media_item({
            "id": f"chunk_image_{chunk_id}_{uuid.uuid4().hex[:8]}",
            "type": "image",
            "path": image_meta.get("path", ""),
            "url": image_meta.get("url", ""),
            "label": f"Чанк #{int(chunk.get('order') or 0) + 1} · {safe_sequence_index}/{safe_sequence_count}",
            "role": "chunk",
            "source": "generated",
            "scheduled": allow_auto_place,
            "start_offset_sec": start,
            "duration_sec": duration,
            "fit": "cover",
            "kind": "timeline_block" if allow_auto_place else "media_asset",
            "timeline_source": "auto_bulk_image" if allow_auto_place else "",
            "auto_sequence_id": sequence_id if allow_auto_place else "",
            "sequence_index": safe_sequence_index,
            "sequence_count": safe_sequence_count,
        }, len(items))
        if not media_item:
            raise RuntimeError("Generated image did not produce a media item")
        media_item.update({
            "chunk_id": str(chunk_id),
            "prompt_scope": "chunk",
            "prompt_source": str(chunk.get("prompt_source") or "fallback"),
            "positive_prompt": prompt_bundle.get("positive_prompt", ""),
            "negative_prompt": prompt_bundle.get("negative_prompt", ""),
            "provider": image_meta.get("provider", ""),
            "model": image_meta.get("model", ""),
            "created_at": time.time(),
        })
        items.append(media_item)
        group["media_items"] = normalize_group_media_items(items, group)
        return media_item

    return {
        "generate_chunk_image_now": generate_chunk_image_now,
        "generate_chunk_video_now": generate_chunk_video_now,
        "update_video_group_image": update_video_group_image,
        "update_video_group_video": update_video_group_video,
    }
