import inspect
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import librosa
import numpy as np
import soundfile as sf


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


def generate_silero_chunk(
    project: dict[str, Any],
    chunk: dict[str, Any],
    *,
    default_settings: dict[str, Any],
    project_chunks_dir: Callable[[str], Path],
    active_project_id: Callable[[], str],
    normalize_chunk_versions: Callable[[dict[str, Any]], None],
    tts_input_text: Callable[[dict[str, Any], str], str],
    chunk_tts_source_text: Callable[[dict[str, Any]], str],
    http_json_request: Callable[..., Any],
    wav_stats: Callable[[Path], dict[str, Any]],
    rel_path: Callable[[Path], str],
    clean_text: Callable[[str], str],
) -> dict[str, Any]:
    settings = project["settings"]
    out_dir = project_chunks_dir(project.get("id") or active_project_id())
    out_dir.mkdir(parents=True, exist_ok=True)
    versions = chunk.setdefault("versions", [])
    normalize_chunk_versions(chunk)
    next_index = max([int(v.get("index") or 0) for v in versions] + [0]) + 1
    version_id = uuid.uuid4().hex[:10]
    out = out_dir / f"chunk_{chunk['id']}_v{next_index:03d}_{version_id}_silero.wav"
    text_for_tts = tts_input_text(project, chunk_tts_source_text(chunk))
    base_url = str(settings.get("silero_api_url") or default_settings["silero_api_url"]).strip().rstrip("/")
    if not base_url:
        raise RuntimeError("Silero API URL is empty")
    payload = {
        "text": text_for_tts,
        "speaker": str(settings.get("silero_speaker") or default_settings["silero_speaker"]),
        "sample_rate": int(settings.get("silero_sample_rate") or default_settings["silero_sample_rate"]),
        "output_path": str(out),
        "return_file": False,
        "realism_enabled": bool(settings.get("silero_realism_enabled", default_settings["silero_realism_enabled"])),
        "preset": str(settings.get("silero_realism_preset") or default_settings["silero_realism_preset"]),
        "seed": int(settings.get("seed", default_settings["seed"])),
        "speed": settings.get("speed", default_settings["speed"]),
    }
    http_json_request(f"{base_url}/v1/tts", method="POST", payload=payload, timeout=600.0)
    if not out.exists():
        raise RuntimeError(f"Silero API completed but output file was not created: {out}")
    y, sr = sf.read(out, dtype="float32", always_2d=False)
    y = soften_and_normalize(y, sr)
    sf.write(out, y, sr, subtype="PCM_16")
    stats = wav_stats(out)
    version = {
        "id": version_id,
        "label": f"Silero {next_index}",
        "index": next_index,
        "audio_path": rel_path(out),
        "created_at": time.time(),
        "text": clean_text(chunk.get("text", "")),
        "tts_text": text_for_tts,
        "settings": {
            "tts_backend": "silero",
            "silero_api_url": base_url,
            "silero_speaker": payload["speaker"],
            "silero_sample_rate": payload["sample_rate"],
            "silero_realism_enabled": payload["realism_enabled"],
            "silero_realism_preset": payload["preset"],
            "stress_mark_style": "plus",
            "text": clean_text(chunk.get("text", "")),
            "tts_text": text_for_tts,
        },
        "duration_sec": stats["duration_sec"],
    }
    versions.append(version)
    chunk["selected_version_id"] = version_id
    chunk.pop("audio_selection_stale", None)
    chunk["audio_path"] = rel_path(out)
    chunk["generated_at"] = time.time()
    chunk["duration_sec"] = stats["duration_sec"]
    return chunk


