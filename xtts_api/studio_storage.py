import hashlib
import re
import time
from pathlib import Path
from typing import Any


def validate_project_id(value: str) -> str:
    """Return a normalized project id or raise ValueError for unsafe storage names."""
    project_id = (value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", project_id):
        raise ValueError("Invalid project_id")
    if ".." in project_id or "/" in project_id or "\\" in project_id or Path(project_id).is_absolute():
        raise ValueError("Invalid project_id")
    return project_id


def normalize_project_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Return normalized project index metadata with a safe project id."""
    project_id = validate_project_id(str(meta.get("id") or meta.get("project_id") or "default"))
    now = time.time()
    return {
        "id": project_id,
        "name": str(meta.get("name") or project_id),
        "created_at": float(meta.get("created_at") or now),
        "updated_at": float(meta.get("updated_at") or now),
    }


def project_metadata_from_project(project: dict[str, Any], project_id: str) -> dict[str, Any]:
    """Return project index metadata derived from project storage data."""
    now = time.time()
    return {
        "id": project_id,
        "name": str(project.get("name") or project_id),
        "created_at": float(project.get("created_at") or now),
        "updated_at": float(project.get("updated_at") or now),
    }


def normalize_loaded_project_basics(project: dict[str, Any], project_id: str, default_settings: dict[str, Any]) -> dict[str, Any]:
    """Normalize basic fields and settings on an already-loaded project dictionary."""
    project["id"] = project_id
    project.setdefault("name", project_id)
    project.setdefault("settings", default_settings.copy())
    for key, value in default_settings.items():
        project["settings"].setdefault(key, value)
    if (
        str(project["settings"].get("image_provider") or default_settings["image_provider"]).strip().lower() == "comfyui"
        and not project["settings"].get("image_comfyui_autostart_user_set")
        and project["settings"].get("image_comfyui_autostart") is False
    ):
        project["settings"]["image_comfyui_autostart"] = True
    return project


def normalize_loaded_chunk_legacy_version(chunk: dict[str, Any]) -> dict[str, Any]:
    """Seed an already-loaded chunk with its legacy audio version when needed."""
    chunk.setdefault("versions", [])
    chunk.setdefault("selected_version_id", "")
    if chunk.get("audio_path") and not chunk.get("versions"):
        chunk["versions"] = [{
            "id": "legacy",
            "label": "legacy",
            "audio_path": chunk.get("audio_path", ""),
            "created_at": chunk.get("generated_at"),
            "settings": {},
            "duration_sec": chunk.get("duration_sec", 0.0),
        }]
        chunk["selected_version_id"] = "legacy"
    return chunk


def normalize_loaded_chunk_selected_version(chunk: dict[str, Any]) -> dict[str, Any]:
    """Ensure an already-loaded chunk selection points at an existing version."""
    versions = chunk.get("versions") if isinstance(chunk.get("versions"), list) else []
    selected_id = chunk.get("selected_version_id")
    selected = next((version for version in versions if isinstance(version, dict) and version.get("id") == selected_id), None)
    if versions and not selected:
        fallback = next((version for version in reversed(versions) if isinstance(version, dict)), None)
        chunk["selected_version_id"] = fallback.get("id", "") if fallback else ""
    elif not versions:
        chunk["selected_version_id"] = ""
    return chunk


def ordered_project_chunks(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Return valid project chunk dictionaries sorted by their stored order."""
    return sorted([chunk for chunk in project.get("chunks", []) if isinstance(chunk, dict)], key=lambda c: c.get("order", 0))


def chunk_order_ids(chunks: list[dict[str, Any]]) -> list[str]:
    """Return non-empty chunk ids from an already-ordered chunk list."""
    return [str(chunk.get("id") or "") for chunk in chunks if str(chunk.get("id") or "")]


def group_chunk_sequence_id(group: dict[str, Any]) -> str:
    """Return a stable short sequence id for a group's current chunk id ordering."""
    raw = "|".join(str(item) for item in group.get("chunk_ids", []) if str(item))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12] if raw else ""


def video_group_coverage_error(flattened: list[str], expected_ids: list[str], scope_label: str) -> str:
    """Return a diagnostic for normalized video-group chunk id coverage mismatches."""
    missing = [chunk_id for chunk_id in expected_ids if chunk_id not in flattened]
    extra = [chunk_id for chunk_id in flattened if chunk_id not in expected_ids]
    details: list[str] = []
    if missing:
        details.append(f"missing ids: {', '.join(missing[:20])}{'…' if len(missing) > 20 else ''}")
    if extra:
        details.append(f"extra ids: {', '.join(extra[:20])}{'…' if len(extra) > 20 else ''}")
    if not details:
        details.append("same ids but wrong order or duplicated ids")
    return f"Flattened group chunk_ids must exactly match ordered {scope_label} chunk ids ({'; '.join(details)})"


