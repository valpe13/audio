import re
import shutil
import time
import unicodedata
import uuid
from typing import Any

from fastapi import File, HTTPException, Query, UploadFile

try:
    from .studio_route_deps import dep
    from .studio_schemas import ChunkCreate, ChunkUpdate, ExportRequest, SplitRequest, VersionSelect
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep
    from studio_schemas import ChunkCreate, ChunkUpdate, ExportRequest, SplitRequest, VersionSelect


def register_chunk_export_routes(app: Any, deps: dict[str, Any]) -> None:
    """Register chunk mutation/generation, export, and music upload routes."""

    @app.post("/api/chunks/split")
    def split_chunks(payload: SplitRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        try:
            # Strict two-phase flow:
            # 1) perform the normal deterministic splitter and assign final chunk ids/order/pauses;
            # 2) optionally ask Grok to post-process only those existing chunk texts with stress marks.
            # Grok never receives the full source text and cannot influence boundaries/count/order.
            chunks = []
            split_min = dep(deps, "clamp_pause")(payload.split_pause_after_min)
            split_max = dep(deps, "clamp_pause")(payload.split_pause_after_max)
            if split_max < split_min:
                split_min, split_max = split_max, split_min
            source_text = dep(deps, "repair_mojibake_text")(payload.text)[0]
            split_items = dep(deps, "split_text_into_chunks")(source_text, payload.max_chars)
            for idx, item in enumerate(split_items):
                text = str(item.get("text") or "")
                boundary_type = str(item.get("boundary_type") or "sentence")
                pause_min, pause_max = dep(deps, "pause_range_for_boundary")(boundary_type, split_min, split_max)
                pause_after = dep(deps, "stable_split_pause_after")(project, text, idx, pause_min, pause_max, boundary_type)
                chunks.append({
                    "id": uuid.uuid4().hex[:12],
                    "order": idx,
                    "text": text,
                    "boundary_type": boundary_type,
                    "pause_after": pause_after,
                    "audio_path": "",
                    "versions": [],
                    "selected_version_id": "",
                    "duration_sec": 0.0,
                    "generated_at": None,
                })
                dep(deps, "normalize_chunk_pauses")(project, chunks[-1])
            stress_note = "disabled"
            try:
                stress_marked, stress_note = dep(deps, "add_ai_stress_to_chunks_safe")(project, chunks)
            except Exception as exc:
                stress_marked = 0
                detail = dep(deps, "truncate_text")(str(exc), 220)
                stress_note = f"Grok stress marking skipped after non-fatal error: {type(exc).__name__}: {detail}; kept original chunks"
                dep(deps, "LOGGER").warning("Optional Grok stress marking block failed during chunk split; keeping original chunks: %s: %s", type(exc).__name__, exc)
                dep(deps, "ensure_chunk_stress_fields")(chunks, source="original")
            for chunk in chunks:
                dep(deps, "sanitize_split_chunk_for_response")(chunk)
            project["full_text"] = source_text
            project["chunks"] = chunks
            if (payload.generate_group_prompts if payload.generate_group_prompts is not None else bool(project.get("settings", {}).get("ai_generate_group_prompts_on_split", dep(deps, "DEFAULT_SETTINGS")["ai_generate_group_prompts_on_split"]))):
                video = project.setdefault("arrangement", {}).setdefault("video", {})
                video["groups"] = dep(deps, "fallback_video_groups")(chunks, 4, exclude_people=bool(project.get("settings", {}).get("image_exclude_people", dep(deps, "DEFAULT_SETTINGS")["image_exclude_people"])))
            else:
                project.setdefault("arrangement", {}).setdefault("video", {})["groups"] = []
            status = f"Standard split into {len(chunks)} chunks"
            if stress_note != "disabled":
                status += f" · {stress_note}"
            dep(deps, "set_status")(project, status)
            return dep(deps, "enrich_project")(project)
        except Exception as exc:
            detail = dep(deps, "truncate_text")(str(exc), 400)
            dep(deps, "LOGGER").exception("Chunk split failed: %s: %s", type(exc).__name__, exc)
            dep(deps, "set_status")(project, f"Chunk split failed: {type(exc).__name__}: {detail}")
            raise HTTPException(status_code=400, detail=f"Chunk split failed: {type(exc).__name__}: {detail}") from exc


    @app.post("/api/chunks/{chunk_id}/select-version")
    def select_chunk_version(chunk_id: str, payload: VersionSelect, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        chunk = next((c for c in project["chunks"] if c["id"] == chunk_id), None)
        if not chunk:
            raise HTTPException(status_code=404, detail="Chunk not found")
        version = next((v for v in chunk.get("versions", []) if v.get("id") == payload.version_id), None)
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")
        chunk["selected_version_id"] = payload.version_id
        chunk.pop("audio_selection_stale", None)
        dep(deps, "sync_chunk_to_selected_version")(chunk)
        dep(deps, "set_status")(project, f"Selected {version.get('label', 'version')} for chunk {chunk.get('order', 0) + 1}")
        return dep(deps, "enrich_project")(project)


    @app.post("/api/chunks")
    def create_chunk_endpoint(payload: ChunkCreate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        chunks = sorted(project.get("chunks", []), key=lambda c: c.get("order", 0))
        insert_at = len(chunks)
        if payload.insert_after_chunk_id:
            idx = next((i for i, chunk in enumerate(chunks) if chunk.get("id") == payload.insert_after_chunk_id), None)
            if idx is not None:
                insert_at = idx + 1
        elif payload.order is not None:
            insert_at = max(0, min(len(chunks), int(payload.order)))
        chunk = dep(deps, "create_chunk_dict")(project, payload, insert_at)
        chunks.insert(insert_at, chunk)
        project["chunks"] = chunks
        dep(deps, "renumber_project_chunks")(project)
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, f"Chunk added at position {insert_at + 1}")
        return dep(deps, "enrich_project")(project)


    @app.delete("/api/chunks/{chunk_id}")
    def delete_chunk_endpoint(chunk_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        before = len(project.get("chunks", []))
        project["chunks"] = [chunk for chunk in project.get("chunks", []) if chunk.get("id") != chunk_id]
        if len(project["chunks"]) == before:
            raise HTTPException(status_code=404, detail="Chunk not found")
        for group in project.setdefault("arrangement", {}).setdefault("video", {}).setdefault("groups", []):
            if isinstance(group, dict) and isinstance(group.get("chunk_ids"), list):
                group["chunk_ids"] = [item for item in group["chunk_ids"] if item != chunk_id]
        dep(deps, "renumber_project_chunks")(project)
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, "Chunk deleted")
        return dep(deps, "enrich_project")(project)


    @app.patch("/api/chunks/{chunk_id}")
    def update_chunk(chunk_id: str, payload: ChunkUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        chunk = next((c for c in project["chunks"] if c["id"] == chunk_id), None)
        if not chunk:
            raise HTTPException(status_code=404, detail="Chunk not found")
        dep(deps, "normalize_chunk_versions")(chunk)
        old_text = str(chunk.get("text") or "")
        repaired_text = dep(deps, "repair_mojibake_text")(payload.text)[0] if payload.text is not None else None
        text_changed = repaired_text is not None and repaired_text != old_text
        if text_changed:
            chunk["text"] = repaired_text
            chunk["tts_text"] = unicodedata.normalize("NFC", repaired_text)
            chunk["stressed_text"] = chunk["tts_text"]
            chunk["stress_source"] = "original"
            dep(deps, "reset_current_chunk_audio_selection")(chunk)
        if payload.tts_text is not None:
            repaired_tts_text = dep(deps, "repair_mojibake_text")(payload.tts_text)[0]
            base_text = str(chunk.get("text") or "")
            if dep(deps, "compact_stress_validation_text")(repaired_tts_text) != dep(deps, "compact_stress_validation_text")(base_text):
                if text_changed and dep(deps, "compact_stress_validation_text")(repaired_tts_text) == dep(deps, "compact_stress_validation_text")(old_text):
                    repaired_tts_text = base_text
                else:
                    raise HTTPException(status_code=400, detail="TTS text may only add or remove stress marks; edit Original text to rewrite content")
            chunk["tts_text"] = unicodedata.normalize("NFC", repaired_tts_text)
            chunk["stressed_text"] = chunk["tts_text"]
            chunk["stress_source"] = "manual" if chunk["tts_text"] != base_text else "original"
            dep(deps, "reset_current_chunk_audio_selection")(chunk)
        if payload.pause_after is not None:
            chunk["pause_after"] = payload.pause_after
        prompt_patch = payload.dict(exclude_unset=True)
        if any(key in prompt_patch for key in dep(deps, "CHUNK_PROMPT_LIMITS")):
            dep(deps, "normalize_chunk_prompt_fields")(chunk, prompt_patch, source=prompt_patch.get("prompt_source") or "manual")
        dep(deps, "normalize_chunk_pauses")(project, chunk)
        if payload.order is not None:
            chunk["order"] = payload.order
        project["chunks"] = sorted(project["chunks"], key=lambda c: c.get("order", 0))
        for idx, item in enumerate(project["chunks"]):
            item["order"] = idx
        dep(deps, "set_status")(project, "Chunk updated")
        return dep(deps, "enrich_project")(project)


    @app.post("/api/chunks/{chunk_id}/move/{direction}")
    def move_chunk(chunk_id: str, direction: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        chunks = sorted(project["chunks"], key=lambda c: c.get("order", 0))
        idx = next((i for i, c in enumerate(chunks) if c["id"] == chunk_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="Chunk not found")
        new_idx = idx - 1 if direction == "up" else idx + 1 if direction == "down" else idx
        if 0 <= new_idx < len(chunks):
            chunks[idx], chunks[new_idx] = chunks[new_idx], chunks[idx]
        for order, chunk in enumerate(chunks):
            chunk["order"] = order
        project["chunks"] = chunks
        dep(deps, "set_status")(project, "Chunk order updated")
        return dep(deps, "enrich_project")(project)


    @app.post("/api/chunks/{chunk_id}/generate")
    def generate_chunk_endpoint(chunk_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        if not any(c["id"] == chunk_id for c in project["chunks"]):
            raise HTTPException(status_code=404, detail="Chunk not found")
        chunk = next(c for c in project["chunks"] if c["id"] == chunk_id)
        if not dep(deps, "clean_text")(chunk.get("text", "")):
            raise HTTPException(status_code=400, detail="Chunk text is empty")
        task = dep(deps, "enqueue_task")("generate_chunk", chunk_id, project.get("id"))
        dep(deps, "set_status")(project, f"Queued chunk {chunk.get('order', 0) + 1} generation")
        return dep(deps, "prepare_queued_task_response")(task, dep(deps, "queue_snapshot")(project.get("id")), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(dep(deps, "load_project")(project.get("id"))))


    @app.post("/api/chunks/generate-all")
    def generate_all_chunks(project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        queued = 0
        for chunk in sorted(project["chunks"], key=lambda c: c.get("order", 0)):
            if not chunk.get("audio_path") and dep(deps, "clean_text")(chunk.get("text", "")):
                dep(deps, "enqueue_task")("generate_chunk", chunk["id"], project.get("id"))
                queued += 1
        dep(deps, "set_status")(project, f"Queued {queued} missing chunk(s)")
        return dep(deps, "prepare_project_queue_progress_response")(dep(deps, "enrich_project")(dep(deps, "load_project")(project.get("id"))), dep(deps, "queue_snapshot")(project.get("id")), dep(deps, "progress_snapshot")())


    @app.post("/api/export")
    def export_endpoint(payload: ExportRequest | None = None, project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        request = payload or ExportRequest()
        task = dep(deps, "enqueue_task")("export", project_id=project.get("id"), payload=request.dict(), label="Export video" if str(request.export_type).startswith("video") else f"Export {request.audio_format.upper()}")
        dep(deps, "set_status")(project, "Export queued", True)
        return dep(deps, "prepare_queued_task_response")(task, dep(deps, "queue_snapshot")(project.get("id")), dep(deps, "progress_snapshot")(), dep(deps, "enrich_project")(project))


    @app.post("/api/upload/music")
    def upload_music(file: UploadFile = File(...), project_id: str | None = Query(default=None)) -> dict[str, Any]:
        project = dep(deps, "load_project")(project_id)
        uploads_dir = dep(deps, "project_uploads_dir")(project.get("id"))
        uploads_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^\w.а-яА-ЯёЁ-]+", "_", file.filename or "music.wav")
        out = uploads_dir / f"{int(time.time())}_{safe_name}"
        with out.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        music = project.setdefault("arrangement", {}).setdefault("music", {})
        sources = music.get("sources") if isinstance(music.get("sources"), list) else []
        source = {"id": uuid.uuid4().hex[:10], "path": dep(deps, "rel_path")(out), "label": out.name}
        sources.append(source)
        music["sources"] = sources
        lanes = music.get("lanes") if isinstance(music.get("lanes"), list) else []
        lanes.append({"id": uuid.uuid4().hex[:10], "source_id": source["id"], "path": dep(deps, "rel_path")(out), "label": out.name, "enabled": True, "loop": False, "volume": 1.0, "volume_envelope": [{"time": 0.0, "volume": 1.0}], "order": len(lanes), "clips": [{"id": uuid.uuid4().hex[:10], "start_time": 0.0, "offset_sec": 0.0, "duration_sec": 0.0, "volume": 1.0}]})
        music["lanes"] = lanes
        dep(deps, "normalize_arrangement")(project)
        dep(deps, "set_status")(project, "Music uploaded")
        return {"path": dep(deps, "rel_path")(out), "project": dep(deps, "enrich_project")(project)}
