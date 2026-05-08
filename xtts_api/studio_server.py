import inspect
import hashlib
import json
import os
import queue
import re
import shutil
import threading
import time
import uuid
import wave
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

os.environ.setdefault("COQUI_TOS_AGREED", "1")


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "xtts_api"
STATIC_DIR = API_DIR / "studio_static"
PROJECTS_DIR = API_DIR / "studio_projects"
DEFAULT_PROJECT_PATH = PROJECTS_DIR / "default_project.json"
PROJECTS_ROOT = PROJECTS_DIR / "projects"
PROJECTS_INDEX_PATH = PROJECTS_DIR / "projects_index.json"
DEFAULT_REF = API_DIR / "reference_audio" / "natalia_shtin" / "natalia_shtin_clean_reference.wav"
DEFAULT_OUTPUT_DIR = PROJECTS_DIR / "outputs"
UPLOADS_DIR = PROJECTS_DIR / "uploads"
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
STUDIO_BUILD = "2026-05-08-cachedecode-scope-header-fix-v1"

DEFAULT_SETTINGS = {
    "reference_path": str(DEFAULT_REF.relative_to(ROOT)),
    "music_path": "",
    "voice_volume": 1.0,
    "music_volume": 0.18,
    "temperature": 0.58,
    "top_p": 0.74,
    "top_k": 30,
    "repetition_penalty": 6.5,
    "length_penalty": 1.0,
    "speed": 0.88,
    "crossfade_sec": 0.055,
    "room_tone": True,
    "room_tone_level": 0.0012,
    "seed": 4242,
}


class SplitRequest(BaseModel):
    text: str
    max_chars: int = Field(default=190, ge=60, le=320)
    split_pause_after_min: float = Field(default=0.85, ge=0.0, le=30.0)
    split_pause_after_max: float = Field(default=0.85, ge=0.0, le=30.0)


class ChunkUpdate(BaseModel):
    text: str | None = None
    pause_after: float | None = Field(default=None, ge=0.0, le=30.0)
    order: int | None = None


class SettingsUpdate(BaseModel):
    reference_path: str | None = None
    music_path: str | None = None
    voice_volume: float | None = Field(default=None, ge=0.0, le=2.0)
    music_volume: float | None = Field(default=None, ge=0.0, le=2.0)
    temperature: float | None = Field(default=None, ge=0.1, le=1.5)
    top_p: float | None = Field(default=None, ge=0.1, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=100)
    repetition_penalty: float | None = Field(default=None, ge=1.0, le=20.0)
    length_penalty: float | None = Field(default=None, ge=0.1, le=5.0)
    speed: float | None = Field(default=None, ge=0.5, le=1.5)
    crossfade_sec: float | None = Field(default=None, ge=0.0, le=0.5)
    room_tone: bool | None = None
    room_tone_level: float | None = Field(default=None, ge=0.0, le=0.02)
    seed: int | None = None


class TextValue(BaseModel):
    text: str


class QueueRequest(BaseModel):
    chunk_ids: list[str]


class VersionSelect(BaseModel):
    version_id: str


class MusicEnvelopePoint(BaseModel):
    time: float = Field(default=0.0, ge=0.0)
    volume: float = Field(default=0.18, ge=0.0, le=2.0)


class VoiceArrangementUpdate(BaseModel):
    volume_envelope: list[MusicEnvelopePoint] = Field(default_factory=list)


class MusicArrangementUpdate(BaseModel):
    mode: str = Field(default="loop")
    volume_envelope: list[MusicEnvelopePoint] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    lanes: list[dict[str, Any]] = Field(default_factory=list)
    tracks: list[dict[str, Any]] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str = Field(default="New project", min_length=1, max_length=120)
    initial_text: str = ""


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class TextImportRequest(BaseModel):
    text: str
    mode: str = Field(default="replace")