def repaired_video_group_spans(
    anchors: list[tuple[int, int, dict[str, Any], int, list[str]]],
    ordered_id_count: int,
) -> list[tuple[int, int, dict[str, Any], list[str]]]:
    """Return repaired contiguous video-group spans from sorted anchor boundaries."""
    spans: list[tuple[int, int, dict[str, Any], list[str]]] = []
    previous_end = -1
    for idx, (first_pos, last_pos, raw_group, _raw_index, group_ids) in enumerate(anchors):
        next_first = anchors[idx + 1][0] if idx + 1 < len(anchors) else ordered_id_count
        start = previous_end + 1
        if idx == 0:
            start = 0
        end = max(last_pos, next_first - 1)
        if idx == len(anchors) - 1:
            end = ordered_id_count - 1
        end = min(ordered_id_count - 1, max(start, end))
        if start <= previous_end:
            start = previous_end + 1
        if start >= ordered_id_count:
            break
        spans.append((start, end, raw_group, group_ids))
        previous_end = end

    if previous_end < ordered_id_count - 1 and spans:
        start, _end, raw_group, group_ids = spans[-1]
        spans[-1] = (start, ordered_id_count - 1, raw_group, group_ids)

    return spans


def collect_repaired_video_group_anchors(
    raw_groups: Any,
    ordered_ids: list[str],
) -> tuple[list[tuple[int, int, dict[str, Any], int, list[str]]], set[str], list[str], list[str]]:
    """Return usable repaired-group anchors and invalid id diagnostics from already-loaded group data."""
    valid_ids = set(ordered_ids)
    position_by_id = {chunk_id: idx for idx, chunk_id in enumerate(ordered_ids)}
    anchors: list[tuple[int, int, dict[str, Any], int, list[str]]] = []
    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    extra_ids: list[str] = []

    if not isinstance(raw_groups, list):
        return anchors, seen_ids, duplicate_ids, extra_ids

    for raw_index, raw_group in enumerate(raw_groups):
        if not isinstance(raw_group, dict):
            continue
        raw_chunk_ids = raw_group.get("chunk_ids")
        if not isinstance(raw_chunk_ids, list):
            continue
        group_ids: list[str] = []
        for raw_id in raw_chunk_ids:
            chunk_id = str(raw_id)
            if chunk_id not in valid_ids:
                extra_ids.append(chunk_id)
                continue
            if chunk_id in seen_ids:
                duplicate_ids.append(chunk_id)
                continue
            seen_ids.add(chunk_id)
            group_ids.append(chunk_id)
        if not group_ids:
            continue
        positions = sorted(position_by_id[chunk_id] for chunk_id in group_ids)
        anchors.append((positions[0], positions[-1], raw_group, raw_index, group_ids))

    anchors.sort(key=lambda item: (item[0], item[1], item[3]))
    return anchors, seen_ids, duplicate_ids, extra_ids


def normalize_video_group_playback_speed(value: Any) -> float:
    """Return a clamped playback speed for already-provided video group data."""
    try:
        return round(max(0.25, min(2.0, float(value if value is not None else 1.0) or 1.0)), 3)
    except (TypeError, ValueError):
        return 1.0


def renumber_project_chunks(project: dict[str, Any]) -> None:
    """Sort and compact chunk order values on an already-loaded project."""
    project["chunks"] = ordered_project_chunks(project)
    for idx, chunk in enumerate(project["chunks"]):
        chunk["order"] = idx


