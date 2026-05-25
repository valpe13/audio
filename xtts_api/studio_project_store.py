import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException

try:
    from .project_compat import extract_legacy_chunks
    from .studio_storage import (
        chunk_order_ids,
        normalize_loaded_chunk_legacy_version,
        normalize_loaded_chunk_selected_version,
        normalize_loaded_project_basics,
        normalize_project_metadata,
        prepare_active_project_index_update,
        prepare_loaded_projects_index,
        prepare_project_save_index_update,
        prepare_projects_index,
        project_metadata_from_project,
        validate_project_id,
    )
    from .studio_audio_helpers import (
        legacy_music_path_track_item,
        legacy_music_track_lane_defaults,
        music_lane_item,
        music_lanes_track_projection,
        music_source_item,
        music_track_clip_projection,
        normalize_music_clip,
        normalize_music_lane_clips,
        normalize_music_lane_defaults,
        normalize_music_lanes_order,
        normalize_music_mode,
        normalize_volume_envelope_points,
    )
    from .studio_prompt_helpers import truncate_text
    from .studio_text import repair_project_mojibake_fields
except ImportError:  # pragma: no cover - direct script imports
    from project_compat import extract_legacy_chunks
    from studio_storage import (
        chunk_order_ids,
        normalize_loaded_chunk_legacy_version,
        normalize_loaded_chunk_selected_version,
        normalize_loaded_project_basics,
        normalize_project_metadata,
        prepare_active_project_index_update,
        prepare_loaded_projects_index,
        prepare_project_save_index_update,
        prepare_projects_index,
        project_metadata_from_project,
        validate_project_id,
    )
    from studio_audio_helpers import (
        legacy_music_path_track_item,
        legacy_music_track_lane_defaults,
        music_lane_item,
        music_lanes_track_projection,
        music_source_item,
        music_track_clip_projection,
        normalize_music_clip,
        normalize_music_lane_clips,
        normalize_music_lane_defaults,
        normalize_music_lanes_order,
        normalize_music_mode,
        normalize_volume_envelope_points,
    )
    from studio_prompt_helpers import truncate_text
    from studio_text import repair_project_mojibake_fields


def default_project(default_settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "default",
        "name": "XTTS Studio Project",
        "full_text": "",
        "settings": default_settings.copy(),
        "chunks": [],
        "export": None,
        "status": {"busy": False, "message": "Ready", "updated_at": time.time()},
    }