def clean_text(text: str) -> str:
    text = text.replace("ё", "ё")
    text = re.sub(r"[\u0300\u0301]", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("--", " — ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def rel_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def resolve_user_path(value: str | None, *, must_exist: bool = False) -> Path | None:
    if not value:
        return None
    raw = Path(value)
    path = raw if raw.is_absolute() else ROOT / raw
    path = path.resolve()
    if must_exist and not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {value}")
    return path


def wav_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": rel_path(path), "exists": False}
    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.getnframes()
        sr = wav_file.getframerate()
        return {
            "path": rel_path(path),
            "url": f"/api/audio?path={rel_path(path)}&v={int(path.stat().st_mtime)}",
            "exists": True,
            "channels": wav_file.getnchannels(),
            "sample_rate": sr,
            "frames": frames,
            "duration_sec": round(frames / float(sr), 3),
        }


def trim_outer_silence(y: np.ndarray, sr: int, pad_sec: float = 0.07) -> np.ndarray:
    intervals = librosa.effects.split(y, top_db=43, frame_length=2048, hop_length=512)
    if len(intervals) == 0:
        return y
    pad = int(pad_sec * sr)
    start = max(0, int(intervals[0][0]) - pad)
    end = min(len(y), int(intervals[-1][1]) + pad)
    return y[start:end]


def soften_and_normalize(y: np.ndarray, sr: int, target_peak: float = 0.78) -> np.ndarray:
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float32)
    y = trim_outer_silence(y, sr)
    fade_len = min(len(y) // 4, int(0.030 * sr))
    if fade_len > 1:
        y[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        y[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 1e-6:
        y = y * (target_peak / peak)
    return np.clip(y, -0.98, 0.98).astype(np.float32)


def room_tone(sr: int, seconds: float, seed: int, level: float) -> np.ndarray:
    n = max(0, int(seconds * sr))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, level, n).astype(np.float32)
    fade = min(n // 3, int(0.08 * sr))
    if fade > 1:
        noise[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        noise[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return noise


def append_crossfaded(parts: list[np.ndarray], new: np.ndarray, sr: int, crossfade_sec: float) -> None:
    if new.size == 0:
        return
    if not parts or crossfade_sec <= 0:
        parts.append(new.astype(np.float32))
        return
    prev = parts.pop()
    n = min(int(crossfade_sec * sr), len(prev) // 3, len(new) // 3)
    if n <= 1:
        parts.extend([prev, new.astype(np.float32)])
        return
    fade_out = np.linspace(1.0, 0.0, n, dtype=np.float32)
    fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
    parts.append(np.concatenate([prev[:-n], prev[-n:] * fade_out + new[:n] * fade_in, new[n:]]).astype(np.float32))


def split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    cleaned = re.sub(r"\r\n?", "\n", text).strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", cleaned) if p.strip()]
    sentences: list[str] = []
    for para in paragraphs or [cleaned]:
        parts = re.split(r"(?<=[.!?…。！？])\s+", para)
        sentences.extend([clean_text(p) for p in parts if clean_text(p)])

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            words = sentence.split()
            piece = ""
            for word in words:
                candidate = f"{piece} {word}".strip()
                if piece and len(candidate) > max_chars:
                    chunks.append(piece)
                    piece = word
                else:
                    piece = candidate
            if piece:
                chunks.append(piece)
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def default_project() -> dict[str, Any]:
    return {
        "id": "default",
        "name": "XTTS Studio Project",
        "full_text": "",
        "settings": DEFAULT_SETTINGS.copy(),
        "chunks": [],
        "export": None,
        "status": {"busy": False, "message": "Ready", "updated_at": time.time()},
    }


def safe_project_id(value: str) -> str:
    project_id = (value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id")
    if ".." in project_id or "/" in project_id or "\\" in project_id or Path(project_id).is_absolute():
        raise HTTPException(status_code=400, detail="Invalid project_id")
    return project_id


def slugify_project_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", (name or "project").lower()).strip("-_")
    return (slug or "project")[:48]


def project_dir(project_id: str) -> Path:
    pid = safe_project_id(project_id)
    path = (PROJECTS_ROOT / pid).resolve()
    root = PROJECTS_ROOT.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project path")
    return path


def project_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.json"


def project_outputs_dir(project_id: str) -> Path:
    return project_dir(project_id) / "outputs"


def project_chunks_dir(project_id: str) -> Path:
    return project_outputs_dir(project_id) / "chunks"


def project_uploads_dir(project_id: str) -> Path:
    return project_dir(project_id) / "uploads"


def ensure_project_dirs(project_id: str) -> None:
    project_dir(project_id).mkdir(parents=True, exist_ok=True)
    project_outputs_dir(project_id).mkdir(parents=True, exist_ok=True)
    project_chunks_dir(project_id).mkdir(parents=True, exist_ok=True)
    project_uploads_dir(project_id).mkdir(parents=True, exist_ok=True)


def index_default() -> dict[str, Any]:
    return {"projects": [], "last_active_project_id": ""}


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + f".{uuid.uuid4().hex[:8]}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def normalize_project_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    project_id = safe_project_id(str(meta.get("id") or meta.get("project_id") or "default"))
    now = time.time()
    return {
        "id": project_id,
        "name": str(meta.get("name") or project_id),
        "created_at": float(meta.get("created_at") or now),
        "updated_at": float(meta.get("updated_at") or now),
    }


def project_metadata_from_project(project: dict[str, Any], project_id: str) -> dict[str, Any]:
    now = time.time()
    return {
        "id": project_id,
        "name": str(project.get("name") or project_id),
        "created_at": float(project.get("created_at") or now),
        "updated_at": float(project.get("updated_at") or now),
    }


def save_projects_index(index: dict[str, Any]) -> None:
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
    atomic_write_json(PROJECTS_INDEX_PATH, {"projects": unique, "last_active_project_id": active})


def load_projects_index() -> dict[str, Any]:
    ensure_dirs(migrate=False)
    if not PROJECTS_INDEX_PATH.exists():
        migrate_legacy_project()
    with PROJECTS_INDEX_PATH.open("r", encoding="utf-8") as f:
        index = json.load(f)
    projects = [normalize_project_metadata(item) for item in (index.get("projects") or []) if isinstance(item, dict)]
    existing = [item for item in projects if project_path(item["id"]).exists()]
    if not existing:
        project = default_project()
        create_project_storage("default", project)
        existing = [project_metadata_from_project(project, "default")]
    active = str(index.get("last_active_project_id") or existing[0]["id"])
    if active not in {item["id"] for item in existing}:
        active = existing[0]["id"]
    normalized = {"projects": sorted(existing, key=lambda item: item.get("updated_at", 0), reverse=True), "last_active_project_id": active}
    save_projects_index(normalized)
    return normalized


def create_project_storage(project_id: str, project: dict[str, Any]) -> None:
    pid = safe_project_id(project_id)
    ensure_project_dirs(pid)
    project["id"] = pid
    project.setdefault("name", pid)
    project.setdefault("created_at", time.time())
    project["updated_at"] = time.time()
    atomic_write_json(project_path(pid), project)


def migrate_legacy_project() -> None:
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    legacy_project = default_project()
    if DEFAULT_PROJECT_PATH.exists():
        try:
            with DEFAULT_PROJECT_PATH.open("r", encoding="utf-8") as f:
                legacy_project = json.load(f)
        except Exception:
            legacy_project = default_project()
    legacy_project["id"] = safe_project_id(str(legacy_project.get("id") or "default"))
    pid = legacy_project["id"]
    if not project_path(pid).exists():
        create_project_storage(pid, legacy_project)
    save_projects_index({"projects": [project_metadata_from_project(legacy_project, pid)], "last_active_project_id": pid})


def ensure_dirs(*, migrate: bool = True) -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_PROJECT_PATH.exists():
        atomic_write_json(DEFAULT_PROJECT_PATH, default_project())
    if migrate and not PROJECTS_INDEX_PATH.exists():
        migrate_legacy_project()


def active_project_id() -> str:
    return load_projects_index()["last_active_project_id"]


def set_active_project(project_id: str) -> None:
    pid = safe_project_id(project_id)
    index = load_projects_index()
    if pid not in {item["id"] for item in index.get("projects", [])}:
        raise HTTPException(status_code=404, detail="Project not found")
    index["last_active_project_id"] = pid
    save_projects_index(index)


def load_project(project_id: str | None = None) -> dict[str, Any]:
    ensure_dirs()
    pid = safe_project_id(project_id or active_project_id())
    path = project_path(pid)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    with path.open("r", encoding="utf-8") as f:
        project = json.load(f)
    project["id"] = pid
    project.setdefault("name", pid)
    project.setdefault("created_at", time.time())
    project.setdefault("updated_at", time.time())
    project.setdefault("settings", DEFAULT_SETTINGS.copy())
    for key, value in DEFAULT_SETTINGS.items():
        project["settings"].setdefault(key, value)
    project.setdefault("chunks", [])
    normalize_arrangement(project)
    project.setdefault("status", {"busy": False, "message": "Ready", "updated_at": time.time()})
    for chunk in project.get("chunks", []):
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
        normalize_chunk_versions(chunk)
        normalize_chunk_pauses(project, chunk)
    return project


def normalize_arrangement(project: dict[str, Any]) -> None:
    arrangement = project.setdefault("arrangement", {})
    voice = arrangement.setdefault("voice", {})
    voice_base = float(project.get("settings", {}).get("voice_volume", DEFAULT_SETTINGS["voice_volume"]))
    voice_points = voice.get("volume_envelope") or [{"time": 0.0, "volume": 1.0}]
    clean_voice_points: list[dict[str, float]] = []
    for point in voice_points:
        try:
            clean_voice_points.append({
                "time": round(max(0.0, float(point.get("time", 0.0))), 3),
                "volume": round(max(0.0, min(2.0, float(point.get("volume", 1.0)))), 3),
            })
        except (AttributeError, TypeError, ValueError):
            continue
    # Voice automation is a multiplier over the existing global voice volume.
    voice["volume_envelope"] = sorted(clean_voice_points or [{"time": 0.0, "volume": min(2.0, max(0.0, voice_base))}], key=lambda p: p["time"])
    music = arrangement.setdefault("music", {})
    music["mode"] = music.get("mode") if music.get("mode") in {"loop", "once", "chain_loop"} else "loop"
    base_volume = float(project.get("settings", {}).get("music_volume", DEFAULT_SETTINGS["music_volume"]))
    points = music.get("volume_envelope") or [{"time": 0.0, "volume": base_volume}]
    clean_points: list[dict[str, float]] = []
    for point in points:
        try:
            clean_points.append({
                "time": round(max(0.0, float(point.get("time", 0.0))), 3),
                "volume": round(max(0.0, min(2.0, float(point.get("volume", base_volume)))), 3),
            })
        except (AttributeError, TypeError, ValueError):
            continue
    music["volume_envelope"] = sorted(clean_points or [{"time": 0.0, "volume": base_volume}], key=lambda p: p["time"])
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
        item = {
            "id": source_id,
            "path": path,
            "label": str(source.get("label") or Path(path).name or f"Music source {idx + 1}"),
        }
        if source.get("duration") is not None:
            try:
                item["duration"] = round(max(0.0, float(source.get("duration") or 0.0)), 3)
            except (TypeError, ValueError):
                pass
        sources.append(item)
        by_path[path] = source_id
    has_explicit_lanes = isinstance(music.get("lanes"), list)
    if legacy_path and not has_explicit_lanes and legacy_path not in by_path:
        source_id = uuid.uuid4().hex[:10]
        sources.append({"id": source_id, "path": legacy_path, "label": Path(legacy_path).name or "Music"})
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
            sources.append({"id": source_id, "path": path, "label": str(track.get("label") or Path(path).name or f"Music source {len(sources) + 1}")})
            by_path[path] = source_id
        source_id = source_id or by_path[path]
        track_id = str(track.get("id") or uuid.uuid4().hex[:10])
        try:
            start_time = max(0.0, float(track.get("start_time", track.get("offset", 0.0)) or 0.0))
        except (TypeError, ValueError):
            start_time = 0.0
        try:
            offset_sec = max(0.0, float(track.get("offset_sec", 0.0) or 0.0))
        except (TypeError, ValueError):
            offset_sec = 0.0
        try:
            volume = max(0.0, min(2.0, float(track.get("volume", 1.0) or 1.0)))
        except (TypeError, ValueError):
            volume = 1.0
        try:
            duration_sec = max(0.0, float(track.get("duration_sec", track.get("duration", 0.0)) or 0.0))
        except (TypeError, ValueError):
            duration_sec = 0.0
        tracks.append({
            "id": track_id,
            "source_id": source_id,
            "path": path,
            "label": str(track.get("label") or Path(path).name or f"Music clip {idx + 1}"),
            "start_time": round(start_time, 3),
            "offset_sec": round(offset_sec, 3),
            "duration_sec": round(duration_sec, 3),
            "volume": round(volume, 3),
        })
    if legacy_path and not has_explicit_lanes:
        if tracks:
            tracks[0]["path"] = tracks[0].get("path") or legacy_path
            tracks[0]["source_id"] = tracks[0].get("source_id") or by_path.get(legacy_path, "")
            tracks[0].setdefault("label", Path(legacy_path).name)
        else:
            tracks = [{"id": uuid.uuid4().hex[:10], "source_id": by_path.get(legacy_path, ""), "path": legacy_path, "start_time": 0.0, "offset_sec": 0.0, "volume": 1.0, "label": Path(legacy_path).name}]
    raw_lanes = music.get("lanes") if isinstance(music.get("lanes"), list) else None
    lanes: list[dict[str, Any]] = []

    def clean_clip(raw_clip: dict[str, Any], idx: int) -> dict[str, Any]:
        try:
            start_time = max(0.0, float(raw_clip.get("start_time", raw_clip.get("offset", 0.0)) or 0.0))
        except (AttributeError, TypeError, ValueError):
            start_time = 0.0
        try:
            offset_sec = max(0.0, float(raw_clip.get("offset_sec", 0.0) or 0.0))
        except (AttributeError, TypeError, ValueError):
            offset_sec = 0.0
        try:
            duration_sec = max(0.0, float(raw_clip.get("duration_sec", raw_clip.get("duration", 0.0)) or 0.0))
        except (AttributeError, TypeError, ValueError):
            duration_sec = 0.0
        try:
            volume = max(0.0, min(2.0, float(raw_clip.get("volume", 1.0) or 1.0)))
        except (AttributeError, TypeError, ValueError):
            volume = 1.0
        return {
            "id": str(raw_clip.get("id") or uuid.uuid4().hex[:10]),
            "start_time": round(start_time, 3),
            "offset_sec": round(offset_sec, 3),
            "duration_sec": round(duration_sec, 3),
            "volume": round(volume, 3),
        }

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
                sources.append({"id": source_id, "path": path, "label": str(lane.get("label") or Path(path).name or f"Music source {len(sources) + 1}")})
                by_path[path] = source_id
            source_id = source_id or by_path[path]
            try:
                volume = max(0.0, min(2.0, float(lane.get("volume", 1.0) or 1.0)))
            except (TypeError, ValueError):
                volume = 1.0
            try:
                order = int(lane.get("order", idx) or idx)
            except (TypeError, ValueError):
                order = idx
            raw_lane_points = lane.get("volume_envelope") if isinstance(lane.get("volume_envelope"), list) else []
            lane_points: list[dict[str, float]] = []
            for point in raw_lane_points:
                try:
                    lane_points.append({
                        "time": round(max(0.0, float(point.get("time", 0.0))), 3),
                        "volume": round(max(0.0, min(2.0, float(point.get("volume", 1.0)))), 3),
                    })
                except (AttributeError, TypeError, ValueError):
                    continue
            clips = [clean_clip(clip, clip_idx) for clip_idx, clip in enumerate(lane.get("clips") if isinstance(lane.get("clips"), list) else []) if isinstance(clip, dict)]
            lanes.append({
                "id": str(lane.get("id") or uuid.uuid4().hex[:10]),
                "source_id": source_id,
                "path": path,
                "label": str(lane.get("label") or Path(path).name or f"Music lane {idx + 1}"),
                "enabled": bool(lane.get("enabled", True)),
                "loop": bool(lane.get("loop", False)),
                "volume": round(volume, 3),
                "volume_envelope": sorted(lane_points or [{"time": 0.0, "volume": 1.0}], key=lambda p: p["time"]),
                "order": order,
                "clips": clips,
            })
    elif tracks:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for idx, track in enumerate(tracks):
            key = (str(track.get("source_id") or ""), str(track.get("path") or ""))
            lane = grouped.get(key)
            if lane is None:
                lane = {
                    "id": uuid.uuid4().hex[:10],
                    "source_id": key[0],
                    "path": key[1],
                    "label": str(track.get("label") or Path(key[1]).name or f"Music lane {len(grouped) + 1}"),
                    "enabled": True,
                    "loop": music.get("mode") == "loop" and not grouped,
                    "volume": 1.0,
                    "volume_envelope": [{"time": 0.0, "volume": 1.0}],
                    "order": len(grouped),
                    "clips": [],
                }
                grouped[key] = lane
            lane["clips"].append(clean_clip(track, idx))
        lanes = sorted(grouped.values(), key=lambda item: item.get("order", 0))
    lanes = sorted(lanes, key=lambda item: item.get("order", 0))
    for order, lane in enumerate(lanes):
        lane["order"] = order
    flattened_tracks: list[dict[str, Any]] = []
    for lane in lanes:
        for clip in lane.get("clips", []):
            flattened_tracks.append({
                "id": clip.get("id", uuid.uuid4().hex[:10]),
                "source_id": lane.get("source_id", ""),
                "path": lane.get("path", ""),
                "label": lane.get("label", Path(str(lane.get("path", ""))).name),
                "start_time": clip.get("start_time", 0.0),
                "offset_sec": clip.get("offset_sec", 0.0),
                "duration_sec": clip.get("duration_sec", 0.0),
                "volume": clip.get("volume", 1.0),
            })
    music["sources"] = sources
    music["lanes"] = lanes
    music["tracks"] = flattened_tracks


def envelope_values(points: list[dict[str, Any]], total_len: int, sr: int, base_volume: float) -> np.ndarray:
    if total_len <= 0:
        return np.zeros(0, dtype=np.float32)
    if not points:
        return np.full(total_len, base_volume, dtype=np.float32)
    sorted_points = sorted(points, key=lambda p: float(p.get("time", 0.0)))
    xp = np.array([max(0, int(float(p.get("time", 0.0)) * sr)) for p in sorted_points], dtype=np.int64)
    fp = np.array([max(0.0, min(2.0, float(p.get("volume", base_volume)))) for p in sorted_points], dtype=np.float32)
    if xp[0] > 0:
        xp = np.insert(xp, 0, 0)
        fp = np.insert(fp, 0, fp[0])
    if xp[-1] < total_len - 1:
        xp = np.append(xp, total_len - 1)
        fp = np.append(fp, fp[-1])
    return np.interp(np.arange(total_len), xp, fp).astype(np.float32)


def music_envelope_values(points: list[dict[str, Any]], total_len: int, sr: int, base_volume: float) -> np.ndarray:
    return envelope_values(points, total_len, sr, base_volume)


def save_project(project: dict[str, Any], project_id: str | None = None) -> None:
    pid = safe_project_id(project_id or str(project.get("id") or active_project_id()))
    project["id"] = pid
    project["updated_at"] = time.time()
    ensure_project_dirs(pid)
    atomic_write_json(project_path(pid), project)
    index = load_projects_index()
    meta = project_metadata_from_project(project, pid)
    updated = False
    for idx, item in enumerate(index.get("projects", [])):
        if item.get("id") == pid:
            index["projects"][idx] = meta
            updated = True
            break
    if not updated:
        index.setdefault("projects", []).append(meta)
    save_projects_index(index)


def set_status(project: dict[str, Any], message: str, busy: bool = False) -> None:
    project["status"] = {"busy": busy, "message": message, "updated_at": time.time()}
    save_project(project)


def clamp_pause(value: Any, fallback: float = 0.0) -> float:
    try:
        pause = float(fallback if value is None else value)
    except (TypeError, ValueError):
        pause = float(fallback)
    return round(max(0.0, min(30.0, pause)), 3)


def stable_split_pause_after(project: dict[str, Any], text: str, order: int, low: float, high: float) -> float:
    low = clamp_pause(low)
    high = clamp_pause(high)
    if high < low:
        low, high = high, low
    if abs(high - low) < 0.0005:
        return round(low, 3)
    settings = project.get("settings", {})
    seed_payload = json.dumps({
        "project_seed": settings.get("seed", DEFAULT_SETTINGS["seed"]),
        "order": order,
        "text": text,
        "field": "pause_after",
        "min": low,
        "max": high,
    }, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(seed_payload.encode("utf-8")).digest()
    unit = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
    return round(low + (high - low) * unit, 3)


def normalize_chunk_pauses(project: dict[str, Any], chunk: dict[str, Any]) -> None:
    fallback = chunk.get("pause_after_resolved", chunk.get("pause_after", 0.0))
    chunk["pause_after"] = clamp_pause(chunk.get("pause_after"), float(fallback or 0.0))
    chunk["pause_after_resolved"] = chunk["pause_after"]
    for legacy_key in ("pause_before", "pause_before_min", "pause_before_max", "pause_after_min", "pause_after_max", "pause_before_resolved"):
        chunk.pop(legacy_key, None)


def normalize_chunk_versions(chunk: dict[str, Any]) -> None:
    versions = chunk.setdefault("versions", [])
    if chunk.get("audio_path") and not versions:
        versions.append({
            "id": "legacy",
            "label": "Legacy version",
            "audio_path": chunk.get("audio_path", ""),
            "created_at": chunk.get("generated_at") or time.time(),
            "settings": {},
            "duration_sec": chunk.get("duration_sec", 0.0),
            "index": 1,
        })
    for idx, version in enumerate(versions, start=1):
        version.setdefault("id", uuid.uuid4().hex[:10])
        version.setdefault("label", f"v{idx}")
        version.setdefault("audio_path", "")
        version.setdefault("created_at", chunk.get("generated_at") or time.time())
        version.setdefault("duration_sec", 0.0)
        version.setdefault("settings", {})
        version.setdefault("index", idx)
    selected_id = chunk.get("selected_version_id")
    selected = next((v for v in versions if v.get("id") == selected_id), None)
    if versions and not selected:
        selected = versions[-1]
        chunk["selected_version_id"] = selected.get("id", "")
    elif not versions:
        chunk["selected_version_id"] = ""


def get_selected_version(chunk: dict[str, Any]) -> dict[str, Any] | None:
    normalize_chunk_versions(chunk)
    selected_id = chunk.get("selected_version_id")
    versions = chunk.get("versions", [])
    return next((v for v in versions if v.get("id") == selected_id), None)


def selected_chunk_audio_path(chunk: dict[str, Any]) -> Path | None:
    selected = get_selected_version(chunk)
    audio_value = selected.get("audio_path") if selected else chunk.get("audio_path")
    return resolve_user_path(audio_value) if audio_value else None


def sync_chunk_to_selected_version(chunk: dict[str, Any]) -> None:
    selected = get_selected_version(chunk)
    if selected:
        chunk["audio_path"] = selected.get("audio_path", "")
        chunk["duration_sec"] = selected.get("duration_sec", 0.0)
    else:
        chunk["audio_path"] = ""
        chunk["duration_sec"] = 0.0


def enrich_project(project: dict[str, Any]) -> dict[str, Any]:
    running = 0.0
    for chunk in sorted(project.get("chunks", []), key=lambda c: c.get("order", 0)):
        normalize_chunk_versions(chunk)
        normalize_chunk_pauses(project, chunk)
        chunk["start_time"] = round(running, 3)
        path = selected_chunk_audio_path(chunk)
        if path and path.exists():
            stats = wav_stats(path)
            chunk["audio_path"] = stats["path"]
            chunk["duration_sec"] = stats["duration_sec"]
            chunk["audio_url"] = stats["url"]
            running += float(stats["duration_sec"])
        else:
            chunk["duration_sec"] = 0.0
            chunk["audio_url"] = ""
        running += float(chunk.get("pause_after", 0.0))
    project["timeline_duration_sec"] = round(running, 3)
    project["queue"] = queue_snapshot(project.get("id"))
    project["progress"] = progress_snapshot()
    for chunk in project.get("chunks", []):
        for version in chunk.get("versions", []):
            path = resolve_user_path(version.get("audio_path")) if version.get("audio_path") else None
            if path and path.exists():
                stats = wav_stats(path)
                version["audio_url"] = stats["url"]
                version["duration_sec"] = stats["duration_sec"]
            else:
                version["audio_url"] = ""
    return project


def enriched_chunk_response(chunk_id: str, project_id: str | None = None) -> dict[str, Any]:
    project = enrich_project(load_project(project_id))
    chunk = next((c for c in project.get("chunks", []) if c.get("id") == chunk_id), None)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return {
        "chunk": chunk,
        "settings": project.get("settings", {}),
        "timeline_duration_sec": project.get("timeline_duration_sec", 0.0),
        "status": project.get("status", {}),
        "export": project.get("export"),
    }


_tts_lock = threading.Lock()
_tts_model = None


_queue_lock = threading.Lock()
_task_queue: queue.Queue[dict[str, Any]] = queue.Queue()
_tasks: list[dict[str, Any]] = []
_worker_started = False
_progress: dict[str, Any] = {"active": False, "percent": 0, "message": "Idle", "current_task_id": None, "updated_at": time.time()}


def progress_snapshot() -> dict[str, Any]:
    with _queue_lock:
        return dict(_progress)


def queue_snapshot(project_id: str | None = None) -> list[dict[str, Any]]:
    with _queue_lock:
        cutoff = time.time() - 3600
        pid = safe_project_id(project_id) if project_id else None
        return [dict(task) for task in _tasks if (not pid or task.get("project_id") == pid) and (task.get("status") in {"queued", "running"} or task.get("updated_at", 0) >= cutoff)]


def set_progress(*, active: bool, percent: float, message: str, current_task_id: str | None = None) -> None:
    with _queue_lock:
        _progress.update({
            "active": active,
            "percent": round(max(0.0, min(100.0, percent)), 1),
            "message": message,
            "current_task_id": current_task_id,
            "updated_at": time.time(),
        })


def ensure_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    _worker_started = True
    thread = threading.Thread(target=queue_worker, name="xtts-studio-worker", daemon=True)
    thread.start()


def enqueue_task(kind: str, chunk_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
    ensure_worker()
    pid = safe_project_id(project_id or active_project_id())
    task = {
        "id": uuid.uuid4().hex[:10],
        "kind": kind,
        "project_id": pid,
        "chunk_id": chunk_id,
        "status": "queued",
        "message": "Queued",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    with _queue_lock:
        _tasks.append(task)
        _progress.update({
            "active": True,
            "percent": max(float(_progress.get("percent") or 0), 2.0),
            "message": f"Queued {kind}",
            "current_task_id": _progress.get("current_task_id"),
            "updated_at": time.time(),
        })
    return task


def update_task(task_id: str, **updates: Any) -> None:
    with _queue_lock:
        for task in _tasks:
            if task["id"] == task_id:
                task.update(updates)
                task["updated_at"] = time.time()
                break


def remove_task(task_id: str) -> bool:
    with _queue_lock:
        for task in _tasks:
            if task["id"] == task_id and task.get("status") == "queued":
                task["status"] = "cancelled"
                task["message"] = "Cancelled"
                task["updated_at"] = time.time()
                return True
    return False


def clear_completed_tasks(project_id: str | None = None) -> int:
    finished_statuses = {"done", "failed", "cancelled", "succeeded", "success", "error"}
    pid = safe_project_id(project_id) if project_id else None
    with _queue_lock:
        before = len(_tasks)
        _tasks[:] = [task for task in _tasks if not ((not pid or task.get("project_id") == pid) and task.get("status") in finished_statuses)]
        return before - len(_tasks)


def move_task(task_id: str, direction: str) -> bool:
    with _queue_lock:
        queued = [i for i, task in enumerate(_tasks) if task.get("status") == "queued"]
        idx = next((i for i in queued if _tasks[i]["id"] == task_id), None)
        if idx is None:
            return False
        pos = queued.index(idx)
        new_pos = pos - 1 if direction == "up" else pos + 1 if direction == "down" else pos
        if not (0 <= new_pos < len(queued)):
            return False
        other_idx = queued[new_pos]
        _tasks[idx], _tasks[other_idx] = _tasks[other_idx], _tasks[idx]
        rebuild_queue_locked()
        return True


def rebuild_queue_locked() -> None:
    # The worker reads queued tasks from _tasks directly so moving/deleting tasks
    # remains deterministic even when the worker is idle.
    return None


def queue_worker() -> None:
    while True:
        with _queue_lock:
            task = next((item for item in _tasks if item.get("status") == "queued"), None)
            if task:
                task["status"] = "running"
                task["message"] = "Running"
                task["updated_at"] = time.time()
        if not task:
            time.sleep(0.25)
            continue
        set_progress(active=True, percent=5, message=f"Starting {task['kind']}…", current_task_id=task["id"])
        update_task(task["id"], progress_percent=5)
        try:
            if task["kind"] == "generate_chunk" and task.get("chunk_id"):
                project = load_project(task.get("project_id"))
                chunk = next((c for c in project["chunks"] if c["id"] == task["chunk_id"]), None)
                if not chunk:
                    raise RuntimeError("Chunk not found")
                set_status(project, f"Queued generation running: chunk {chunk.get('order', 0) + 1}", True)
                set_progress(active=True, percent=20, message="Loading/generating XTTS chunk…", current_task_id=task["id"])
                update_task(task["id"], progress_percent=20, message="Loading/generating XTTS chunk…")
                before_versions = {v.get("id") for v in chunk.get("versions", [])}
                generate_xtts_chunk(project, chunk)
                new_version = next((v for v in chunk.get("versions", []) if v.get("id") not in before_versions), None)
                save_project(project)
                set_status(project, f"Generated chunk {chunk.get('order', 0) + 1}")
                update_task(
                    task["id"],
                    result_chunk_id=chunk.get("id"),
                    result_version_id=(new_version or {}).get("id", chunk.get("selected_version_id", "")),
                    result_kind="chunk_version",
                )
            elif task["kind"] == "export":
                project = load_project(task.get("project_id"))
                set_progress(active=True, percent=40, message="Exporting final WAV…", current_task_id=task["id"])
                update_task(task["id"], progress_percent=40, message="Exporting final WAV…")
                result = export_project(project)
                project = load_project(task.get("project_id"))
                set_status(project, f"Export complete: {result.get('path')}")
            update_task(task["id"], status="done", message="Done", progress_percent=100)
            set_progress(active=False, percent=100, message="Done", current_task_id=None)
        except Exception as exc:
            update_task(task["id"], status="failed", message=str(exc))
            set_progress(active=False, percent=0, message=f"Failed: {exc}", current_task_id=None)
            try:
                project = load_project(task.get("project_id"))
                set_status(project, f"Task failed: {exc}")
            except Exception:
                pass
        finally:
            pass


def get_tts_model():
    global _tts_model
    if _tts_model is None:
        from TTS.api import TTS

        _tts_model = TTS(MODEL_NAME, progress_bar=True, gpu=True)
    return _tts_model


def generate_xtts_chunk(project: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
    settings = project["settings"]
    ref = resolve_user_path(settings.get("reference_path"), must_exist=True)
    out_dir = project_chunks_dir(project.get("id") or active_project_id())
    out_dir.mkdir(parents=True, exist_ok=True)
    versions = chunk.setdefault("versions", [])
    normalize_chunk_versions(chunk)
    next_index = max([int(v.get("index") or 0) for v in versions] + [0]) + 1
    version_id = uuid.uuid4().hex[:10]
    out = out_dir / f"chunk_{chunk['id']}_v{next_index:03d}_{version_id}.wav"
    kwargs = {
        "text": clean_text(chunk.get("text", "")),
        "speaker_wav": str(ref),
        "language": "ru",
        "file_path": str(out),
        "temperature": settings.get("temperature", DEFAULT_SETTINGS["temperature"]),
        "top_p": settings.get("top_p", DEFAULT_SETTINGS["top_p"]),
        "top_k": settings.get("top_k", DEFAULT_SETTINGS["top_k"]),
        "repetition_penalty": settings.get("repetition_penalty", DEFAULT_SETTINGS["repetition_penalty"]),
        "length_penalty": settings.get("length_penalty", DEFAULT_SETTINGS["length_penalty"]),
        "speed": settings.get("speed", DEFAULT_SETTINGS["speed"]),
    }
    with _tts_lock:
        tts = get_tts_model()
        if "split_sentences" in inspect.signature(tts.tts_to_file).parameters:
            kwargs["split_sentences"] = False
        tts.tts_to_file(**kwargs)

    y, sr = sf.read(out, dtype="float32", always_2d=False)
    y = soften_and_normalize(y, sr)
    sf.write(out, y, sr, subtype="PCM_16")
    stats = wav_stats(out)
    version = {
        "id": version_id,
        "label": f"Version {next_index}",
        "index": next_index,
        "audio_path": rel_path(out),
        "created_at": time.time(),
        "settings": {
            "reference_path": settings.get("reference_path", DEFAULT_SETTINGS["reference_path"]),
            "temperature": settings.get("temperature", DEFAULT_SETTINGS["temperature"]),
            "top_p": settings.get("top_p", DEFAULT_SETTINGS["top_p"]),
            "top_k": settings.get("top_k", DEFAULT_SETTINGS["top_k"]),
            "repetition_penalty": settings.get("repetition_penalty", DEFAULT_SETTINGS["repetition_penalty"]),
            "length_penalty": settings.get("length_penalty", DEFAULT_SETTINGS["length_penalty"]),
            "speed": settings.get("speed", DEFAULT_SETTINGS["speed"]),
            "seed": settings.get("seed", DEFAULT_SETTINGS["seed"]),
            "text": clean_text(chunk.get("text", "")),
        },
        "duration_sec": stats["duration_sec"],
    }
    versions.append(version)
    chunk["selected_version_id"] = version_id
    chunk["audio_path"] = rel_path(out)
    chunk["generated_at"] = time.time()
    chunk["duration_sec"] = stats["duration_sec"]
    return chunk


def read_audio_mono(path: Path, target_sr: int | None = None) -> tuple[np.ndarray, int]:
    y, sr = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    if target_sr and sr != target_sr:
        y = librosa.resample(y.astype(np.float32), orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    return y.astype(np.float32), sr


def mix_music_clip(music_mix: np.ndarray, music: np.ndarray, sr: int, start_sec: float, offset_sec: float, volume: float, duration_sec: float | None = None, volume_curve: np.ndarray | None = None) -> None:
    if music.size == 0 or music_mix.size == 0:
        return
    start = int(max(0.0, start_sec) * sr)
    if start >= len(music_mix):
        return
    offset = min(len(music), int(max(0.0, offset_sec) * sr))
    clip = music[offset:]
    if duration_sec is not None and duration_sec > 0:
        clip = clip[:int(duration_sec * sr)]
    if clip.size == 0:
        return
    available = len(music_mix) - start
    clip = clip[:available]
    base_volume = max(0.0, min(2.0, volume))
    if volume_curve is not None and volume_curve.size:
        curve = volume_curve[start:start + len(clip)]
        if curve.size < len(clip):
            curve = np.pad(curve, (0, len(clip) - curve.size), mode="edge")
        music_mix[start:start + len(clip)] += clip * base_volume * curve[:len(clip)]
    else:
        music_mix[start:start + len(clip)] += clip * base_volume


def clip_effective_duration(audio: np.ndarray, sr: int, clip: dict[str, Any]) -> float:
    try:
        offset_sec = max(0.0, float(clip.get("offset_sec", 0.0) or 0.0))
    except (TypeError, ValueError):
        offset_sec = 0.0
    try:
        duration_sec = max(0.0, float(clip.get("duration_sec", 0.0) or 0.0))
    except (TypeError, ValueError):
        duration_sec = 0.0
    available = max(0.0, (len(audio) / sr) - offset_sec)
    return min(duration_sec, available) if duration_sec > 0 else available


def mix_music_lane(music_mix: np.ndarray, audio: np.ndarray, sr: int, lane: dict[str, Any], final_duration_sec: float) -> None:
    clips = lane.get("clips") if isinstance(lane.get("clips"), list) else []
    if audio.size == 0 or not clips:
        return
    lane_volume = max(0.0, min(2.0, float(lane.get("volume", 1.0) or 1.0)))
    lane_curve = music_envelope_values(
        lane.get("volume_envelope", []),
        len(music_mix),
        sr,
        1.0,
    )
    prepared: list[tuple[dict[str, Any], float, float]] = []
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        start_sec = max(0.0, float(clip.get("start_time", 0.0) or 0.0))
        duration_sec = clip_effective_duration(audio, sr, clip)
        if duration_sec > 0:
            prepared.append((clip, start_sec, start_sec + duration_sec))
    if not prepared:
        return
    pattern_start = min(item[1] for item in prepared)
    pattern_end = max(item[2] for item in prepared)
    pattern_len = max(0.001, pattern_end - pattern_start)
    repeat_start = pattern_start
    while repeat_start < final_duration_sec:
        for clip, start_sec, _end_sec in prepared:
            clip_volume = max(0.0, min(2.0, float(clip.get("volume", 1.0) or 1.0)))
            duration_sec = clip_effective_duration(audio, sr, clip)
            mix_music_clip(
                music_mix,
                audio,
                sr,
                repeat_start + (start_sec - pattern_start),
                float(clip.get("offset_sec", 0.0) or 0.0),
                lane_volume * clip_volume,
                duration_sec,
                lane_curve,
            )
        if not lane.get("loop", False):
            break
        repeat_start += pattern_len


def export_project(project: dict[str, Any]) -> dict[str, Any]:
    settings = project["settings"]
    chunks = sorted(project.get("chunks", []), key=lambda c: c.get("order", 0))
    rendered: list[np.ndarray] = []
    sr: int | None = None
    seed = int(settings.get("seed", DEFAULT_SETTINGS["seed"]))
    voice_cursor = 0
    voice_multiplier = envelope_values(
        project.get("arrangement", {}).get("voice", {}).get("volume_envelope", []),
        max(1, int(max(1.0, sum(float(c.get("duration_sec", 0.0) or 0.0) + float(c.get("pause_after", 0.0) or 0.0) for c in chunks)) * 48000)),
        48000,
        1.0,
    )
    for idx, chunk in enumerate(chunks):
        normalize_chunk_versions(chunk)
        normalize_chunk_pauses(project, chunk)
        audio_path = selected_chunk_audio_path(chunk)
        if not audio_path or not audio_path.exists():
            continue
        y, this_sr = read_audio_mono(audio_path, sr)
        sr = this_sr if sr is None else sr
        after = float(chunk.get("pause_after", 0.0))
        if sr != 48000 or len(voice_multiplier) < voice_cursor + len(y):
            voice_multiplier = envelope_values(
                project.get("arrangement", {}).get("voice", {}).get("volume_envelope", []),
                max(voice_cursor + len(y) + int(after * sr), 1),
                sr,
                1.0,
            )
        # Voice automation is a multiplier over the global voice_volume setting.
        y_voice = y * float(settings.get("voice_volume", 1.0)) * voice_multiplier[voice_cursor: voice_cursor + len(y)]
        append_crossfaded(rendered, y_voice, sr, float(settings.get("crossfade_sec", 0.055)))
        voice_cursor += len(y)
        if settings.get("room_tone", True):
            tone = room_tone(sr, after, seed + idx, float(settings.get("room_tone_level", 0.0012)))
            append_crossfaded(rendered, tone, sr, float(settings.get("crossfade_sec", 0.055)))
            voice_cursor += len(tone)
        else:
            silence = np.zeros(int(after * sr), dtype=np.float32)
            append_crossfaded(rendered, silence, sr, 0.0)
            voice_cursor += len(silence)

    if not rendered or sr is None:
        raise HTTPException(status_code=400, detail="No generated chunks to export.")
    final = np.concatenate(rendered).astype(np.float32)
    normalize_arrangement(project)
    music_cfg = project.get("arrangement", {}).get("music", {})
    music_lanes = [lane for lane in (music_cfg.get("lanes") or []) if isinstance(lane, dict) and lane.get("enabled", True) and lane.get("clips")]
    if music_lanes:
        music_mix = np.zeros(len(final), dtype=np.float32)
        audio_cache: dict[str, np.ndarray] = {}

        def lane_audio(lane: dict[str, Any]) -> np.ndarray | None:
            music_path = resolve_user_path(lane.get("path")) if lane.get("path") else None
            if not music_path or not music_path.exists():
                return None
            key = str(music_path)
            if key not in audio_cache:
                audio_cache[key], _ = read_audio_mono(music_path, sr)
            return audio_cache[key]

        for lane in music_lanes:
            audio = lane_audio(lane)
            if audio is None or audio.size == 0:
                continue
            mix_music_lane(music_mix, audio, sr, lane, len(final) / sr)
        envelope = music_envelope_values(
            music_cfg.get("volume_envelope", []),
            len(final),
            sr,
            float(settings.get("music_volume", 0.18)),
        )
        music_mix = music_mix * envelope
        fade = min(len(music_mix) // 5, int(1.5 * sr))
        if fade > 1:
            music_mix[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
            music_mix[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
        final = final + music_mix
    peak = float(np.max(np.abs(final))) if final.size else 0.0
    if peak > 0.94:
        final = final * (0.94 / peak)
    final = np.clip(final, -0.98, 0.98).astype(np.float32)
    out = project_outputs_dir(project.get("id") or active_project_id()) / f"final_{int(time.time())}.wav"
    sf.write(out, final, sr, subtype="PCM_16")
    result = wav_stats(out)
    project["export"] = result
    save_project(project)
    return result


app = FastAPI(title="XTTS Studio", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:7870"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def route_availability_summary() -> dict[str, Any]:
    expected = {
        "GET /api/projects": ("GET", "/api/projects"),
        "GET /api/queue": ("GET", "/api/queue"),
        "POST /api/queue/generate": ("POST", "/api/queue/generate"),
        "POST /api/queue/export": ("POST", "/api/queue/export"),
        "GET /api/health": ("GET", "/api/health"),
    }
    registered: dict[str, list[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = sorted(getattr(route, "methods", []) or [])
        if path:
            registered[path] = methods
    return {
        name: {"available": method in registered.get(path, []), "path": path, "method": method}
        for name, (method, path) in expected.items()
    } | {"registered_api_paths": {path: methods for path, methods in registered.items() if path.startswith("/api/")}}


@app.on_event("startup")
def _startup() -> None:
    ensure_dirs()
    print(
        "XTTS Studio startup:",
        json.dumps({
            "build": STUDIO_BUILD,
            "pid": os.getpid(),
            "server_file": str(Path(__file__).resolve()),
            "queue_routes": route_availability_summary(),
        }, ensure_ascii=False),
        flush=True,
    )


@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse("/studio/")


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    icon = STATIC_DIR / "favicon.ico"
    if icon.exists():
        return FileResponse(str(icon))
    raise HTTPException(status_code=204, detail="No favicon")


@app.get("/robots.txt")
def robots() -> dict[str, str]:
    return {"User-agent": "*", "Disallow": "/"}


@app.get("/api/health")
def health() -> dict[str, Any]:
    project = load_project()
    return {
        "ok": True,
        "build": STUDIO_BUILD,
        "api_version": app.version,
        "pid": os.getpid(),
        "server_file": str(Path(__file__).resolve()),
        "module": __name__,
        "project": rel_path(project_path(project.get("id", "default"))),
        "active_project_id": project.get("id"),
        "model_loaded": _tts_model is not None,
        "status": project.get("status", {}),
        "queue_route": "/api/queue",
        "queue_routes": route_availability_summary(),
    }


def project_has_active_tasks(project_id: str) -> bool:
    pid = safe_project_id(project_id)
    with _queue_lock:
        return any(task.get("project_id") == pid and task.get("status") in {"queued", "running"} for task in _tasks)


@app.get("/api/projects")
def list_projects() -> dict[str, Any]:
    index = load_projects_index()
    return {"projects": index.get("projects", []), "last_active_project_id": index.get("last_active_project_id", "")}


@app.post("/api/projects")
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    index = load_projects_index()
    existing = {item["id"] for item in index.get("projects", [])}
    base = slugify_project_name(payload.name)
    pid = base
    counter = 2
    while pid in existing:
        suffix = f"-{counter}"
        pid = f"{base[:64 - len(suffix)]}{suffix}"
        counter += 1
    project = default_project()
    project["id"] = pid
    project["name"] = payload.name.strip() or "New project"
    project["full_text"] = payload.initial_text or ""
    project["created_at"] = time.time()
    project["updated_at"] = time.time()
    create_project_storage(pid, project)
    index.setdefault("projects", []).append(project_metadata_from_project(project, pid))
    index["last_active_project_id"] = pid
    save_projects_index(index)
    return {"project": enrich_project(load_project(pid)), "projects": load_projects_index().get("projects", []), "last_active_project_id": pid}


@app.get("/api/projects/active")
def get_active_project() -> dict[str, Any]:
    project = load_project(active_project_id())
    return {"project": enrich_project(project), "project_id": project.get("id")}


@app.post("/api/projects/active")
def post_active_project(payload: dict[str, Any]) -> dict[str, Any]:
    pid = safe_project_id(str(payload.get("project_id") or ""))
    set_active_project(pid)
    return {"project": enrich_project(load_project(pid)), "project_id": pid}


@app.get("/api/projects/{project_id}")
def open_project(project_id: str) -> dict[str, Any]:
    pid = safe_project_id(project_id)
    set_active_project(pid)
    return enrich_project(load_project(pid))


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, payload: ProjectPatch) -> dict[str, Any]:
    pid = safe_project_id(project_id)
    project = load_project(pid)
    if payload.name is not None:
        project["name"] = payload.name.strip() or project.get("name") or pid
    save_project(project, pid)
    return {"project": enrich_project(load_project(pid)), "projects": load_projects_index().get("projects", [])}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, confirm: str = Query(default="")) -> dict[str, Any]:
    pid = safe_project_id(project_id)
    if confirm != pid:
        raise HTTPException(status_code=400, detail="Deletion requires confirm query equal to project_id")
    index = load_projects_index()
    projects = index.get("projects", [])
    if len(projects) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last project")
    if project_has_active_tasks(pid):
        raise HTTPException(status_code=400, detail="Cannot delete a project with queued/running tasks")
    path = project_dir(pid)
    if path.exists():
        shutil.rmtree(path)
    remaining = [item for item in projects if item.get("id") != pid]
    active = index.get("last_active_project_id")
    if active == pid:
        active = remaining[0]["id"]
    save_projects_index({"projects": remaining, "last_active_project_id": active})
    return {"projects": load_projects_index().get("projects", []), "last_active_project_id": active}


@app.post("/api/projects/{project_id}/import-text")
def import_project_text(project_id: str, payload: TextImportRequest) -> dict[str, Any]:
    pid = safe_project_id(project_id)
    if payload.mode not in {"replace", "append"}:
        raise HTTPException(status_code=400, detail="mode must be replace or append")
    project = load_project(pid)
    incoming = payload.text or ""
    if payload.mode == "append" and project.get("full_text"):
        project["full_text"] = f"{project.get('full_text', '')}\n\n{incoming}" if incoming else project.get("full_text", "")
    else:
        project["full_text"] = incoming
    set_status(project, f"Text imported ({payload.mode})")
    return enrich_project(project)


@app.get("/api/project")
def get_project(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    return enrich_project(load_project(project_id))


@app.get("/api/chunks/{chunk_id}")
def get_chunk(chunk_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    return enriched_chunk_response(chunk_id, project_id)


@app.post("/api/project/text")
def save_full_text(payload: TextValue, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    project["full_text"] = payload.text
    set_status(project, "Text saved")
    return enrich_project(project)


@app.post("/api/project/settings")
def update_settings(payload: SettingsUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    data = payload.dict(exclude_unset=True)
    for key, value in data.items():
        if value is not None:
            project["settings"][key] = value
    normalize_arrangement(project)
    set_status(project, "Settings saved")
    return enrich_project(project)


@app.post("/api/project/arrangement/music")
def update_music_arrangement(payload: MusicArrangementUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    music = project.setdefault("arrangement", {}).setdefault("music", {})
    music["mode"] = payload.mode if payload.mode in {"loop", "once", "chain_loop"} else "loop"
    music["volume_envelope"] = [point.dict() for point in payload.volume_envelope]
    music["sources"] = payload.sources
    music["lanes"] = payload.lanes
    music["tracks"] = payload.tracks
    normalize_arrangement(project)
    set_status(project, f"Music mode saved: {music['mode']} · automation saved")
    return enrich_project(project)


@app.post("/api/project/arrangement/voice")
def update_voice_arrangement(payload: VoiceArrangementUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    voice = project.setdefault("arrangement", {}).setdefault("voice", {})
    voice["volume_envelope"] = [point.dict() for point in payload.volume_envelope]
    normalize_arrangement(project)
    set_status(project, "Voice volume automation saved")
    return enrich_project(project)


@app.post("/api/chunks/split")
def split_chunks(payload: SplitRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    chunks = []
    split_min = clamp_pause(payload.split_pause_after_min)
    split_max = clamp_pause(payload.split_pause_after_max)
    if split_max < split_min:
        split_min, split_max = split_max, split_min
    for idx, text in enumerate(split_text_into_chunks(payload.text, payload.max_chars)):
        pause_after = stable_split_pause_after(project, text, idx, split_min, split_max)
        chunks.append({
            "id": uuid.uuid4().hex[:12],
            "order": idx,
            "text": text,
            "pause_after": pause_after,
            "audio_path": "",
            "versions": [],
            "selected_version_id": "",
            "duration_sec": 0.0,
            "generated_at": None,
        })
        normalize_chunk_pauses(project, chunks[-1])
    project["full_text"] = payload.text
    project["chunks"] = chunks
    set_status(project, f"Split into {len(chunks)} chunks")
    return enrich_project(project)


@app.post("/api/chunks/{chunk_id}/select-version")
def select_chunk_version(chunk_id: str, payload: VersionSelect, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    chunk = next((c for c in project["chunks"] if c["id"] == chunk_id), None)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    version = next((v for v in chunk.get("versions", []) if v.get("id") == payload.version_id), None)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    chunk["selected_version_id"] = payload.version_id
    sync_chunk_to_selected_version(chunk)
    set_status(project, f"Selected {version.get('label', 'version')} for chunk {chunk.get('order', 0) + 1}")
    return enrich_project(project)


@app.get("/api/queue")
def get_queue(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    pid = project_id or active_project_id()
    return {"queue": queue_snapshot(pid), "progress": progress_snapshot()}


@app.post("/api/queue/clear-completed")
def clear_completed_queue_tasks(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    pid = project_id or active_project_id()
    removed = clear_completed_tasks(pid)
    return {"removed": removed, "queue": queue_snapshot(pid), "progress": progress_snapshot()}


@app.post("/api/queue/generate")
def queue_generate(payload: QueueRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    pid = project.get("id")
    valid = {c["id"] for c in project.get("chunks", [])}
    queued = []
    for chunk_id in payload.chunk_ids:
        if chunk_id in valid:
            queued.append(enqueue_task("generate_chunk", chunk_id, pid))
    set_status(project, f"Queued {len(queued)} generation task(s)", bool(queued))
    return {"queued_tasks": queued, "queue": queue_snapshot(pid), "progress": progress_snapshot(), "project": enrich_project(load_project(pid))}


@app.post("/api/queue/export")
def queue_export(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    task = enqueue_task("export", project_id=project.get("id"))
    set_status(project, "Export queued", True)
    return {"queued_task": task, "queue": queue_snapshot(project.get("id")), "progress": progress_snapshot(), "project": enrich_project(project)}


@app.delete("/api/queue/{task_id}")
def delete_queue_task(task_id: str) -> dict[str, Any]:
    if not remove_task(task_id):
        raise HTTPException(status_code=400, detail="Only queued tasks can be removed")
    return {"queue": queue_snapshot(active_project_id()), "progress": progress_snapshot()}


@app.post("/api/queue/{task_id}/move/{direction}")
def move_queue_task(task_id: str, direction: str) -> dict[str, Any]:
    if direction not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="direction must be up or down")
    if not move_task(task_id, direction):
        raise HTTPException(status_code=400, detail="Task cannot be moved")
    return {"queue": queue_snapshot(active_project_id()), "progress": progress_snapshot()}


@app.patch("/api/chunks/{chunk_id}")
def update_chunk(chunk_id: str, payload: ChunkUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    chunk = next((c for c in project["chunks"] if c["id"] == chunk_id), None)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")
    if payload.text is not None and payload.text != chunk.get("text"):
        chunk["text"] = payload.text
        chunk["audio_path"] = ""
        chunk["audio_url"] = ""
        chunk["versions"] = []
        chunk["selected_version_id"] = ""
        chunk["duration_sec"] = 0.0
    if payload.pause_after is not None:
        chunk["pause_after"] = payload.pause_after
    normalize_chunk_pauses(project, chunk)
    if payload.order is not None:
        chunk["order"] = payload.order
    project["chunks"] = sorted(project["chunks"], key=lambda c: c.get("order", 0))
    for idx, item in enumerate(project["chunks"]):
        item["order"] = idx
    set_status(project, "Chunk updated")
    return enrich_project(project)


@app.post("/api/chunks/{chunk_id}/move/{direction}")
def move_chunk(chunk_id: str, direction: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
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
    set_status(project, "Chunk order updated")
    return enrich_project(project)


@app.post("/api/chunks/{chunk_id}/generate")
def generate_chunk_endpoint(chunk_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    if not any(c["id"] == chunk_id for c in project["chunks"]):
        raise HTTPException(status_code=404, detail="Chunk not found")
    chunk = next(c for c in project["chunks"] if c["id"] == chunk_id)
    if not clean_text(chunk.get("text", "")):
        raise HTTPException(status_code=400, detail="Chunk text is empty")
    task = enqueue_task("generate_chunk", chunk_id, project.get("id"))
    set_status(project, f"Queued chunk {chunk.get('order', 0) + 1} generation")
    return enrich_project(load_project(project.get("id"))) | {"queued_task": task, "queue": queue_snapshot(project.get("id")), "progress": progress_snapshot()}


@app.post("/api/chunks/generate-all")
def generate_all_chunks(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    queued = 0
    for chunk in sorted(project["chunks"], key=lambda c: c.get("order", 0)):
        if not chunk.get("audio_path") and clean_text(chunk.get("text", "")):
            enqueue_task("generate_chunk", chunk["id"], project.get("id"))
            queued += 1
    set_status(project, f"Queued {queued} missing chunk(s)")
    return enrich_project(load_project(project.get("id"))) | {"queue": queue_snapshot(project.get("id")), "progress": progress_snapshot()}


@app.post("/api/export")
def export_endpoint(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    task = enqueue_task("export", project_id=project.get("id"))
    set_status(project, "Export queued", True)
    return {"queued_task": task, "queue": queue_snapshot(project.get("id")), "progress": progress_snapshot(), "project": enrich_project(project)}


@app.post("/api/upload/music")
def upload_music(file: UploadFile = File(...), project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    uploads_dir = project_uploads_dir(project.get("id"))
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.а-яА-ЯёЁ-]+", "_", file.filename or "music.wav")
    out = uploads_dir / f"{int(time.time())}_{safe_name}"
    with out.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    music = project.setdefault("arrangement", {}).setdefault("music", {})
    sources = music.get("sources") if isinstance(music.get("sources"), list) else []
    source = {"id": uuid.uuid4().hex[:10], "path": rel_path(out), "label": out.name}
    sources.append(source)
    music["sources"] = sources
    lanes = music.get("lanes") if isinstance(music.get("lanes"), list) else []
    lanes.append({"id": uuid.uuid4().hex[:10], "source_id": source["id"], "path": rel_path(out), "label": out.name, "enabled": True, "loop": False, "volume": 1.0, "volume_envelope": [{"time": 0.0, "volume": 1.0}], "order": len(lanes), "clips": [{"id": uuid.uuid4().hex[:10], "start_time": 0.0, "offset_sec": 0.0, "duration_sec": 0.0, "volume": 1.0}]})
    music["lanes"] = lanes
    normalize_arrangement(project)
    set_status(project, "Music uploaded")
    return {"path": rel_path(out), "project": enrich_project(project)}


@app.get("/api/audio")
def audio(path: str) -> FileResponse:
    if re.match(r"^https?://", path or "", flags=re.IGNORECASE):
        return RedirectResponse(path)
    resolved = resolve_user_path(path, must_exist=True)
    if not resolved or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(resolved), media_type="audio/wav", filename=resolved.name)


class NoStoreStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        if path in {"app.js", "style.css", "index.html", ""}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.mount("/studio", NoStoreStaticFiles(directory=str(STATIC_DIR), html=True), name="studio")