def prepare_projects_index(index: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized, de-duplicated projects index without performing I/O."""
    projects = [normalize_project_metadata(item) for item in (index.get("projects") or []) if isinstance(item, dict)]
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in projects:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        unique.append(item)
    active = str(index.get("last_active_project_id") or (unique[0]["id"] if unique else ""))
    if active and active not in seen:
        active = unique[0]["id"] if unique else ""
    return {"projects": unique, "last_active_project_id": active}


def prepare_loaded_projects_index(existing_projects: list[dict[str, Any]], requested_active_project_id: str) -> dict[str, Any]:
    """Return the projects-index load result from already-existing project metadata."""
    active = str(requested_active_project_id or (existing_projects[0]["id"] if existing_projects else ""))
    if active not in {item["id"] for item in existing_projects}:
        active = existing_projects[0]["id"] if existing_projects else ""
    return {
        "projects": sorted(existing_projects, key=lambda item: item.get("updated_at", 0), reverse=True),
        "last_active_project_id": active,
    }


def upsert_project_index_metadata(index: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """Return a projects index with metadata replaced by id or appended without performing I/O."""
    project_id = str(meta.get("id") or "")
    projects = list(index.get("projects", []))
    for idx, item in enumerate(projects):
        if isinstance(item, dict) and item.get("id") == project_id:
            projects[idx] = meta
            break
    else:
        projects.append(meta)
    return {**index, "projects": projects}


def prepare_project_save_index_update(index: dict[str, Any], project: dict[str, Any], project_id: str) -> dict[str, Any]:
    """Return a projects index updated with metadata from an already-prepared project save."""
    meta = project_metadata_from_project(project, project_id)
    return upsert_project_index_metadata(index, meta)


def prepare_project_create_index_update(index: dict[str, Any], meta: dict[str, Any], project_id: str) -> dict[str, Any]:
    """Return a projects index updated for an already-created project without performing I/O."""
    return {**upsert_project_index_metadata(index, meta), "last_active_project_id": validate_project_id(project_id)}


def prepare_active_project_index_update(index: dict[str, Any], project_id: str) -> dict[str, Any]:
    """Return a projects index with a validated active project id without performing I/O."""
    return {**index, "last_active_project_id": validate_project_id(project_id)}


def prepare_project_delete_index_update(index: dict[str, Any], deleted_project_id: str) -> dict[str, Any]:
    """Return a projects index with one project removed and active id fallback selected."""
    project_id = validate_project_id(deleted_project_id)
    projects = [item for item in (index.get("projects") or []) if isinstance(item, dict)]
    remaining = [item for item in projects if item.get("id") != project_id]
    active = index.get("last_active_project_id")
    if active == project_id:
        active = remaining[0]["id"]
    return {"projects": remaining, "last_active_project_id": active}


def prepare_created_project_response(project: dict[str, Any], projects: list[dict[str, Any]], project_id: str) -> dict[str, Any]:
    """Return the API response payload for an already-created, already-loaded project."""
    return {"project": project, "projects": projects, "last_active_project_id": project_id}


def prepare_deleted_project_response(projects: list[dict[str, Any]], active_project_id: str) -> dict[str, Any]:
    """Return the API response payload for an already-deleted, already-persisted project index."""
    return {"projects": projects, "last_active_project_id": active_project_id}


def prepare_patched_project_response(project: dict[str, Any], projects: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the API response payload for an already-patched, already-reloaded project."""
    return {"project": project, "projects": projects}


def prepare_active_project_response(project: dict[str, Any], project_id: str) -> dict[str, Any]:
    """Return the API response payload for an already-activated, already-loaded project."""
    return {"project": project, "project_id": project_id}


def prepare_queued_task_response(queued_task: dict[str, Any], queue: list[dict[str, Any]], progress: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Return the API response payload for an already-queued single task."""
    return {"queued_task": queued_task, "queue": queue, "progress": progress, "project": project}


def prepare_optional_queued_task_response(queued_task: dict[str, Any] | None, queue: list[dict[str, Any]], progress: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Return the API response payload for an already-attempted optional queued task."""
    return {"queued_tasks": [queued_task] if queued_task else [], "skipped_count": 0 if queued_task else 1, "queue": queue, "progress": progress, "project": project}


def prepare_optional_queued_tasks_response(queued_task: dict[str, Any] | None, queue: list[dict[str, Any]], progress: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Return the API response payload for an already-attempted optional queued task list."""
    return {"queued_tasks": [queued_task] if queued_task else [], "queue": queue, "progress": progress, "project": project}


def prepare_queued_tasks_plain_response(queued_tasks: list[dict[str, Any]], queue: list[dict[str, Any]], progress: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Return the API response payload for already-computed queued tasks without skipped metadata."""
    return {"queued_tasks": queued_tasks, "queue": queue, "progress": progress, "project": project}


def prepare_queued_tasks_response(queued_tasks: list[dict[str, Any]], skipped_count: int, queue: list[dict[str, Any]], progress: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Return the API response payload for already-computed queued tasks."""
    return {"queued_tasks": queued_tasks, "skipped_count": skipped_count, "queue": queue, "progress": progress, "project": project}


def prepare_queued_tasks_skipped_response(queued_tasks: list[dict[str, Any]], skipped: list[dict[str, Any]], queue: list[dict[str, Any]], progress: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Return the API response payload for already-computed queued tasks with skipped details."""
    return {"queued_tasks": queued_tasks, "skipped": skipped, "skipped_count": len(skipped), "queue": queue, "progress": progress, "project": project}


def prepare_queued_tasks_empty_skipped_response(queued_tasks: list[dict[str, Any]], queue: list[dict[str, Any]], progress: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Return the API response payload for already-computed queued tasks with no skipped entries."""
    return {"queued_tasks": queued_tasks, "skipped": [], "skipped_count": 0, "queue": queue, "progress": progress, "project": project}


def prepare_queue_progress_response(queue: list[dict[str, Any]], progress: dict[str, Any]) -> dict[str, Any]:
    """Return the API response payload for already-computed queue and progress snapshots."""
    return {"queue": queue, "progress": progress}


def prepare_project_queue_progress_response(project: dict[str, Any], queue: list[dict[str, Any]], progress: dict[str, Any]) -> dict[str, Any]:
    """Return an already-enriched project payload with queue and progress snapshots."""
    return {**project, "queue": queue, "progress": progress}


def prepare_clear_completed_tasks_response(removed: int, queue: list[dict[str, Any]], progress: dict[str, Any]) -> dict[str, Any]:
    """Return the API response payload for already-cleared completed queue tasks."""
    return {"removed": removed, "queue": queue, "progress": progress}
