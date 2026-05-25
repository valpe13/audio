import queue
import re
import threading
import time
import uuid
from typing import Any

try:
    from .studio_route_deps import dep
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep


def make_queue_runtime_helpers(deps: dict[str, Any]) -> dict[str, Any]:
    """Build XTTS Studio background task queue state and worker helpers."""

    queue_lock = threading.Lock()
    task_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    tasks: list[dict[str, Any]] = []
    state: dict[str, Any] = {
        "worker_started": False,
        "progress": {"active": False, "percent": 0, "message": "Idle", "current_task_id": None, "updated_at": time.time()},
    }

    def progress_snapshot() -> dict[str, Any]:
        with queue_lock:
            return dict(state["progress"])

    def queue_snapshot(project_id: str | None = None) -> list[dict[str, Any]]:
        with queue_lock:
            cutoff = time.time() - 3600
            pid = dep(deps, "safe_project_id")(project_id) if project_id else None
            return [dict(task) for task in tasks if (not pid or task.get("project_id") == pid) and (dep(deps, "task_is_queued_or_running")(task) or task.get("updated_at", 0) >= cutoff)]

    def set_progress(*, active: bool, percent: float, message: str, current_task_id: str | None = None) -> None:
        with queue_lock:
            state["progress"].update({
                "active": active,
                "percent": round(max(0.0, min(100.0, percent)), 1),
                "message": message,
                "current_task_id": current_task_id,
                "updated_at": time.time(),
            })

    def ensure_worker() -> None:
        if state["worker_started"]:
            return
        state["worker_started"] = True
        thread = threading.Thread(target=queue_worker, name="xtts-studio-worker", daemon=True)
        thread.start()

    def enqueue_task(
        kind: str,
        chunk_id: str | None = None,
        project_id: str | None = None,
        payload: dict[str, Any] | None = None,
        label: str | None = None,
        stage: str | None = None,
    ) -> dict[str, Any]:
        ensure_worker()
        pid = dep(deps, "safe_project_id")(project_id or dep(deps, "active_project_id")())
        task = {
            "id": uuid.uuid4().hex[:10],
            "kind": kind,
            "project_id": pid,
            "chunk_id": chunk_id,
            "status": "queued",
            "message": "Queued",
            "label": label or kind,
            "stage": stage or "queued",
            "progress_percent": 0,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        if payload is not None:
            task["payload"] = payload
            task["params"] = payload
        with queue_lock:
            tasks.append(task)
            state["progress"].update({
                "active": True,
                "percent": max(float(state["progress"].get("percent") or 0), 2.0),
                "message": f"Queued {kind}",
                "current_task_id": state["progress"].get("current_task_id"),
                "updated_at": time.time(),
            })
        return task

    def active_task_by_kind_project(kind: str, project_id: str) -> dict[str, Any] | None:
        pid = dep(deps, "safe_project_id")(project_id)
        with queue_lock:
            for task in tasks:
                if task.get("kind") == kind and task.get("project_id") == pid and dep(deps, "task_is_queued_or_running")(task):
                    return dict(task)
        return None

    def update_task(task_id: str, **updates: Any) -> None:
        with queue_lock:
            for task in tasks:
                if task["id"] == task_id:
                    task.update(updates)
                    task["updated_at"] = time.time()
                    break

    def remove_task(task_id: str) -> bool:
        with queue_lock:
            for task in tasks:
                if task["id"] == task_id and task.get("status") == "queued":
                    task["status"] = "cancelled"
                    task["message"] = "Cancelled"
                    task["updated_at"] = time.time()
                    return True
        return False

    def clear_completed_tasks(project_id: str | None = None) -> int:
        finished_statuses = {"done", "failed", "cancelled", "succeeded", "success", "error"}
        pid = dep(deps, "safe_project_id")(project_id) if project_id else None
        with queue_lock:
            before = len(tasks)
            tasks[:] = [task for task in tasks if not ((not pid or task.get("project_id") == pid) and task.get("status") in finished_statuses)]
            return before - len(tasks)

    def move_task(task_id: str, direction: str) -> bool:
        with queue_lock:
            queued = [i for i, task in enumerate(tasks) if task.get("status") == "queued"]
            idx = next((i for i in queued if tasks[i]["id"] == task_id), None)
            if idx is None:
                return False
            pos = queued.index(idx)
            new_pos = pos - 1 if direction == "up" else pos + 1 if direction == "down" else pos
            if not (0 <= new_pos < len(queued)):
                return False
            other_idx = queued[new_pos]
            tasks[idx], tasks[other_idx] = tasks[other_idx], tasks[idx]
            rebuild_queue_locked()
            return True

    def rebuild_queue_locked() -> None:
        # The worker reads queued tasks from tasks directly so moving/deleting tasks
        # remains deterministic even when the worker is idle.
        return None

    def queue_worker() -> None:
        while True:
            task = None
            with queue_lock:
                task = next((item for item in tasks if item.get("status") == "queued"), None)
                if task:
                    task["status"] = "running"
                    task["message"] = "Running"
                    task["updated_at"] = time.time()
            if not task:
                time.sleep(0.25)
                continue
            set_progress(active=True, percent=5, message=f"Starting {task['kind']}…", current_task_id=task["id"])
            update_task(task["id"], progress_percent=5, stage="starting")
            try:
                if task["kind"] == "generate_chunk" and task.get("chunk_id"):
                    project = dep(deps, "load_project")(task.get("project_id"))
                    chunk = next((c for c in project["chunks"] if c["id"] == task["chunk_id"]), None)
                    if not chunk:
                        raise RuntimeError("Chunk not found")
                    dep(deps, "set_status")(project, f"Queued generation running: chunk {chunk.get('order', 0) + 1}", True)
                    set_progress(active=True, percent=20, message="Loading/generating XTTS chunk…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=20, message="Loading/generating XTTS chunk…", stage="generating")
                    before_versions = {v.get("id") for v in chunk.get("versions", [])}
                    dep(deps, "generate_tts_chunk")(project, chunk)
                    new_version = next((v for v in chunk.get("versions", []) if v.get("id") not in before_versions), None)
                    dep(deps, "save_project")(project)
                    dep(deps, "set_status")(project, f"Generated chunk {chunk.get('order', 0) + 1}")
                    update_task(
                        task["id"],
                        result_chunk_id=chunk.get("id"),
                        result_version_id=(new_version or {}).get("id", chunk.get("selected_version_id", "")),
                        result_kind="chunk_version",
                    )
                elif task["kind"] == "export":
                    project = dep(deps, "load_project")(task.get("project_id"))
                    payload_data = task.get("payload") or task.get("params") or {}
                    export_request_type = dep(deps, "ExportRequest")
                    payload = export_request_type(**payload_data) if isinstance(payload_data, dict) and payload_data else export_request_type()
                    export_label = "video with audio" if str(payload.export_type).startswith("video") else f"audio {payload.audio_format.upper()}"
                    set_progress(active=True, percent=40, message=f"Exporting {export_label}…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=40, message=f"Exporting {export_label}…", stage="exporting")
                    result = dep(deps, "export_project_with_settings")(project, payload)
                    project = dep(deps, "load_project")(task.get("project_id"))
                    dep(deps, "set_status")(project, f"Export complete: {result.get('path')}")
                    update_task(task["id"], result_kind="export", result_path=result.get("path", ""), stage="saved")
                elif task["kind"] == "grok_groups":
                    project = dep(deps, "load_project")(task.get("project_id"))
                    payload_data = task.get("payload") or task.get("params") or {}
                    payload = dep(deps, "VideoGroupsAiRequest")(**payload_data)
                    dep(deps, "set_status")(project, "Grok AI grouping running", True)
                    set_progress(active=True, percent=10, message="Preparing Grok AI grouping…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=10, message="Preparing Grok AI grouping…", stage="preparing")

                    def grok_progress(stage_message: str, percent: float) -> None:
                        set_progress(active=True, percent=percent, message=stage_message, current_task_id=task["id"])
                        update_task(task["id"], progress_percent=percent, message=stage_message, stage=stage_message)

                    groups = dep(deps, "generate_video_groups_ai")(project, payload, progress_callback=grok_progress)
                    grok_progress("Saving Grok AI groups…", 95)
                    video = project.setdefault("arrangement", {}).setdefault("video", {})
                    video["groups"] = groups
                    dep(deps, "normalize_arrangement")(project)
                    dep(deps, "set_status")(project, f"Video groups saved: {len(groups)} group(s)")
                    update_task(task["id"], result_kind="video_groups", result_group_count=len(groups), stage="saved")
                elif task["kind"] == "image_group":
                    project = dep(deps, "load_project")(task.get("project_id"))
                    payload_data = task.get("payload") or task.get("params") or {}
                    group_id = str(payload_data.get("group_id") or "")
                    group = dep(deps, "find_video_group")(project, group_id)
                    if not group:
                        raise RuntimeError("Video group not found")
                    dep(deps, "set_status")(project, f"Image generation running: {group.get('title') or group_id}", True)
                    running_meta = dep(deps, "normalize_group_image_meta")(group.get("image") if isinstance(group.get("image"), dict) else {})
                    running_meta.update({"status": "running", "updated_at": time.time()})
                    dep(deps, "update_video_group_image")(project, group_id, running_meta)
                    dep(deps, "save_project")(project)
                    set_progress(active=True, percent=25, message="Formatting image prompt…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=25, message="Formatting image prompt…", stage="prompt")
                    settings = dep(deps, "image_settings")(project)
                    prompt_bundle = dep(deps, "format_image_prompt")(group, settings)
                    set_progress(active=True, percent=55, message="Generating image artifact…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=55, message="Generating image artifact…", stage="generating")
                    image_meta = dep(deps, "generate_group_image")(project, group, settings, prompt_bundle)
                    image_meta["status"] = "ready"
                    dep(deps, "update_video_group_image")(project, group_id, image_meta)
                    dep(deps, "normalize_arrangement")(project)
                    dep(deps, "save_project")(project)
                    dep(deps, "set_status")(project, f"Image ready: {group.get('title') or group_id}")
                    update_task(task["id"], result_kind="image_group", result_group_id=group_id, result_image_path=image_meta.get("path", ""), stage="saved")
                elif task["kind"] == "chunk_image":
                    project = dep(deps, "load_project")(task.get("project_id"))
                    payload_data = task.get("payload") or task.get("params") or {}
                    group_id = str(payload_data.get("group_id") or "")
                    chunk_id = str(payload_data.get("chunk_id") or "")
                    replace = bool(payload_data.get("replace"))
                    bulk_auto_place = bool(payload_data.get("bulk_auto_place"))
                    auto_sequence_id = str(payload_data.get("auto_sequence_id") or "")
                    group = dep(deps, "find_video_group")(project, group_id)
                    if not group:
                        raise RuntimeError("Video group not found")
                    dep(deps, "set_status")(project, f"Генерация картинки чанка: {chunk_id}", True)
                    set_progress(active=True, percent=35, message="Готовим промт картинки чанка…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=35, message="Готовим промт картинки чанка…", stage="prompt")
                    set_progress(active=True, percent=65, message="Генерируем картинку чанка…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=65, message="Генерируем картинку чанка…", stage="generating")
                    media_item = dep(deps, "generate_chunk_image_now")(project, group_id, chunk_id, replace=replace, bulk_auto_place=bulk_auto_place, auto_sequence_id=auto_sequence_id, sequence_index=int(payload_data.get("sequence_index") or 1), sequence_count=int(payload_data.get("sequence_count") or 1))
                    dep(deps, "normalize_arrangement")(project)
                    dep(deps, "save_project")(project)
                    dep(deps, "set_status")(project, f"Картинка чанка готова: {chunk_id}")
                    update_task(task["id"], result_kind="chunk_image", result_group_id=group_id, result_chunk_id=chunk_id, result_image_path=media_item.get("path", ""), stage="saved")
                elif task["kind"] == "chunk_video":
                    project = dep(deps, "load_project")(task.get("project_id"))
                    payload_data = task.get("payload") or task.get("params") or {}
                    group_id = str(payload_data.get("group_id") or "")
                    chunk_id = str(payload_data.get("chunk_id") or "")
                    replace = bool(payload_data.get("replace"))
                    bulk_auto_place = bool(payload_data.get("bulk_auto_place"))
                    auto_sequence_id = str(payload_data.get("auto_sequence_id") or "")
                    group = dep(deps, "find_video_group")(project, group_id)
                    if not group:
                        raise RuntimeError("Video group not found")
                    vsettings = dep(deps, "video_i2v_settings")(project)
                    backend_label = dep(deps, "video_i2v_backend_label")(vsettings)
                    dep(deps, "set_status")(project, f"Генерация видео чанка: {chunk_id}", True)
                    set_progress(active=True, percent=35, message=f"Готовим {backend_label} видео чанка…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=35, message=f"Готовим {backend_label} видео чанка…", stage="workflow")
                    if not vsettings.get("enabled"):
                        raise RuntimeError(f"{backend_label} image-to-video is disabled in settings")
                    if vsettings.get("workflow_mode") == "disabled":
                        raise RuntimeError(f"{backend_label} workflow mode is disabled")
                    set_progress(active=True, percent=60, message=f"Генерируем {backend_label} видео чанка…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=60, message=f"Генерируем {backend_label} видео чанка…", stage="generating")
                    media_item = dep(deps, "generate_chunk_video_now")(project, group_id, chunk_id, replace=replace, bulk_auto_place=bulk_auto_place, auto_sequence_id=auto_sequence_id, source_media_id=str(payload_data.get("source_media_id") or ""))
                    dep(deps, "normalize_arrangement")(project)
                    dep(deps, "save_project")(project)
                    dep(deps, "set_status")(project, f"Видео чанка готово: {chunk_id}")
                    update_task(task["id"], result_kind="chunk_video", result_group_id=group_id, result_chunk_id=chunk_id, result_video_path=media_item.get("path", ""), stage="saved")
                elif task["kind"] == "video_group":
                    project = dep(deps, "load_project")(task.get("project_id"))
                    payload_data = task.get("payload") or task.get("params") or {}
                    group_id = str(payload_data.get("group_id") or "")
                    source_media_id = str(payload_data.get("source_media_id") or "")
                    bulk_auto_place = bool(payload_data.get("bulk_auto_place"))
                    group = dep(deps, "find_video_group")(project, group_id)
                    if not group:
                        raise RuntimeError("Video group not found")
                    settings = dep(deps, "image_settings")(project)
                    vsettings = dep(deps, "video_i2v_settings")(project)
                    backend_label = dep(deps, "video_i2v_backend_label")(vsettings)
                    dep(deps, "set_status")(project, f"{backend_label} video generation running: {group.get('title') or group_id}", True)
                    running_meta = dep(deps, "normalize_group_video_meta")(group.get("video") if isinstance(group.get("video"), dict) else {})
                    running_meta.update({"status": "running", "updated_at": time.time()})
                    dep(deps, "update_video_group_video")(project, group_id, running_meta)
                    dep(deps, "save_project")(project)
                    set_progress(active=True, percent=35, message=f"Preparing {backend_label} image-to-video workflow…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=35, message=f"Preparing {backend_label} image-to-video workflow…", stage="workflow")
                    if not vsettings.get("enabled"):
                        raise RuntimeError(f"{backend_label} image-to-video is disabled in settings")
                    if vsettings.get("workflow_mode") == "disabled":
                        raise RuntimeError(f"{backend_label} workflow mode is disabled")
                    set_progress(active=True, percent=55, message=f"Generating {backend_label} video…", current_task_id=task["id"])
                    update_task(task["id"], progress_percent=55, message=f"Generating {backend_label} video…", stage="generating")
                    output_prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", f"xtts_i2v_{dep(deps, 'safe_project_id')(str(project.get('id') or dep(deps, 'active_project_id')()))}_{group_id}").strip("_")
                    source_group, source_item = dep(deps, "group_media_source_for_video")(project, group, source_media_id)
                    video_meta = dep(deps, "run_comfyui_video_i2v_workflow")(project, source_group, settings, vsettings, output_prefix)
                    video_meta["status"] = "ready"
                    dep(deps, "update_video_group_video")(project, group_id, video_meta)
                    dep(deps, "append_or_replace_group_video_media")(project, group, video_meta, source_item, bulk_auto_place=bulk_auto_place)
                    dep(deps, "normalize_arrangement")(project)
                    dep(deps, "save_project")(project)
                    dep(deps, "set_status")(project, f"{backend_label} video ready: {group.get('title') or group_id}")
                    update_task(task["id"], result_kind="video_group", result_group_id=group_id, result_video_path=video_meta.get("path", ""), stage="saved")
                update_task(task["id"], status="done", message="Done", progress_percent=100, stage="done")
                set_progress(active=False, percent=100, message="Done", current_task_id=None)
            except Exception as exc:
                update_task(task["id"], status="failed", message=str(exc), stage="failed")
                set_progress(active=False, percent=0, message=f"Failed: {exc}", current_task_id=None)
                try:
                    project = dep(deps, "load_project")(task.get("project_id"))
                    if task.get("kind") == "video_group":
                        payload_data = task.get("payload") or task.get("params") or {}
                        group_id = str(payload_data.get("group_id") or "")
                        group = dep(deps, "find_video_group")(project, group_id) if group_id else None
                        if group:
                            settings = dep(deps, "image_settings")(project)
                            vsettings = dep(deps, "video_i2v_settings")(project)
                            output_prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", f"xtts_i2v_{dep(deps, 'safe_project_id')(str(project.get('id') or dep(deps, 'active_project_id')()))}_{group_id}").strip("_")
                            fallback_output = dep(deps, "comfyui_newest_video_by_prefix")(settings, output_prefix, 0.0)
                            if fallback_output and fallback_output.exists():
                                video_meta = dep(deps, "copy_comfyui_prefix_video_to_project")(project, settings, vsettings, group, output_prefix, fallback_output, "")
                                video_meta["status"] = "ready"
                                dep(deps, "update_video_group_video")(project, group_id, video_meta)
                                dep(deps, "normalize_arrangement")(project)
                                dep(deps, "save_project")(project)
                                update_task(
                                    task["id"],
                                    status="done",
                                    message="Recovered completed SVD/SVD-XT output after failure",
                                    result_kind="video_group",
                                    result_group_id=group_id,
                                    result_video_path=video_meta.get("path", ""),
                                    progress_percent=100,
                                    stage="recovered",
                                )
                                set_progress(active=False, percent=100, message="Recovered completed SVD/SVD-XT output", current_task_id=None)
                                dep(deps, "set_status")(project, f"SVD/SVD-XT video recovered: {group.get('title') or group_id}")
                                continue
                            failed_meta = dep(deps, "normalize_group_video_meta")(group.get("video") if isinstance(group.get("video"), dict) else {})
                            failed_meta.update({"status": "failed", "error": str(exc), "updated_at": time.time()})
                            dep(deps, "update_video_group_video")(project, group_id, failed_meta)
                            dep(deps, "save_project")(project)
                    dep(deps, "set_status")(project, f"Task failed: {exc}")
                except Exception:
                    pass
            finally:
                pass

    return {
        "_queue_lock": queue_lock,
        "_task_queue": task_queue,
        "_tasks": tasks,
        "progress_snapshot": progress_snapshot,
        "queue_snapshot": queue_snapshot,
        "set_progress": set_progress,
        "ensure_worker": ensure_worker,
        "enqueue_task": enqueue_task,
        "active_task_by_kind_project": active_task_by_kind_project,
        "update_task": update_task,
        "remove_task": remove_task,
        "clear_completed_tasks": clear_completed_tasks,
        "move_task": move_task,
        "rebuild_queue_locked": rebuild_queue_locked,
        "queue_worker": queue_worker,
    }