def generate_xtts_chunk(
    project: dict[str, Any],
    chunk: dict[str, Any],
    *,
    default_settings: dict[str, Any],
    project_chunks_dir: Callable[[str], Path],
    active_project_id: Callable[[], str],
    normalize_chunk_versions: Callable[[dict[str, Any]], None],
    tts_input_text: Callable[[dict[str, Any], str], str],
    chunk_tts_source_text: Callable[[dict[str, Any]], str],
    get_tts_model: Callable[[], Any],
    tts_lock: Any,
    resolve_user_path: Callable[..., Path | None],
    wav_stats: Callable[[Path], dict[str, Any]],
    rel_path: Callable[[Path], str],
    clean_text: Callable[[str], str],
) -> dict[str, Any]:
    settings = project["settings"]
    ref = resolve_user_path(settings.get("reference_path"), must_exist=True)
    out_dir = project_chunks_dir(project.get("id") or active_project_id())
    out_dir.mkdir(parents=True, exist_ok=True)
    versions = chunk.setdefault("versions", [])
    normalize_chunk_versions(chunk)
    next_index = max([int(v.get("index") or 0) for v in versions] + [0]) + 1
    version_id = uuid.uuid4().hex[:10]
    out = out_dir / f"chunk_{chunk['id']}_v{next_index:03d}_{version_id}.wav"
    text_for_tts = tts_input_text(project, chunk_tts_source_text(chunk))
    kwargs = {
        "text": text_for_tts,
        "speaker_wav": str(ref),
        "language": "ru",
        "file_path": str(out),
        "temperature": settings.get("temperature", default_settings["temperature"]),
        "top_p": settings.get("top_p", default_settings["top_p"]),
        "top_k": settings.get("top_k", default_settings["top_k"]),
        "repetition_penalty": settings.get("repetition_penalty", default_settings["repetition_penalty"]),
        "length_penalty": settings.get("length_penalty", default_settings["length_penalty"]),
        "speed": settings.get("speed", default_settings["speed"]),
    }
    with tts_lock:
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
        "text": clean_text(chunk.get("text", "")),
        "tts_text": text_for_tts,
        "settings": {
            "reference_path": settings.get("reference_path", default_settings["reference_path"]),
            "temperature": settings.get("temperature", default_settings["temperature"]),
            "top_p": settings.get("top_p", default_settings["top_p"]),
            "top_k": settings.get("top_k", default_settings["top_k"]),
            "repetition_penalty": settings.get("repetition_penalty", default_settings["repetition_penalty"]),
            "length_penalty": settings.get("length_penalty", default_settings["length_penalty"]),
            "speed": settings.get("speed", default_settings["speed"]),
            "seed": settings.get("seed", default_settings["seed"]),
            "tts_backend": "xtts",
            "text": clean_text(chunk.get("text", "")),
            "tts_text": text_for_tts,
        },
        "duration_sec": stats["duration_sec"],
    }
    versions.append(version)
    chunk["selected_version_id"] = version_id
    chunk.pop("audio_selection_stale", None)
    chunk["audio_path"] = rel_path(out)
    chunk["generated_at"] = time.time()
    chunk["duration_sec"] = stats["duration_sec"]
    return chunk


def make_tts_generation_helpers(deps: dict[str, Any]) -> dict[str, Any]:
    tts_lock = threading.Lock()
    state: dict[str, Any] = {"tts_model": None}

    def use_cuda_for_xtts() -> bool:
        requested = os.environ.get("XTTS_DEVICE", os.environ.get("XTTS_TTS_DEVICE", "auto")).strip().lower()
        if requested in {"cpu", "false", "0", "no", "off"}:
            return False
        if requested in {"cuda", "gpu", "true", "1", "yes", "on"}:
            return True
        try:
            import torch

            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def get_tts_model():
        if state["tts_model"] is None:
            from TTS.api import TTS

            state["tts_model"] = TTS(deps["MODEL_NAME"], progress_bar=True, gpu=use_cuda_for_xtts())
        return state["tts_model"]

    def is_tts_model_loaded() -> bool:
        return state["tts_model"] is not None

    def generate_silero_chunk_for_project(project: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
        return generate_silero_chunk(
            project,
            chunk,
            default_settings=deps["DEFAULT_SETTINGS"],
            project_chunks_dir=deps["project_chunks_dir"],
            active_project_id=deps["active_project_id"],
            normalize_chunk_versions=deps["normalize_chunk_versions"],
            tts_input_text=deps["tts_input_text"],
            chunk_tts_source_text=deps["chunk_tts_source_text"],
            http_json_request=deps["http_json_request"],
            wav_stats=deps["wav_stats"],
            rel_path=deps["rel_path"],
            clean_text=deps["clean_text"],
        )

    def generate_xtts_chunk_for_project(project: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
        return generate_xtts_chunk(
            project,
            chunk,
            default_settings=deps["DEFAULT_SETTINGS"],
            project_chunks_dir=deps["project_chunks_dir"],
            active_project_id=deps["active_project_id"],
            normalize_chunk_versions=deps["normalize_chunk_versions"],
            tts_input_text=deps["tts_input_text"],
            chunk_tts_source_text=deps["chunk_tts_source_text"],
            get_tts_model=get_tts_model,
            tts_lock=tts_lock,
            resolve_user_path=deps["resolve_user_path"],
            wav_stats=deps["wav_stats"],
            rel_path=deps["rel_path"],
            clean_text=deps["clean_text"],
        )

    def generate_tts_chunk(project: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
        backend = deps["normalize_tts_backend"](project.get("settings", {}))
        if backend == "silero":
            return generate_silero_chunk_for_project(project, chunk)
        return generate_xtts_chunk_for_project(project, chunk)

    return {
        "generate_tts_chunk": generate_tts_chunk,
        "generate_silero_chunk": generate_silero_chunk_for_project,
        "generate_xtts_chunk": generate_xtts_chunk_for_project,
        "get_tts_model": get_tts_model,
        "is_tts_model_loaded": is_tts_model_loaded,
    }