def safe_project_id(value: str) -> str:
    try:
        return validate_project_id(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id")


def slugify_project_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", (name or "project").lower()).strip("-_")
    return (slug or "project")[:48]


def project_dir(projects_root: Path, project_id: str) -> Path:
    pid = safe_project_id(project_id)
    path = (projects_root / pid).resolve()
    root = projects_root.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project path")
    return path


def project_path(projects_root: Path, project_id: str) -> Path:
    return project_dir(projects_root, project_id) / "project.json"


def project_secrets_path(projects_root: Path, project_id: str) -> Path:
    return project_dir(projects_root, project_id) / "project.secrets.json"


def load_project_secrets(projects_root: Path, project_id: str) -> dict[str, Any]:
    path = project_secrets_path(projects_root, project_id)
    if not path.exists():
        return {}
    try:
        data = load_json_file(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_project_secrets(projects_root: Path, project_id: str, data: dict[str, Any]) -> None:
    clean = {str(key): value for key, value in (data or {}).items() if value not in (None, "")}
    path = project_secrets_path(projects_root, project_id)
    if clean:
        atomic_write_json(path, clean)
    elif path.exists():
        path.unlink()


def resolve_xai_api_key(projects_root: Path, project: dict[str, Any], project_id: str) -> str:
    secrets = load_project_secrets(projects_root, project_id)
    project_key = str(secrets.get("xai_api_key") or "").strip()
    if project_key:
        return project_key
    return os.environ.get("XAI_API_KEY", "").strip()


def mask_secret(value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    if len(clean) <= 8:
        return f"{clean[:2]}…{clean[-2:]}"
    return f"{clean[:4]}…{clean[-4:]}"


def xai_api_key_hint(projects_root: Path, project_id: str) -> str:
    project_key = str(load_project_secrets(projects_root, project_id).get("xai_api_key") or "").strip()
    if project_key:
        return f"Project key configured ({mask_secret(project_key)})"
    env_key = os.environ.get("XAI_API_KEY", "").strip()
    if env_key:
        return f"Using XAI_API_KEY from environment ({mask_secret(env_key)})"
    return "Not configured"


def apply_safe_secret_settings(projects_root: Path, project: dict[str, Any], project_id: str) -> None:
    settings = project.setdefault("settings", {})
    settings.pop("xai_api_key", None)
    configured = bool(resolve_xai_api_key(projects_root, project, project_id))
    settings["xai_api_key_configured"] = configured
    settings["xai_api_key_hint"] = xai_api_key_hint(projects_root, project_id)


def project_outputs_dir(projects_root: Path, project_id: str) -> Path:
    return project_dir(projects_root, project_id) / "outputs"


def project_chunks_dir(projects_root: Path, project_id: str) -> Path:
    return project_outputs_dir(projects_root, project_id) / "chunks"


def project_images_dir(projects_root: Path, project_id: str) -> Path:
    return project_outputs_dir(projects_root, project_id) / "images"


def project_videos_dir(projects_root: Path, project_id: str) -> Path:
    return project_outputs_dir(projects_root, project_id) / "videos"


def project_exports_dir(projects_root: Path, project_id: str) -> Path:
    return project_outputs_dir(projects_root, project_id) / "export"


def project_uploads_dir(projects_root: Path, project_id: str) -> Path:
    return project_dir(projects_root, project_id) / "uploads"


def ensure_project_dirs(projects_root: Path, project_id: str) -> None:
    project_dir(projects_root, project_id).mkdir(parents=True, exist_ok=True)
    project_outputs_dir(projects_root, project_id).mkdir(parents=True, exist_ok=True)
    project_chunks_dir(projects_root, project_id).mkdir(parents=True, exist_ok=True)
    project_images_dir(projects_root, project_id).mkdir(parents=True, exist_ok=True)
    project_exports_dir(projects_root, project_id).mkdir(parents=True, exist_ok=True)
    project_uploads_dir(projects_root, project_id).mkdir(parents=True, exist_ok=True)


def index_default() -> dict[str, Any]:
    return {"projects": [], "last_active_project_id": ""}


def is_windows_file_lock_error(exc: BaseException) -> bool:
    if not isinstance(exc, OSError):
        return False
    winerror = getattr(exc, "winerror", None)
    if winerror in {5, 32, 33}:
        return True
    return isinstance(exc, PermissionError) or getattr(exc, "errno", None) in {5, 13, 32, 33}


def cleanup_stale_atomic_temps(path: Path, *, keep: Path | None = None, min_age_seconds: float = 900.0) -> None:
    cutoff = time.time() - max(0.0, min_age_seconds)
    try:
        candidates = list(path.parent.glob(f"{path.stem}.*.tmp"))
    except OSError:
        return
    keep_resolved = keep.resolve() if keep else None
    for candidate in candidates:
        try:
            if keep_resolved and candidate.resolve() == keep_resolved:
                continue
            if not candidate.is_file() or candidate.suffix != ".tmp" or candidate.parent.resolve() != path.parent.resolve():
                continue
            if candidate.stat().st_mtime > cutoff:
                continue
            candidate.unlink()
        except OSError:
            continue


def atomic_replace_with_retry(tmp: Path, path: Path, *, attempts: int = 8, base_delay: float = 0.08) -> None:
    last_exc: OSError | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            os.replace(tmp, path)
            return
        except OSError as exc:
            if not is_windows_file_lock_error(exc):
                raise
            last_exc = exc
            cleanup_stale_atomic_temps(path, keep=tmp)
            if attempt >= attempts:
                break
            time.sleep(base_delay * attempt)
    recovery_path = path.with_name(f"{path.stem}.{time.strftime('%Y%m%d-%H%M%S')}.failed-save.json")
    try:
        shutil.copy2(tmp, recovery_path)
    except OSError:
        recovery_path = tmp
    raise RuntimeError(
        "Could not replace project JSON after several retries because Windows denied access, likely due to OneDrive sync, "
        "an editor, antivirus, or indexer temporarily locking the file. The existing project.json was left unchanged. "
        f"A recovery copy of the new data was saved at {recovery_path}. Close programs viewing the project file, pause OneDrive sync for this folder, then retry."
    ) from last_exc


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + f".{uuid.uuid4().hex[:8]}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        atomic_replace_with_retry(tmp, path)
        cleanup_stale_atomic_temps(path, keep=None)
    except Exception:
        if tmp.exists():
            cleanup_stale_atomic_temps(path, keep=tmp)
        raise


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_projects_index(projects_index_path: Path, index: dict[str, Any]) -> None:
    atomic_write_json(projects_index_path, prepare_projects_index(index))


def load_projects_index(
    *,
    projects_index_path: Path,
    default_project_path: Path,
    projects_root: Path,
    default_settings: dict[str, Any],
) -> dict[str, Any]:
    ensure_dirs(
        projects_dir=projects_index_path.parent,
        projects_root=projects_root,
        default_output_dir=projects_root.parent / "outputs",
        uploads_dir=projects_root.parent / "uploads",
        default_project_path=default_project_path,
        projects_index_path=projects_index_path,
        default_settings=default_settings,
        migrate=False,
    )
    if not projects_index_path.exists():
        migrate_legacy_project(
            default_project_path=default_project_path,
            projects_root=projects_root,
            projects_index_path=projects_index_path,
            default_settings=default_settings,
        )
    index = load_json_file(projects_index_path)
    projects = [normalize_project_metadata(item) for item in (index.get("projects") or []) if isinstance(item, dict)]
    existing = [item for item in projects if project_path(projects_root, item["id"]).exists()]
    if not existing:
        project = default_project(default_settings)
        create_project_storage(projects_root, "default", project)
        existing = [project_metadata_from_project(project, "default")]
    normalized = prepare_loaded_projects_index(existing, str(index.get("last_active_project_id") or existing[0]["id"]))
    save_projects_index(projects_index_path, normalized)
    return normalized


def create_project_storage(projects_root: Path, project_id: str, project: dict[str, Any]) -> None:
    pid = safe_project_id(project_id)
    ensure_project_dirs(projects_root, pid)
    project["id"] = pid
    project.setdefault("name", pid)
    project.setdefault("created_at", time.time())
    project["updated_at"] = time.time()
    atomic_write_json(project_path(projects_root, pid), project)


def migrate_legacy_project(
    *,
    default_project_path: Path,
    projects_root: Path,
    projects_index_path: Path,
    default_settings: dict[str, Any],
) -> None:
    projects_root.mkdir(parents=True, exist_ok=True)
    legacy_project = default_project(default_settings)
    if default_project_path.exists():
        try:
            legacy_project = load_json_file(default_project_path)
        except Exception:
            legacy_project = default_project(default_settings)
    legacy_project["id"] = safe_project_id(str(legacy_project.get("id") or "default"))
    pid = legacy_project["id"]
    if not project_path(projects_root, pid).exists():
        create_project_storage(projects_root, pid, legacy_project)
    save_projects_index(projects_index_path, {"projects": [project_metadata_from_project(legacy_project, pid)], "last_active_project_id": pid})


def ensure_dirs(
    *,
    projects_dir: Path,
    projects_root: Path,
    default_output_dir: Path,
    uploads_dir: Path,
    default_project_path: Path,
    projects_index_path: Path,
    default_settings: dict[str, Any],
    migrate: bool = True,
) -> None:
    projects_dir.mkdir(parents=True, exist_ok=True)
    projects_root.mkdir(parents=True, exist_ok=True)
    default_output_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    if not default_project_path.exists():
        atomic_write_json(default_project_path, default_project(default_settings))
    if migrate and not projects_index_path.exists():
        migrate_legacy_project(
            default_project_path=default_project_path,
            projects_root=projects_root,
            projects_index_path=projects_index_path,
            default_settings=default_settings,
        )


def active_project_id(
    *,
    projects_index_path: Path,
    default_project_path: Path,
    projects_root: Path,
    default_settings: dict[str, Any],
) -> str:
    return load_projects_index(
        projects_index_path=projects_index_path,
        default_project_path=default_project_path,
        projects_root=projects_root,
        default_settings=default_settings,
    )["last_active_project_id"]


def set_active_project(
    project_id: str,
    *,
    projects_index_path: Path,
    default_project_path: Path,
    projects_root: Path,
    default_settings: dict[str, Any],
) -> None:
    pid = safe_project_id(project_id)
    index = load_projects_index(
        projects_index_path=projects_index_path,
        default_project_path=default_project_path,
        projects_root=projects_root,
        default_settings=default_settings,
    )
    if pid not in {item["id"] for item in index.get("projects", [])}:
        raise HTTPException(status_code=404, detail="Project not found")
    save_projects_index(projects_index_path, prepare_active_project_index_update(index, pid))


def load_project(
    *,
    project_id: str | None,
    projects_dir: Path,
    projects_root: Path,
    default_output_dir: Path,
    uploads_dir: Path,
    default_project_path: Path,
    projects_index_path: Path,
    default_settings: dict[str, Any],
    normalize_arrangement: Any,
    normalize_chunk_versions: Any,
    normalize_chunk_pauses: Any,
    save_project: Any,
) -> dict[str, Any]:
    ensure_dirs(
        projects_dir=projects_dir,
        projects_root=projects_root,
        default_output_dir=default_output_dir,
        uploads_dir=uploads_dir,
        default_project_path=default_project_path,
        projects_index_path=projects_index_path,
        default_settings=default_settings,
    )
    pid = safe_project_id(project_id or active_project_id(
        projects_index_path=projects_index_path,
        default_project_path=default_project_path,
        projects_root=projects_root,
        default_settings=default_settings,
    ))
    path = project_path(projects_root, pid)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    project = load_json_file(path)
    repaired_mojibake_fields = repair_project_mojibake_fields(project)
    normalize_loaded_project_basics(project, pid, default_settings)
    project.setdefault("created_at", time.time())
    project.setdefault("updated_at", time.time())
    project["chunks"] = extract_legacy_chunks(project)
    normalize_arrangement(project)
    project.setdefault("status", {"busy": False, "message": "Ready", "updated_at": time.time()})
    for chunk in project.get("chunks", []):
        normalize_loaded_chunk_legacy_version(chunk)
        normalize_chunk_versions(chunk)
        normalize_chunk_pauses(project, chunk)
    if repaired_mojibake_fields:
        project.setdefault("status", {})["message"] = f"Repaired text encoding in {repaired_mojibake_fields} field(s)"
        project.setdefault("status", {})["updated_at"] = time.time()
        save_project(project, pid)
    return project


def normalize_project_arrangement(
    project: dict[str, Any],
    *,
    default_settings: dict[str, Any],
    normalize_video_groups: Any,
    ordered_project_chunks: Any,
    migrate_ungrouped_chunks_to_video_groups: Any,
    normalize_speed_envelope_points: Any,
) -> None:
    arrangement = project.setdefault("arrangement", {})
    video = arrangement.setdefault("video", {})
    video["groups"] = normalize_video_groups(video.get("groups") if isinstance(video.get("groups"), list) else [], ordered_project_chunks(project))
    migrate_ungrouped_chunks_to_video_groups(project)
    video["speed_envelope"] = normalize_speed_envelope_points(video.get("speed_envelope"))
    voice = arrangement.setdefault("voice", {})
    voice_base = float(project.get("settings", {}).get("voice_volume", default_settings["voice_volume"]))
    # Voice automation is a multiplier over the existing global voice volume.
    voice["volume_envelope"] = normalize_volume_envelope_points(voice.get("volume_envelope") or [{"time": 0.0, "volume": 1.0}], min(2.0, max(0.0, voice_base)))
    music = arrangement.setdefault("music", {})
    music["mode"] = normalize_music_mode(music.get("mode"))
    base_volume = float(project.get("settings", {}).get("music_volume", default_settings["music_volume"]))
    music["volume_envelope"] = normalize_volume_envelope_points(music.get("volume_envelope"), base_volume)
    legacy_path = project.get("settings", {}).get("music_path", "")
    raw_sources = music.get("sources") if isinstance(music.get("sources"), list) else []
    sources: list[dict[str, Any]] = []
    by_path: dict[str, str] = {}
    for idx, source in enumerate(raw_sources):
        if not isinstance(source, dict):
            continue
        path = str(source.get("path") or "").strip()
        if not path:
            continue
        source_id = str(source.get("id") or uuid.uuid4().hex[:10])
        sources.append(music_source_item(source, source_id, path, idx))
        by_path[path] = source_id
    has_explicit_lanes = isinstance(music.get("lanes"), list)
    if legacy_path and not has_explicit_lanes and legacy_path not in by_path:
        source_id = uuid.uuid4().hex[:10]
        sources.append(music_source_item({"label": "Music"}, source_id, legacy_path, len(sources)))
        by_path[legacy_path] = source_id
    raw_tracks = music.get("tracks") if isinstance(music.get("tracks"), list) else []
    tracks: list[dict[str, Any]] = []
    for idx, track in enumerate(raw_tracks):
        if not isinstance(track, dict):
            continue
        source_id = str(track.get("source_id") or "").strip()
        path = str(track.get("path") or "").strip()
        if source_id and not path:
            path = next((source.get("path", "") for source in sources if source.get("id") == source_id), "")
        if not path:
            continue
        if path not in by_path:
            source_id = source_id or uuid.uuid4().hex[:10]
            sources.append(music_source_item(track, source_id, path, len(sources)))
            by_path[path] = source_id
        source_id = source_id or by_path[path]
        clip = normalize_music_clip(track, idx)
        tracks.append(music_track_clip_projection(track, clip, source_id, path, idx))
    if legacy_path and not has_explicit_lanes:
        if tracks:
            tracks[0]["path"] = tracks[0].get("path") or legacy_path
            tracks[0]["source_id"] = tracks[0].get("source_id") or by_path.get(legacy_path, "")
            tracks[0].setdefault("label", Path(legacy_path).name)
        else:
            tracks = [legacy_music_path_track_item(legacy_path, by_path.get(legacy_path, ""))]
    raw_lanes = music.get("lanes") if isinstance(music.get("lanes"), list) else None
    lanes: list[dict[str, Any]] = []

    if raw_lanes is not None:
        for idx, lane in enumerate(raw_lanes):
            if not isinstance(lane, dict):
                continue
            source_id = str(lane.get("source_id") or "").strip()
            path = str(lane.get("path") or "").strip()
            if source_id and not path:
                path = next((source.get("path", "") for source in sources if source.get("id") == source_id), "")
            if not path:
                continue
            if path not in by_path:
                source_id = source_id or uuid.uuid4().hex[:10]
                sources.append(music_source_item({"label": lane.get("label")}, source_id, path, len(sources)))
                by_path[path] = source_id
            source_id = source_id or by_path[path]
            lane_defaults = normalize_music_lane_defaults(lane, idx)
            clips = normalize_music_lane_clips(lane)
            lanes.append(music_lane_item(lane, source_id, path, idx, lane_defaults, clips))
    elif tracks:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for idx, track in enumerate(tracks):
            key = (str(track.get("source_id") or ""), str(track.get("path") or ""))
            lane = grouped.get(key)
            if lane is None:
                lane = legacy_music_track_lane_defaults(track, key, len(grouped), loop=music.get("mode") == "loop" and not grouped)
                grouped[key] = lane
            lane["clips"].append(normalize_music_clip(track, idx))
        lanes = sorted(grouped.values(), key=lambda item: item.get("order", 0))
    lanes = normalize_music_lanes_order(lanes)
    music["sources"] = sources
    music["lanes"] = lanes
    music["tracks"] = music_lanes_track_projection(lanes)


def migrate_ungrouped_chunks_to_video_groups(project: dict[str, Any], create_video_group_dict: Any, renumber_video_groups: Any) -> None:
    chunks = project.get("chunks", [])
    valid_ids = chunk_order_ids(chunks)
    groups = project.setdefault("arrangement", {}).setdefault("video", {}).setdefault("groups", [])
    used = {chunk_id for group in groups if isinstance(group, dict) for chunk_id in group.get("chunk_ids", []) if chunk_id in valid_ids}
    missing = [chunk_id for chunk_id in valid_ids if chunk_id not in used]
    if not missing:
        return
    title = f"Manual group {len(groups) + 1}"
    summary = truncate_text(" ".join(str(chunk.get("text") or "") for chunk in chunks if str(chunk.get("id") or "") in missing), 260)
    groups.append(create_video_group_dict(title, summary, missing, order=len(groups), source="auto-repair"))
    project["arrangement"]["video"]["groups"] = renumber_video_groups(groups)


def make_project_store_bindings(ctx: dict[str, Any]) -> dict[str, Any]:
    projects_root = ctx["PROJECTS_ROOT"]
    projects_dir = ctx["PROJECTS_DIR"]
    default_output_dir = ctx["DEFAULT_OUTPUT_DIR"]
    uploads_dir = ctx["UPLOADS_DIR"]
    default_project_path = ctx["DEFAULT_PROJECT_PATH"]
    projects_index_path = ctx["PROJECTS_INDEX_PATH"]
    default_settings = ctx["DEFAULT_SETTINGS"]
    project_save_lock = ctx["PROJECT_SAVE_LOCK"]

    bindings: dict[str, Any] = {}
    bindings["default_project"] = lambda: default_project(default_settings)
    bindings["safe_project_id"] = safe_project_id
    bindings["slugify_project_name"] = slugify_project_name
    bindings["project_dir"] = lambda project_id: project_dir(projects_root, project_id)
    bindings["project_path"] = lambda project_id: project_path(projects_root, project_id)
    bindings["project_secrets_path"] = lambda project_id: project_secrets_path(projects_root, project_id)
    bindings["load_project_secrets"] = lambda project_id: load_project_secrets(projects_root, project_id)
    bindings["save_project_secrets"] = lambda project_id, data: save_project_secrets(projects_root, project_id, data)
    bindings["resolve_xai_api_key"] = lambda project, project_id: resolve_xai_api_key(projects_root, project, project_id)
    bindings["xai_api_key_hint"] = lambda project_id: xai_api_key_hint(projects_root, project_id)
    bindings["apply_safe_secret_settings"] = lambda project, project_id: apply_safe_secret_settings(projects_root, project, project_id)
    bindings["project_outputs_dir"] = lambda project_id: project_outputs_dir(projects_root, project_id)
    bindings["project_chunks_dir"] = lambda project_id: project_chunks_dir(projects_root, project_id)
    bindings["project_images_dir"] = lambda project_id: project_images_dir(projects_root, project_id)
    bindings["project_videos_dir"] = lambda project_id: project_videos_dir(projects_root, project_id)
    bindings["project_exports_dir"] = lambda project_id: project_exports_dir(projects_root, project_id)
    bindings["project_uploads_dir"] = lambda project_id: project_uploads_dir(projects_root, project_id)
    bindings["ensure_project_dirs"] = lambda project_id: ensure_project_dirs(projects_root, project_id)
    bindings["save_projects_index"] = lambda index: save_projects_index(projects_index_path, index)
    bindings["load_projects_index"] = lambda: load_projects_index(projects_index_path=projects_index_path, default_project_path=default_project_path, projects_root=projects_root, default_settings=default_settings)
    bindings["create_project_storage"] = lambda project_id, project: create_project_storage(projects_root, project_id, project)
    bindings["ensure_dirs"] = lambda *, migrate=True: ensure_dirs(projects_dir=projects_dir, projects_root=projects_root, default_output_dir=default_output_dir, uploads_dir=uploads_dir, default_project_path=default_project_path, projects_index_path=projects_index_path, default_settings=default_settings, migrate=migrate)
    bindings["active_project_id"] = lambda: active_project_id(projects_index_path=projects_index_path, default_project_path=default_project_path, projects_root=projects_root, default_settings=default_settings)
    bindings["set_active_project"] = lambda project_id: set_active_project(project_id, projects_index_path=projects_index_path, default_project_path=default_project_path, projects_root=projects_root, default_settings=default_settings)
    bindings["save_project"] = lambda project, project_id=None: save_project(project, project_id, project_save_lock=project_save_lock, projects_root=projects_root, projects_index_path=projects_index_path, default_project_path=default_project_path, default_settings=default_settings)
    bindings["load_project"] = lambda project_id=None: load_project(project_id=project_id, projects_dir=projects_dir, projects_root=projects_root, default_output_dir=default_output_dir, uploads_dir=uploads_dir, default_project_path=default_project_path, projects_index_path=projects_index_path, default_settings=default_settings, normalize_arrangement=ctx["normalize_arrangement"], normalize_chunk_versions=ctx["normalize_chunk_versions"], normalize_chunk_pauses=ctx["normalize_chunk_pauses"], save_project=bindings["save_project"])
    bindings["migrate_ungrouped_chunks_to_video_groups"] = lambda project: migrate_ungrouped_chunks_to_video_groups(project, ctx["create_video_group_dict"](), ctx["renumber_video_groups"]())
    bindings["set_status"] = lambda project, message, busy=False: set_status(project, message, busy, bindings["save_project"])
    return bindings


def save_project(
    project: dict[str, Any],
    project_id: str | None,
    *,
    project_save_lock: Any,
    projects_root: Path,
    projects_index_path: Path,
    default_project_path: Path,
    default_settings: dict[str, Any],
) -> None:
    with project_save_lock:
        pid = safe_project_id(project_id or str(project.get("id") or active_project_id(
            projects_index_path=projects_index_path,
            default_project_path=default_project_path,
            projects_root=projects_root,
            default_settings=default_settings,
        )))
        project["id"] = pid
        project["updated_at"] = time.time()
        project.setdefault("settings", {}).pop("xai_api_key", None)
        ensure_project_dirs(projects_root, pid)
        atomic_write_json(project_path(projects_root, pid), project)
        index = load_projects_index(
            projects_index_path=projects_index_path,
            default_project_path=default_project_path,
            projects_root=projects_root,
            default_settings=default_settings,
        )
        index = prepare_project_save_index_update(index, project, pid)
        save_projects_index(projects_index_path, index)


def set_status(project: dict[str, Any], message: str, busy: bool, save_project_func: Any) -> None:
    project["status"] = {"busy": busy, "message": message, "updated_at": time.time()}
    save_project_func(project)
