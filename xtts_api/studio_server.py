import base64
import inspect
import hashlib
import html
import json
import logging
import math
import mimetypes
import os
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import librosa
import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from pronunciation_preprocess import load_pronunciation_dictionary, preprocess_tts_text
except ImportError:  # pragma: no cover - package-style imports
    from .pronunciation_preprocess import load_pronunciation_dictionary, preprocess_tts_text

os.environ.setdefault("COQUI_TOS_AGREED", "1")


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "xtts_api"
STATIC_DIR = API_DIR / "studio_static"
PROJECTS_DIR = API_DIR / "studio_projects"
DEFAULT_PROJECT_PATH = PROJECTS_DIR / "default_project.json"
PROJECTS_ROOT = PROJECTS_DIR / "projects"
PROJECTS_INDEX_PATH = PROJECTS_DIR / "projects_index.json"
PROJECT_SAVE_LOCK = threading.RLock()
LOGGER = logging.getLogger("xtts_studio")
DEFAULT_REF = API_DIR / "reference_audio" / "natalia_shtin" / "natalia_shtin_clean_reference.wav"
DEFAULT_OUTPUT_DIR = PROJECTS_DIR / "outputs"
UPLOADS_DIR = PROJECTS_DIR / "uploads"
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
STUDIO_BUILD = "2026-05-12-studio-cleanup-stage1-v1"
SVD_HISTORY_WAIT_TIMEOUT_SECONDS = 1800.0
XAI_IMAGINE_VIDEO_POLL_TIMEOUT_SECONDS = 900.0
XAI_IMAGINE_VIDEO_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_PRONUNCIATION_DICTIONARY = API_DIR / "pronunciation_dictionary.json"
DEFAULT_SILERO_API_URL = "http://127.0.0.1:7866"

REALVISXL_CHECKPOINT = "RealVisXL_V5.0_fp16.safetensors"
SVD_XT_CHECKPOINT = "svd_xt.safetensors"
GROK_IMAGINE_VIDEO_MODEL = "grok-imagine-video"
GROK_IMAGE_MODEL = "grok-2-image"
ANIMATEDIFF_MOTION_MODEL = "mm_sd_v15_v2.ckpt"
ANIMATEDIFF_SDXL_ENV_MODEL = "XTTS_ANIMATEDIFF_SDXL_MOTION_MODEL"
ANIMATEDIFF_SDXL_MODEL_CANDIDATES = ("hsxl_temporal_layers.safetensors", "hotshotxl.safetensors", "mm_sdxl_v10_beta.ckpt", "mm_sdxl_v10_beta.safetensors")
IMAGE_QUALITY_PRESETS = {
    "fast": {
        "vertical": {"width": 832, "height": 1216},
        "horizontal": {"width": 1216, "height": 832},
        "steps": 16,
        "cfg": 5.5,
        "sampler": "dpmpp_2m_sde",
        "scheduler": "karras",
    },
    "balanced": {
        "vertical": {"width": 896, "height": 1152},
        "horizontal": {"width": 1152, "height": 896},
        "steps": 22,
        "cfg": 6.0,
        "sampler": "dpmpp_2m_sde",
        "scheduler": "karras",
    },
    "quality": {
        "vertical": {"width": 1024, "height": 1536},
        "horizontal": {"width": 1536, "height": 1024},
        "steps": 28,
        "cfg": 6.0,
        "sampler": "dpmpp_2m_sde",
        "scheduler": "karras",
    },
}
VIDEO_I2V_QUALITY_PRESETS = {
    "fast": {
        "frames": 14,
        "fps": 6,
        "motion_bucket_id": 96,
        "augmentation_level": 0.01,
        "min_cfg": 1.0,
        "cfg": 2.0,
        "steps": 12,
        "sampler": "euler",
        "scheduler": "normal",
    },
    "balanced": {
        "frames": 25,
        "fps": 6,
        "motion_bucket_id": 104,
        "augmentation_level": 0.01,
        "min_cfg": 1.0,
        "cfg": 2.2,
        "steps": 20,
        "sampler": "euler",
        "scheduler": "normal",
    },
    "quality": {
        "frames": 49,
        "fps": 8,
        "motion_bucket_id": 140,
        "augmentation_level": 0.02,
        "min_cfg": 1.0,
        "cfg": 3.0,
        "steps": 30,
        "sampler": "euler",
        "scheduler": "normal",
    },
}
GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS = {
    "fast": "480p",
    "balanced": "720p",
    "quality": "720p",
}
GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS = {"480p", "720p"}
GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS = {"16:9", "9:16"}
VIDEO_I2V_MOTION_STYLE_PRESETS = {
    "object_locked": {
        "label": "Object motion, locked camera",
        "motion_bucket_id": 56,
        "augmentation_level": 0.0,
        "cfg": 1.8,
        "max_frames": 25,
        "max_fps": 6,
        "steps_delta": 0,
    },
    "still_life": {
        "label": "Still life",
        "motion_bucket_id": 48,
        "augmentation_level": 0.0,
        "cfg": 1.8,
        "max_frames": 25,
        "max_fps": 6,
        "steps_delta": 0,
    },
    "ambient_nature": {
        "label": "Ambient nature",
        "motion_bucket_id": 72,
        "augmentation_level": 0.005,
        "cfg": 2.0,
        "max_frames": 25,
        "max_fps": 6,
        "steps_delta": 0,
    },
    "human_subtle": {
        "label": "Human subtle",
        "motion_bucket_id": 64,
        "augmentation_level": 0.005,
        "cfg": 1.9,
        "max_frames": 25,
        "max_fps": 6,
        "steps_delta": 0,
    },
    "cinematic_slow": {
        "label": "Cinematic slow",
        "motion_bucket_id": 96,
        "augmentation_level": 0.01,
        "cfg": 2.2,
        "max_frames": 49,
        "max_fps": 8,
        "steps_delta": 2,
    },
    "landscape_long_loop": {
        "label": "Landscape long loop",
        "motion_bucket_id": 112,
        "augmentation_level": 0.02,
        "cfg": 2.1,
        "max_frames": 49,
        "max_fps": 6,
        "steps_delta": -4,
    },
}
COMMON_REALVISXL_NEGATIVE = (
    "text, watermark, logo, low quality, blurry, distorted anatomy, extra fingers, deformed hands, "
    "bad anatomy, missing fingers, bad eyes, duplicate people, cropped face, noisy, jpeg artifacts, "
    "overexposed, underexposed, oversaturated, cartoon, anime, cgi, plastic skin"
)
DEFAULT_VIDEO_GROUP_NEGATIVE = (
    "text, captions, subtitles, watermark, logo, signature, low quality, blurry, out of focus, "
    "noisy, jpeg artifacts, overexposed, underexposed, oversaturated, cartoon, anime, cgi, "
    "plastic skin, distorted anatomy, bad anatomy, deformed hands, extra fingers, missing fingers, "
    "bad eyes, duplicate people, cropped face"
)
ANCIENT_PREHISTORY_NEGATIVE = (
    "modern clothing, business suit, office suit, shirt and tie, jacket, blazer, dress pants, modern shoes, "
    "sneakers, watch, glasses, phone, earbuds, backpack, plastic, flashlight, metal camping gear, city, office, "
    "modern buildings, cars, road, power lines, modern campfire scene, tourists, safari, cosplay, fantasy armor"
)
DEFAULT_ANIMATION_POSITIVE_PROMPT = (
    "Calm seamless image-to-video loop, perfect loop, first and last frame match naturally, locked static camera and no camera movement. "
    "Animate only objects or scene elements inside the frame: gentle grass or leaves swaying, soft water ripples, "
    "faint smoke drifting, candle or fire flicker, slow cyclic clouds, floating dust motes, and light fabric movement. "
    "Keep motion subtle and continuous with no beginning or ending reveal; keep the original composition stable, peaceful, slow, realistic, and suitable for a quiet sleep documentary loop."
)
DEFAULT_ANIMATION_NEGATIVE_PROMPT = (
    "camera movement, camera pan, camera zoom, camera orbit, dolly, trucking shot, whole image moving, drifting frame, "
    "handheld camera, camera shake, tilt, fast action, cut, cuts, jump cut, scene transition, scene change, character movement, walking, running, talking, "
    "gestures, morphing, warping, new objects appearing, objects disappearing, disappearing objects, non-looping motion, one-way motion, sudden ending, start/end mismatch, object popping, text, subtitles, watermark, logo, "
    "flicker artifacts, jitter, strobe, abrupt lighting changes"
)
NO_PEOPLE_IMAGE_NEGATIVE = (
    "people, person, human, humans, face, faces, body, bodies, crowd, crowds, hands, fingers, arms, legs, "
    "characters, man, woman, child, clothing, portrait, selfie, skin, eyes, hair"
)
NO_PEOPLE_VISUAL_INSTRUCTION = (
    "No people, faces, bodies, crowds, hands, characters, portraits, clothing, or human silhouettes. "
    "Focus only on environment, landscape, objects, architecture, nature, artifacts, tools, textures, light, weather, and atmosphere. "
)


def rounded_video_dimension(value: Any, fallback: int, *, multiple: int = 8, minimum: int = 64, maximum: int = 4096) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = int(fallback)
    number = max(minimum, min(maximum, number))
    return max(multiple, int(round(number / multiple)) * multiple)


def svd_source_dimensions(settings: dict[str, Any], image_meta: dict[str, Any] | None = None) -> tuple[int, int]:
    image_meta = image_meta if isinstance(image_meta, dict) else {}
    default_width = int(settings.get("width") or 1024)
    default_height = int(settings.get("height") or 576)
    width = rounded_video_dimension(image_meta.get("width"), default_width)
    height = rounded_video_dimension(image_meta.get("height"), default_height)
    aspect_ratio = str(image_meta.get("aspect_ratio") or settings.get("aspect_ratio") or "").lower()
    if aspect_ratio == "vertical" and width > height:
        width, height = height, width
    elif aspect_ratio == "horizontal" and height > width:
        width, height = height, width
    return width, height


def source_image_aspect_ratio(settings: dict[str, Any], image_meta: dict[str, Any] | None = None, *, mode: str = "auto") -> str:
    requested = str(mode or "auto").strip().lower()
    if requested in GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS:
        return requested
    width, height = svd_source_dimensions(settings, image_meta)
    if height > width:
        return "9:16"
    return "16:9"


def format_grok_imagine_video_prompt(group: dict[str, Any]) -> str:
    base = truncate_text(
        group.get("grok_video_prompt") or group.get("animation_positive_prompt") or group.get("visual_prompt") or group.get("summary") or group.get("title"),
        1200,
    )
    if not base:
        base = DEFAULT_ANIMATION_POSITIVE_PROMPT
    return truncate_text(
        f"{base}. Locked static camera, stable composition, preserve the source image scene and framing. "
        "Generate a seamless looping video / perfect loop: first and last frame match naturally, cyclic ambient motion, no beginning or ending reveal. "
        "Animate only subtle continuous natural object or environmental motion inside the frame: gentle cyclic leaves, grass, water, smoke, firelight, clouds, dust motes, or fabric where appropriate. "
        "For landscapes, make leaves, grass, water, and clouds move in a gentle cyclic pattern. "
        "No cuts, no jump cut, no scene transition, no zoom, no pan, no camera shake, no sudden camera movement, no new objects appearing, no objects disappearing, no object popping, no text, no start/end mismatch, calm realistic sleep-documentary motion.",
        1800,
    )


def image_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    if mime not in {"image/png", "image/jpeg", "image/webp"}:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def xai_json_request(base_url: str, endpoint: str, api_key: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 60.0) -> Any:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{base_url.rstrip('/')}{endpoint}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:700]
        raise RuntimeError(f"xAI Imagine Video request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"xAI Imagine Video request failed: {exc.reason}") from exc
    return json.loads(response_body) if response_body else {}


def download_http_file(url: str, out_path: Path, *, timeout: float = 180.0) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "XTTS-Studio/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    if not data:
        raise RuntimeError("Downloaded xAI video URL returned an empty body")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
IMAGE_STYLE_PRESETS = {
    "sleep_documentary": {
        "positive_prefix": "calm documentary realism, soft natural light, realistic scene",
        "positive_suffix": "quiet atmosphere, natural skin texture, realistic materials, sleep documentary mood",
        "negative": "harsh contrast, action scene, neon colors",
    },
    "cinematic_realism": {
        "positive_prefix": "cinematic realistic scene, dramatic but calm lighting, high detail",
        "positive_suffix": "film still, realistic depth of field, detailed environment, restrained color grading",
        "negative": "overdramatic pose, extreme action, fake CGI, plastic skin",
    },
    "ancient_history": {
        "positive_prefix": "historical reconstruction, ancient or prehistoric people in era-appropriate natural-material clothing, realistic archaeology documentary",
        "positive_suffix": "visible handmade textiles or animal-hide garments as appropriate, stone, clay, wood, historically plausible clothing, museum-quality realism",
        "negative": f"modern clothing, modern buildings, fantasy armor, anachronistic objects, {ANCIENT_PREHISTORY_NEGATIVE}",
    },
    "soft_painting": {
        "positive_prefix": "soft painterly realism, gentle colors, realistic but slightly painted look",
        "positive_suffix": "subtle brush texture, soft edges, warm muted palette, peaceful composition",
        "negative": "hard outlines, comic style, anime, flat colors, oversharpened",
    },
    "night_firelight": {
        "positive_prefix": "warm firelight, night camp, calm atmosphere, realistic low light",
        "positive_suffix": "glowing embers, soft shadows, warm torch light, peaceful night scene, natural darkness",
        "negative": "daylight, cold fluorescent light, overexposed fire, horror atmosphere",
    },
}

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
    "image_provider": "comfyui",
    "image_model": "realvisxl",
    "image_grok_model": GROK_IMAGE_MODEL,
    "image_quality_preset": "balanced",
    "image_aspect_ratio": "vertical",
    "image_width": 896,
    "image_height": 1152,
    "image_style_preset": "sleep_documentary",
    "image_comfyui_url": "http://127.0.0.1:8188",
    "image_comfyui_path": "ComfyUI_windows_portable",
    "image_comfyui_python": "",
    "image_comfyui_launch_cmd": "",
    "image_comfyui_autostart": True,
    "image_workflow_mode": "generated",
    "image_workflow_path": "",
    "image_model_checkpoint": REALVISXL_CHECKPOINT,
    "image_negative_preset": "default",
    "image_exclude_people": False,
    "image_seed": 0,
    "image_steps": 22,
    "image_cfg": 6.0,
    "image_sampler": "dpmpp_2m_sde",
    "image_scheduler": "karras",
    "video_i2v_enabled": False,
    "video_i2v_quality_preset": "balanced",
    "video_i2v_motion_style": "ambient_nature",
    "video_i2v_workflow_mode": "generated_svd",
    "video_i2v_model_checkpoint": SVD_XT_CHECKPOINT,
    "video_i2v_grok_model": GROK_IMAGINE_VIDEO_MODEL,
    "video_i2v_grok_duration_sec": 5,
    "video_i2v_grok_resolution": "480p",
    "video_i2v_grok_aspect_ratio_mode": "auto",
    "video_i2v_grok_loop_postprocess": "pingpong",
    "video_i2v_grok_crossfade_sec": 0.5,
    "video_i2v_frames": 25,
    "video_i2v_fps": 6,
    "video_i2v_motion_bucket_id": 127,
    "video_i2v_augmentation_level": 0.02,
    "video_i2v_min_cfg": 1.0,
    "video_i2v_cfg": 2.5,
    "video_i2v_steps": 20,
    "video_i2v_sampler": "euler",
    "video_i2v_scheduler": "normal",
    "video_i2v_pingpong": True,
    "video_i2v_target_duration_sec": 20.0,
    "video_i2v_preview_playback_rate": 1.0,
    "tts_pronunciation_preprocess_enabled": True,
    "tts_pronunciation_dictionary_path": str(DEFAULT_PRONUNCIATION_DICTIONARY.relative_to(ROOT)),
    "tts_stress_mark_style": "acute",
    "tts_backend": "xtts",
    "silero_api_url": DEFAULT_SILERO_API_URL,
    "silero_speaker": "baya",
    "silero_sample_rate": 48000,
    "silero_realism_enabled": True,
    "silero_realism_preset": "sleep_safe",
    "ai_add_russian_stress_marks": False,
    "ai_stress_model": "",
    "ai_stress_batch_chunks": 2,
    "ai_stress_max_request_chars": 2500,
    "ai_stress_retries": 2,
}


class SplitRequest(BaseModel):
    text: str
    max_chars: int = Field(default=190, ge=60, le=320)
    split_pause_after_min: float = Field(default=0.18, ge=0.0, le=30.0)
    split_pause_after_max: float = Field(default=0.35, ge=0.0, le=30.0)


class ChunkUpdate(BaseModel):
    text: str | None = None
    tts_text: str | None = None
    pause_after: float | None = Field(default=None, ge=0.0, le=30.0)
    order: int | None = None


class ChunkCreate(BaseModel):
    text: str = ""
    tts_text: str | None = None
    pause_after: float = Field(default=0.25, ge=0.0, le=30.0)
    insert_after_chunk_id: str | None = None
    order: int | None = None


class SettingsUpdate(BaseModel):
    reference_path: str | None = None
    music_path: str | None = None
    xai_api_key: str | None = None
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
    image_provider: str | None = None
    image_model: str | None = None
    image_grok_model: str | None = None
    image_quality_preset: str | None = None
    image_aspect_ratio: str | None = None
    image_width: int | None = Field(default=None, ge=64, le=4096)
    image_height: int | None = Field(default=None, ge=64, le=4096)
    image_style_preset: str | None = None
    image_comfyui_url: str | None = None
    image_comfyui_path: str | None = None
    image_comfyui_python: str | None = None
    image_comfyui_launch_cmd: str | None = None
    image_comfyui_autostart: bool | None = None
    image_workflow_mode: str | None = None
    image_workflow_path: str | None = None
    image_model_checkpoint: str | None = None
    image_negative_preset: str | None = None
    image_exclude_people: bool | None = None
    image_seed: int | None = None
    image_steps: int | None = Field(default=None, ge=1, le=150)
    image_cfg: float | None = Field(default=None, ge=0.0, le=30.0)
    image_sampler: str | None = None
    image_scheduler: str | None = None
    video_i2v_enabled: bool | None = None
    video_i2v_quality_preset: str | None = None
    video_i2v_motion_style: str | None = None
    video_i2v_workflow_mode: str | None = None
    video_i2v_model_checkpoint: str | None = None
    video_i2v_grok_model: str | None = None
    video_i2v_grok_duration_sec: int | None = Field(default=None, ge=1, le=30)
    video_i2v_grok_resolution: str | None = None
    video_i2v_grok_aspect_ratio_mode: str | None = None
    video_i2v_grok_loop_postprocess: str | None = None
    video_i2v_grok_crossfade_sec: float | None = Field(default=None, ge=0.1, le=2.0)
    video_i2v_frames: int | None = Field(default=None, ge=2, le=256)
    video_i2v_fps: int | None = Field(default=None, ge=1, le=60)
    video_i2v_motion_bucket_id: int | None = Field(default=None, ge=1, le=1023)
    video_i2v_augmentation_level: float | None = Field(default=None, ge=0.0, le=1.0)
    video_i2v_min_cfg: float | None = Field(default=None, ge=0.0, le=30.0)
    video_i2v_cfg: float | None = Field(default=None, ge=0.0, le=30.0)
    video_i2v_steps: int | None = Field(default=None, ge=1, le=150)
    video_i2v_sampler: str | None = None
    video_i2v_scheduler: str | None = None
    video_i2v_pingpong: bool | None = None
    video_i2v_target_duration_sec: float | None = Field(default=None, ge=2.0, le=60.0)
    video_i2v_preview_playback_rate: float | None = Field(default=None, ge=0.25, le=2.0)
    tts_pronunciation_preprocess_enabled: bool | None = None
    tts_pronunciation_dictionary_path: str | None = None
    tts_stress_mark_style: str | None = None
    tts_backend: str | None = None
    silero_api_url: str | None = None
    silero_speaker: str | None = None
    silero_sample_rate: int | None = Field(default=None, ge=8000, le=96000)
    silero_realism_enabled: bool | None = None
    silero_realism_preset: str | None = None
    ai_add_russian_stress_marks: bool | None = None
    ai_stress_model: str | None = None
    ai_stress_batch_chunks: int | None = Field(default=None, ge=1, le=12)
    ai_stress_max_request_chars: int | None = Field(default=None, ge=500, le=20000)
    ai_stress_retries: int | None = Field(default=None, ge=0, le=5)


class TextValue(BaseModel):
    text: str


class QueueRequest(BaseModel):
    chunk_ids: list[str]


class VersionSelect(BaseModel):
    version_id: str


class MusicEnvelopePoint(BaseModel):
    time: float = Field(default=0.0, ge=0.0)
    volume: float = Field(default=0.18, ge=0.0, le=2.0)


class VideoSpeedEnvelopePoint(BaseModel):
    time: float = Field(default=0.0, ge=0.0)
    speed: float = Field(default=1.0, ge=0.25, le=2.0)


class VoiceArrangementUpdate(BaseModel):
    volume_envelope: list[MusicEnvelopePoint] = Field(default_factory=list)


class MusicArrangementUpdate(BaseModel):
    mode: Optional[str] = None
    volume_envelope: Optional[list[MusicEnvelopePoint]] = None
    sources: Optional[list[dict[str, Any]]] = None
    lanes: Optional[list[dict[str, Any]]] = None
    tracks: Optional[list[dict[str, Any]]] = None


class VideoArrangementUpdate(BaseModel):
    speed_envelope: Optional[list[VideoSpeedEnvelopePoint]] = None


class VideoGroupsAiRequest(BaseModel):
    model: Optional[str] = None
    strategy: str = "auto"
    max_section_chunks: int = Field(default=40, ge=1, le=500)
    max_request_chars: int = Field(default=22000, ge=5000, le=200000)
    section_overlap_chunks: int = Field(default=0, ge=0, le=20)
    min_chunks_per_group: int = 2
    max_chunks_per_group: int = 8
    fallback_on_error: bool = False
    exclude_people_from_images: bool | None = None
    instruction: Optional[str] = None


class GroupMediaItem(BaseModel):
    id: str | None = None
    type: str = Field(default="image")
    path: str = ""
    url: str | None = None
    label: str | None = None
    role: str = Field(default="main")
    start_offset_sec: float = Field(default=0.0, ge=0.0, le=36000.0)
    duration_sec: float = Field(default=0.0, ge=0.0, le=36000.0)
    fit: str = Field(default="cover")
    volume: float | None = Field(default=None, ge=0.0, le=2.0)


class GroupUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    chunk_ids: list[str] | None = None
    visual_prompt: str | None = None
    negative_prompt: str | None = None
    animation_positive_prompt: str | None = None
    animation_negative_prompt: str | None = None
    grok_video_prompt: str | None = None
    mood: str | None = None
    scene_type: str | None = None
    video_motion_intensity: str | None = None
    video_loop_notes: str | None = None
    media_items: list[GroupMediaItem] | None = None
    media_layout: str | None = None
    default_media_duration_sec: float | None = Field(default=None, ge=0.0, le=36000.0)


class GroupCreate(BaseModel):
    title: str = ""
    summary: str = ""
    chunk_ids: list[str] = Field(default_factory=list)
    insert_after_group_id: str | None = None


class GroupMoveRequest(BaseModel):
    direction: str | None = None
    order: int | None = None


XAI_VIDEO_GROUPS_ATTEMPTS = 3
XAI_VIDEO_GROUPS_TIMEOUT_SECONDS = 120
XAI_VIDEO_GROUPS_RETRY_BASE_DELAY_SECONDS = 1.5
XAI_STRESS_ATTEMPTS = 3
XAI_STRESS_TIMEOUT_SECONDS = 90
XAI_STRESS_MAX_CHUNKS_PER_BATCH = 2
XAI_STRESS_MAX_REQUEST_CHARS = 2500
XAI_STRESS_MAX_TOKENS = 6000
XAI_STRESS_LONG_CHUNK_CHARS = 1200


def resolve_xai_text_model(project: dict[str, Any] | None = None, override: str | None = None) -> str:
    """Resolve the shared xAI chat/text model used by Grok grouping and optional text helpers."""
    explicit = str(override or "").strip()
    if explicit:
        return explicit
    env_model = str(os.environ.get("XAI_MODEL") or "").strip()
    if env_model:
        return env_model
    return "grok-3-mini"


class GroupImageRequest(BaseModel):
    force: bool = False


class GroupImagesRequest(BaseModel):
    missing_only: bool = True
    force: bool = False


class GroupVideosRequest(BaseModel):
    missing_only: bool = True
    force: bool = False


class GroupVideoRequest(BaseModel):
    force: bool = False


class ExportRequest(BaseModel):
    export_type: str = Field(default="audio")
    audio_format: str = Field(default="wav")
    audio_bitrate: str = Field(default="192k")
    sample_rate: int | None = Field(default=None, ge=8000, le=96000)
    channels: int = Field(default=1, ge=1, le=2)
    video_format: str = Field(default="mp4")
    orientation: str = Field(default="auto")
    resolution: str = Field(default="720p")
    fps: int = Field(default=30, ge=1, le=60)
    video_quality: str = Field(default="medium")
    video_fit: str = Field(default="cover")


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
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("--", " — ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tts_input_text(project: dict[str, Any], raw_text: str) -> str:
    settings = project.get("settings", {}) if isinstance(project.get("settings"), dict) else {}
    text = str(raw_text or "")
    backend = normalize_tts_backend(settings)
    if bool(settings.get("tts_pronunciation_preprocess_enabled", DEFAULT_SETTINGS["tts_pronunciation_preprocess_enabled"])):
        dictionary_path = resolve_user_path(str(settings.get("tts_pronunciation_dictionary_path") or DEFAULT_SETTINGS["tts_pronunciation_dictionary_path"]))
        dictionary = load_pronunciation_dictionary(dictionary_path) if dictionary_path else {}
        requested_style = str(settings.get("tts_stress_mark_style") or DEFAULT_SETTINGS["tts_stress_mark_style"])
        stress_style = "plus" if backend == "silero" and requested_style.strip().lower() in {"auto", "backend", ""} else requested_style
        text = preprocess_tts_text(
            text,
            dictionary,
            stress_mark_style=stress_style,
        )
    return clean_text(text)


def normalize_tts_backend(settings: dict[str, Any] | None) -> str:
    backend = str((settings or {}).get("tts_backend") or DEFAULT_SETTINGS["tts_backend"]).strip().lower()
    return backend if backend in {"xtts", "silero"} else "xtts"


def chunk_tts_source_text(chunk: dict[str, Any]) -> str:
    return str(chunk.get("tts_text") or chunk.get("stressed_text") or chunk.get("text") or "")


MOJIBAKE_SUSPICIOUS_CHARS = set("\u0402\u0403\u0405\u0406\u0408\u0409\u040a\u040b\u040c\u040e\u040f\u0452\u0453\u0455\u0456\u0458\u0459\u045a\u045b\u045c\u045e\u045f\u0490\u0491\u201a\u201e\u2020\u2021\u2026\u2030\u2039\u203a\u20ac\u2116\ufffd")
MOJIBAKE_CP1251_ENCODE_FALLBACK = {
    "\u02dc": b"\x98",
}
RUSSIAN_COMMON_WORD_RE = re.compile(
    r"\b(представьте|себе|очень|воздух|становится|прошлом|когда|которые|можно|люди|время|земли|свет|тише|были)\b",
    flags=re.IGNORECASE,
)


def mojibake_score(text: str) -> int:
    if not text:
        return 0
    suspicious = sum(1 for char in text if char in MOJIBAKE_SUSPICIOUS_CHARS)
    suspicious += len(re.findall(r"[РС][\u00a0-\u00ff\u0400-\u040f\u0450-\u045f\u0490-\u0491\u2010-\u203a\u20ac\u2116]", text))
    suspicious += len(re.findall(r"[ÐÑ][\u0080-\u00ff]", text))
    return suspicious


def readable_russian_score(text: str) -> int:
    if not text:
        return 0
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", text))
    common_words = len(RUSSIAN_COMMON_WORD_RE.findall(text))
    return cyrillic + common_words * 25 - mojibake_score(text) * 3


def encode_mojibake_cp1251(text: str) -> bytes:
    parts: list[bytes] = []
    for char in text:
        try:
            parts.append(char.encode("cp1251"))
        except UnicodeEncodeError:
            fallback = MOJIBAKE_CP1251_ENCODE_FALLBACK.get(char)
            if fallback is None:
                raise
            parts.append(fallback)
    return b"".join(parts)


def repair_mojibake_text(text: str) -> tuple[str, bool]:
    """Conservatively repair UTF-8 Cyrillic text decoded through a single-byte codepage."""
    if not isinstance(text, str) or not text:
        return text, False
    before_mojibake = mojibake_score(text)
    if before_mojibake < max(6, min(80, len(text) // 200)):
        return text, False

    before_readable = readable_russian_score(text)
    best = text
    best_codec = ""
    best_mojibake = before_mojibake
    best_readable = before_readable
    for codec in ("cp1251", "cp1252", "latin1"):
        try:
            raw = encode_mojibake_cp1251(text) if codec == "cp1251" else text.encode(codec)
            candidate = raw.decode("utf-8")
        except UnicodeError:
            continue
        candidate_mojibake = mojibake_score(candidate)
        candidate_readable = readable_russian_score(candidate)
        if candidate_mojibake < best_mojibake and candidate_readable > best_readable:
            best = candidate
            best_codec = codec
            best_mojibake = candidate_mojibake
            best_readable = candidate_readable

    if not best_codec:
        return text, False
    if best_mojibake > max(2, before_mojibake // 10):
        return text, False
    if best_readable < before_readable + max(25, before_mojibake * 2):
        return text, False
    return best, True


def repair_project_mojibake_fields(project: dict[str, Any]) -> int:
    repaired = 0
    full_text, changed = repair_mojibake_text(str(project.get("full_text") or ""))
    if changed:
        project["full_text"] = full_text
        repaired += 1
    for chunk in project.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        text, changed = repair_mojibake_text(str(chunk.get("text") or ""))
        if changed:
            chunk["text"] = text
            repaired += 1
    return repaired


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


def media_stats(path: Path, *, sample_rate: int | None = None, duration_sec: float | None = None, media_type: str = "audio") -> dict[str, Any]:
    if not path.exists():
        return {"path": rel_path(path), "exists": False, "media_type": media_type}
    suffix = path.suffix.lower().lstrip(".")
    rel = rel_path(path)
    url_path = "/api/video" if media_type == "video" else "/api/audio"
    result: dict[str, Any] = {
        "path": rel,
        "url": f"{url_path}?path={rel}&v={int(path.stat().st_mtime)}",
        "exists": True,
        "media_type": media_type,
        "format": suffix,
        "bytes": path.stat().st_size,
    }
    if sample_rate:
        result["sample_rate"] = int(sample_rate)
    if duration_sec is not None:
        result["duration_sec"] = round(float(duration_sec), 3)
    return result


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


def split_paragraph_blocks(text: str) -> list[dict[str, Any]]:
    cleaned = re.sub(r"\r\n?", "\n", text).strip()
    if not cleaned:
        return []
    pieces = re.split(r"(\n\s*\n+)", cleaned)
    blocks: list[dict[str, Any]] = []
    for idx in range(0, len(pieces), 2):
        para = pieces[idx].strip()
        if not para:
            continue
        separator = pieces[idx + 1] if idx + 1 < len(pieces) else ""
        blank_lines = separator.count("\n")
        boundary_type = "section" if blank_lines >= 3 else ("paragraph" if separator else "sentence")
        blocks.append({"text": para, "boundary_type": boundary_type})
    return blocks


def looks_like_section_heading(paragraph: str) -> bool:
    compact = re.sub(r"\s+", " ", paragraph).strip()
    if not compact or len(compact) > 90:
        return False
    if re.match(r"^(#{1,6}\s+|(?:глава|часть|раздел|section|chapter)\b|\d{1,3}[.)]\s+)", compact, flags=re.IGNORECASE):
        return True
    return not re.search(r"[.!?…。！？]$", compact) and len(compact.split()) <= 9


def split_paragraph_sentences(paragraph: str) -> list[str]:
    normalized = re.sub(r"[ \t]*\n[ \t]*", " ", paragraph).strip()
    # Python's `re` requires look-behind assertions to be fixed width.  The
    # previous splitter used `(?<=[.!?…。！？][\"'»”’)]*)`, which is variable
    # width because of `*` inside the look-behind and fails at runtime.  Match
    # the whole boundary instead and split after the matched whitespace so the
    # sentence-ending punctuation and optional closing quotes stay with the
    # preceding sentence.
    parts: list[str] = []
    start = 0
    for match in re.finditer(r"[.!?…。！？][\"'»”’)]*\s+(?=[А-ЯЁA-Z0-9\"'«“(])", normalized):
        parts.append(normalized[start:match.end()].strip())
        start = match.end()
    parts.append(normalized[start:].strip())
    return [clean_text(part) for part in parts if clean_text(part)]


def split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    clause_parts = [part.strip() for part in re.split(r"(?<=[,;:—-])\s+", sentence) if part.strip()]
    current = ""
    for part in clause_parts:
        candidate = f"{current} {part}".strip()
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = part
        else:
            current = candidate
    if current:
        pieces.append(current)

    final: list[str] = []
    for piece in pieces or [sentence]:
        if len(piece) <= max_chars:
            final.append(piece)
            continue
        words = piece.split()
        word_piece = ""
        for word in words:
            candidate = f"{word_piece} {word}".strip()
            if word_piece and len(candidate) > max_chars:
                final.append(word_piece)
                word_piece = word
            else:
                word_piece = candidate
        if word_piece:
            final.append(word_piece)
    return [clean_text(piece) for piece in final if clean_text(piece)]


def split_text_into_chunks(text: str, max_chars: int) -> list[dict[str, Any]]:
    blocks = split_paragraph_blocks(text)
    units: list[dict[str, str]] = []
    for idx, block in enumerate(blocks):
        para = block["text"]
        boundary_type = str(block.get("boundary_type") or "sentence")
        if idx + 1 < len(blocks) and looks_like_section_heading(para):
            boundary_type = "section"
        sentences = split_paragraph_sentences(para)
        for sent_idx, sentence in enumerate(sentences):
            units.append({
                "text": sentence,
                "boundary_type": boundary_type if sent_idx == len(sentences) - 1 else "sentence",
            })

    chunks: list[dict[str, Any]] = []
    current = ""
    current_boundary = "sentence"

    def emit_current() -> None:
        nonlocal current, current_boundary
        if current:
            chunks.append({"text": current, "boundary_type": current_boundary})
            current = ""
            current_boundary = "sentence"

    for unit in units:
        sentence = unit["text"]
        boundary_type = unit["boundary_type"]
        if len(sentence) > max_chars:
            emit_current()
            long_pieces = split_long_sentence(sentence, max_chars)
            for piece_idx, piece in enumerate(long_pieces):
                piece_boundary = boundary_type if piece_idx == len(long_pieces) - 1 else "sentence"
                chunks.append({"text": piece, "boundary_type": piece_boundary})
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            emit_current()
            current = sentence
            current_boundary = boundary_type
        else:
            current = candidate
            current_boundary = boundary_type
    emit_current()
    return chunks


def truncate_text(value: Any, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def looks_like_ancient_prehistory_scene(*values: Any) -> bool:
    text = " ".join(str(value or "") for value in values).lower()
    if not text:
        return False
    return bool(re.search(
        r"\b(prehistoric|prehistory|stone age|paleolithic|palaeolithic|mesolithic|neolithic|hominid|hominin|early human|"
        r"caveman|cave people|animal hide|animal-hide|fur cloak|hide wrap|bronze age|iron age|"
        r"ancient villager|ancient village|hunter-gatherer|hunter gatherer)\b",
        text,
        flags=re.IGNORECASE,
    ))


def append_unique_csv_terms(base: str, extra: str, *, limit: int = 1500) -> str:
    seen: set[str] = set()
    terms: list[str] = []
    for source in (base, extra):
        for raw_term in str(source or "").split(","):
            term = re.sub(r"\s+", " ", raw_term).strip()
            if not term:
                continue
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(term)
    return truncate_text(", ".join(terms), limit)


def ordered_project_chunks(project: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted([chunk for chunk in project.get("chunks", []) if isinstance(chunk, dict)], key=lambda c: c.get("order", 0))


def chunk_order_ids(chunks: list[dict[str, Any]]) -> list[str]:
    return [str(chunk.get("id") or "") for chunk in chunks if str(chunk.get("id") or "")]


def fallback_video_groups(chunks: list[dict[str, Any]], max_chunks_per_group: int = 4, *, exclude_people: bool = False) -> list[dict[str, Any]]:
    ordered_ids = chunk_order_ids(chunks)
    group_size = max(1, int(max_chunks_per_group or 4))
    groups: list[dict[str, Any]] = []
    for start in range(0, len(ordered_ids), group_size):
        ids = ordered_ids[start:start + group_size]
        number = len(groups) + 1
        texts = [truncate_text(chunk.get("text", ""), 140) for chunk in chunks[start:start + group_size]]
        summary = truncate_text(" ".join(texts), 260)
        ancient_prehistory = looks_like_ancient_prehistory_scene(summary)
        scene_lead = "A calm realistic documentary scene inspired by the narration: "
        material_rule = ""
        if ancient_prehistory and not exclude_people:
            scene_lead = "A calm realistic archaeology documentary scene inspired by the narration: "
            material_rule = (
                "Show era-specific humans, not generic figures: prehistoric humans, early hominids, or ancient villagers as appropriate. "
                "Make clothing visibly handmade from natural materials: rough animal-hide wraps, fur cloaks, barefoot bodies, or simple linen tunics only when era-appropriate. "
                "No modern objects visible; no tailored clothing visible. "
            )
        if exclude_people:
            visual_prompt = truncate_text(
                scene_lead +
                f"{summary}. {NO_PEOPLE_VISUAL_INSTRUCTION}Show one coherent place with relevant objects, artifacts, natural materials, "
                "soft natural light, balanced cinematic composition, muted colors, atmospheric depth, "
                "and a peaceful sleep-lecture mood. Avoid symbolic collages; make it a single specific image.",
                900,
            )
        else:
            visual_prompt = truncate_text(
                scene_lead +
                f"{summary}. {material_rule}Show one coherent place with believable characters, relevant objects, "
                "soft natural light, balanced cinematic composition, muted colors, atmospheric depth, "
                "and a peaceful sleep-lecture mood. Avoid symbolic collages; make it a single specific image.",
                900,
            )
        animation_positive_prompt = build_animation_positive_prompt(summary, visual_prompt)
        negative_prompt = DEFAULT_VIDEO_GROUP_NEGATIVE
        if ancient_prehistory and not exclude_people:
            negative_prompt = append_unique_csv_terms(DEFAULT_VIDEO_GROUP_NEGATIVE, ANCIENT_PREHISTORY_NEGATIVE, limit=700)
        if exclude_people:
            negative_prompt = append_unique_csv_terms(DEFAULT_VIDEO_GROUP_NEGATIVE, NO_PEOPLE_IMAGE_NEGATIVE, limit=700)
        groups.append({
            "id": f"video_group_{number:03d}",
            "title": f"Video group {number}",
            "summary": summary,
            "chunk_ids": ids,
            "visual_prompt": visual_prompt,
            "negative_prompt": negative_prompt,
            "animation_positive_prompt": animation_positive_prompt,
            "animation_negative_prompt": DEFAULT_ANIMATION_NEGATIVE_PROMPT,
            "grok_video_prompt": format_grok_imagine_video_prompt({"animation_positive_prompt": animation_positive_prompt, "visual_prompt": visual_prompt, "summary": summary}),
            "mood": "calm",
            "scene_type": "sleep lecture",
            "order": number - 1,
            "source": "fallback",
        })
    return groups


def build_animation_positive_prompt(summary: Any = "", visual_prompt: Any = "") -> str:
    scene_hint = truncate_text(summary or visual_prompt, 220)
    if scene_hint:
        return truncate_text(
            "Calm seamless image-to-video loop, perfect loop, first and last frame match naturally, locked camera, very subtle natural ambient motion only. "
            f"Preserve the scene inspired by: {scene_hint}. "
            "Animate cyclic gentle environmental details such as grass or leaves swaying in soft wind, water ripples, "
            "smoke or candle/fire flicker, drifting clouds, floating dust motes, and light fabric movement where appropriate. "
            "Keep the composition stable, slow, realistic, peaceful, continuous, with no cuts, no scene change, no object popping, and no beginning or ending reveal.",
            900,
        )
    return DEFAULT_ANIMATION_POSITIVE_PROMPT


def normalize_animation_positive_prompt(raw_group: dict[str, Any]) -> str:
    prompt = truncate_text(raw_group.get("animation_positive_prompt") or raw_group.get("loop_motion_prompt"), 900)
    if prompt:
        return prompt
    return build_animation_positive_prompt(raw_group.get("summary"), raw_group.get("visual_prompt"))


def normalize_animation_negative_prompt(raw_group: dict[str, Any]) -> str:
    prompt = truncate_text(raw_group.get("animation_negative_prompt"), 700)
    if prompt:
        return prompt
    return DEFAULT_ANIMATION_NEGATIVE_PROMPT


def normalize_grok_video_prompt(raw_group: dict[str, Any]) -> str:
    prompt = truncate_text(raw_group.get("grok_video_prompt"), 1800)
    if prompt:
        return prompt
    return format_grok_imagine_video_prompt(raw_group)


def normalize_group_media_duration(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(fallback if value in (None, "") else value)
    except (TypeError, ValueError):
        number = float(fallback or 0.0)
    if not math.isfinite(number):
        number = float(fallback or 0.0)
    return round(max(0.0, min(36000.0, number)), 3)


def normalize_group_media_layout(value: Any) -> str:
    layout = str(value or "sequence").strip().lower()
    return layout if layout in {"sequence", "overlay", "background", "manual"} else "sequence"


def normalize_group_media_item(raw_item: Any, idx: int = 0) -> dict[str, Any] | None:
    if not isinstance(raw_item, dict):
        return None
    media_type = str(raw_item.get("type") or raw_item.get("media_type") or "image").strip().lower()
    if media_type not in {"image", "video"}:
        media_type = "video" if str(raw_item.get("path") or raw_item.get("url") or "").lower().endswith((".mp4", ".webm", ".gif", ".mov")) else "image"
    path = str(raw_item.get("path") or "").strip()
    url = str(raw_item.get("url") or "").strip()
    item: dict[str, Any] = {
        "id": str(raw_item.get("id") or uuid.uuid4().hex[:10]),
        "type": media_type,
        "path": path,
        "url": url,
        "label": truncate_text(raw_item.get("label") or Path(path).name or f"Media {idx + 1}", 120),
        "role": truncate_text(raw_item.get("role") or "main", 80),
        "start_offset_sec": normalize_group_media_duration(raw_item.get("start_offset_sec"), 0.0),
        "duration_sec": normalize_group_media_duration(raw_item.get("duration_sec"), 0.0),
        "fit": str(raw_item.get("fit") or "cover").strip().lower(),
        "order": idx,
    }
    if item["fit"] not in {"cover", "contain", "fill"}:
        item["fit"] = "cover"
    if raw_item.get("volume") is not None:
        try:
            item["volume"] = round(max(0.0, min(2.0, float(raw_item.get("volume") or 0.0))), 3)
        except (TypeError, ValueError):
            item["volume"] = 1.0
    return item


def normalize_group_media_items(raw_items: Any, group: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(raw_items, list):
        for idx, raw_item in enumerate(raw_items):
            item = normalize_group_media_item(raw_item, idx)
            if item:
                items.append(item)
    group = group if isinstance(group, dict) else {}
    legacy: list[dict[str, Any]] = []
    image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
    video_meta = group.get("video") if isinstance(group.get("video"), dict) else {}
    if image_meta.get("path") or image_meta.get("url"):
        legacy.append({"id": "legacy_image", "type": "image", "path": image_meta.get("path", ""), "url": image_meta.get("url", ""), "label": "Generated image", "role": "background", "duration_sec": 0.0})
    if video_meta.get("path") or video_meta.get("url"):
        legacy.append({"id": "legacy_video", "type": "video", "path": video_meta.get("path", ""), "url": video_meta.get("url", ""), "label": "Generated video", "role": "background", "duration_sec": float(video_meta.get("duration_sec") or 0.0)})
    seen = {str(item.get("path") or item.get("url") or item.get("id")) for item in items}
    for raw_item in legacy:
        key = str(raw_item.get("path") or raw_item.get("url") or raw_item.get("id"))
        if key in seen:
            continue
        item = normalize_group_media_item(raw_item, len(items))
        if item:
            items.append(item)
            seen.add(key)
    for idx, item in enumerate(items):
        item["order"] = idx
    return items


def compact_ai_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": str(chunk.get("id") or ""), "order": idx, "text": truncate_text(chunk.get("text", ""), 1200)}
        for idx, chunk in enumerate(chunks)
        if str(chunk.get("id") or "")
    ]


def compact_ai_payload_chars(chunks: list[dict[str, Any]], payload: VideoGroupsAiRequest) -> int:
    sample = {
        "optional_user_instruction": truncate_text(payload.instruction, 1000),
        "chunks": compact_ai_chunks(chunks),
    }
    return len(json.dumps(sample, ensure_ascii=False))


def split_chunks_for_ai_batches(chunks: list[dict[str, Any]], payload: VideoGroupsAiRequest) -> list[list[dict[str, Any]]]:
    max_chunks = max(1, int(payload.max_section_chunks or 40))
    max_chars = max(5000, int(payload.max_request_chars or 22000))
    sections: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for chunk in chunks:
        chunk_chars = max(1, len(json.dumps(compact_ai_chunks([chunk]), ensure_ascii=False)))
        would_overflow = bool(current) and (len(current) >= max_chunks or current_chars + chunk_chars > max_chars)
        if would_overflow:
            sections.append(current)
            current = []
            current_chars = 0
        current.append(chunk)
        current_chars += chunk_chars
    if current:
        sections.append(current)
    return sections


def video_group_coverage_error(flattened: list[str], expected_ids: list[str], scope_label: str) -> str:
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


def normalize_video_groups(raw_groups: Any, chunks: list[dict[str, Any]], *, source: str | None = None, require_all_chunks: bool = False, expected_ordered_ids: list[str] | None = None, scope_label: str = "project") -> list[dict[str, Any]]:
    if not isinstance(raw_groups, list):
        if require_all_chunks:
            raise ValueError("AI response field 'groups' must be a list")
        return []
    ordered_ids = expected_ordered_ids or chunk_order_ids(chunks)
    valid_ids = set(ordered_ids)
    cursor = 0
    flattened: list[str] = []
    normalized: list[dict[str, Any]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, dict):
            if require_all_chunks:
                raise ValueError("Each group must be an object")
            continue
        raw_chunk_ids = raw_group.get("chunk_ids")
        if not isinstance(raw_chunk_ids, list):
            if require_all_chunks:
                raise ValueError("Each group must include chunk_ids list")
            continue
        ids = [str(chunk_id) for chunk_id in raw_chunk_ids if str(chunk_id) in valid_ids]
        if not ids:
            if require_all_chunks:
                raise ValueError("Group contains no valid chunk_ids")
            continue
        if require_all_chunks:
            expected_slice = ordered_ids[cursor:cursor + len(ids)]
            if ids != expected_slice:
                raise ValueError("Groups must preserve chunk order and use contiguous chunk ranges")
        number = len(normalized) + 1
        item = {
            "id": f"video_group_{number:03d}",
            "title": truncate_text(raw_group.get("title") or f"Video group {number}", 120),
            "summary": truncate_text(raw_group.get("summary"), 600),
            "chunk_ids": ids,
            "visual_prompt": truncate_text(raw_group.get("visual_prompt"), 900),
            "negative_prompt": truncate_text(raw_group.get("negative_prompt"), 500),
            "animation_positive_prompt": normalize_animation_positive_prompt(raw_group),
            "animation_negative_prompt": normalize_animation_negative_prompt(raw_group),
            "grok_video_prompt": normalize_grok_video_prompt(raw_group),
            "mood": truncate_text(raw_group.get("mood"), 80),
            "scene_type": truncate_text(raw_group.get("scene_type"), 80),
            "order": number - 1,
            "source": source or truncate_text(raw_group.get("source") or "manual", 40),
        }
        try:
            item["playback_speed"] = round(max(0.25, min(2.0, float(raw_group.get("playback_speed", 1.0) or 1.0))), 3)
        except (TypeError, ValueError):
            item["playback_speed"] = 1.0
        if isinstance(raw_group.get("image"), dict):
            item["image"] = normalize_group_image_meta(raw_group.get("image"))
        if isinstance(raw_group.get("video"), dict):
            item["video"] = normalize_group_video_meta(raw_group.get("video"))
        item["media_items"] = normalize_group_media_items(raw_group.get("media_items"), item)
        item["media_layout"] = normalize_group_media_layout(raw_group.get("media_layout"))
        item["default_media_duration_sec"] = normalize_group_media_duration(raw_group.get("default_media_duration_sec"), 0.0)
        if raw_group.get("repair_note"):
            item["repair_note"] = truncate_text(raw_group.get("repair_note"), 500)
        normalized.append(item)
        flattened.extend(ids)
        cursor += len(ids)
    if require_all_chunks and flattened != ordered_ids:
        raise ValueError(video_group_coverage_error(flattened, ordered_ids, scope_label))
    return normalized


def normalize_group_image_meta(raw_image: Any) -> dict[str, Any]:
    if not isinstance(raw_image, dict):
        return {}
    meta: dict[str, Any] = {
        "status": str(raw_image.get("status") or "ready")[:40],
        "provider": str(raw_image.get("provider") or "placeholder")[:40],
        "model": str(raw_image.get("model") or "")[:80],
        "aspect_ratio": str(raw_image.get("aspect_ratio") or "")[:40],
        "path": str(raw_image.get("path") or ""),
        "url": str(raw_image.get("url") or ""),
        "positive_prompt": truncate_text(raw_image.get("positive_prompt"), 3000),
        "negative_prompt": truncate_text(raw_image.get("negative_prompt"), 1500),
        "error": truncate_text(raw_image.get("error"), 1000),
    }
    for key in ("width", "height", "seed", "created_at", "updated_at"):
        if raw_image.get(key) is not None:
            meta[key] = raw_image.get(key)
    return {key: value for key, value in meta.items() if value not in (None, "")}


def normalize_group_video_meta(raw_video: Any) -> dict[str, Any]:
    if not isinstance(raw_video, dict):
        return {}
    meta: dict[str, Any] = {
        "status": str(raw_video.get("status") or "ready")[:40],
        "provider": str(raw_video.get("provider") or "comfyui")[:40],
        "model": str(raw_video.get("model") or "svd_xt")[:80],
        "model_checkpoint": str(raw_video.get("model_checkpoint") or "")[:200],
        "aspect_ratio": str(raw_video.get("aspect_ratio") or "")[:40],
        "resolution": str(raw_video.get("resolution") or "")[:40],
        "path": str(raw_video.get("path") or ""),
        "url": str(raw_video.get("url") or ""),
        "source_image_path": str(raw_video.get("source_image_path") or ""),
        "request_id": str(raw_video.get("request_id") or "")[:120],
        "positive_prompt": truncate_text(raw_video.get("positive_prompt"), 3000),
        "error": truncate_text(raw_video.get("error"), 1000),
    }
    for key in ("width", "height", "seed", "frames", "fps", "output_fps", "output_frames", "loop_count", "target_duration_sec", "motion_bucket_id", "augmentation_level", "min_cfg", "cfg", "steps", "created_at", "updated_at", "duration_sec"):
        if raw_video.get(key) is not None:
            meta[key] = raw_video.get(key)
    for key in ("loop", "pingpong"):
        if raw_video.get(key) is not None:
            meta[key] = bool(raw_video.get(key))
    return {key: value for key, value in meta.items() if value not in (None, "")}


def repair_ai_video_groups(raw_groups: Any, chunks: list[dict[str, Any]], expected_ordered_ids: list[str], scope_label: str = "project", *, source: str = "grok_repaired", exclude_people: bool = False) -> list[dict[str, Any]]:
    ordered_ids = [str(chunk_id) for chunk_id in expected_ordered_ids if str(chunk_id)]
    if not ordered_ids:
        return []
    valid_ids = set(ordered_ids)
    position_by_id = {chunk_id: idx for idx, chunk_id in enumerate(ordered_ids)}
    fallback_groups = fallback_video_groups(chunks, 4, exclude_people=exclude_people)
    if not isinstance(raw_groups, list):
        return normalize_video_groups(
            fallback_groups,
            chunks,
            source="fallback",
            require_all_chunks=True,
            expected_ordered_ids=ordered_ids,
            scope_label=f"{scope_label} repair fallback",
        )

    anchors: list[tuple[int, int, dict[str, Any], int, list[str]]] = []
    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    extra_ids: list[str] = []
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

    if not anchors:
        repaired_fallback = normalize_video_groups(
            fallback_groups,
            chunks,
            source="fallback",
            require_all_chunks=True,
            expected_ordered_ids=ordered_ids,
            scope_label=f"{scope_label} repair fallback",
        )
        for group in repaired_fallback:
            group["repair_note"] = f"{scope_label}: no usable Grok chunk ids; used fallback groups"
        return repaired_fallback

    anchors.sort(key=lambda item: (item[0], item[1], item[3]))
    spans: list[tuple[int, int, dict[str, Any], list[str]]] = []
    previous_end = -1
    for idx, (first_pos, last_pos, raw_group, _raw_index, group_ids) in enumerate(anchors):
        next_first = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(ordered_ids)
        start = previous_end + 1
        if idx == 0:
            start = 0
        end = max(last_pos, next_first - 1)
        if idx == len(anchors) - 1:
            end = len(ordered_ids) - 1
        end = min(len(ordered_ids) - 1, max(start, end))
        if start <= previous_end:
            start = previous_end + 1
        if start >= len(ordered_ids):
            break
        spans.append((start, end, raw_group, group_ids))
        previous_end = end

    if previous_end < len(ordered_ids) - 1 and spans:
        start, _end, raw_group, group_ids = spans[-1]
        spans[-1] = (start, len(ordered_ids) - 1, raw_group, group_ids)

    repaired: list[dict[str, Any]] = []
    removed_notes: list[str] = []
    if extra_ids:
        removed_notes.append(f"removed extra ids: {', '.join(extra_ids[:10])}{'…' if len(extra_ids) > 10 else ''}")
    if duplicate_ids:
        removed_notes.append(f"removed duplicate ids: {', '.join(duplicate_ids[:10])}{'…' if len(duplicate_ids) > 10 else ''}")
    missing_ids = [chunk_id for chunk_id in ordered_ids if chunk_id not in seen_ids]
    if missing_ids:
        removed_notes.append(f"inserted missing ids: {', '.join(missing_ids[:10])}{'…' if len(missing_ids) > 10 else ''}")
    repair_note = f"{scope_label}: repaired Grok chunk coverage"
    if removed_notes:
        repair_note += f" ({'; '.join(removed_notes)})"

    for start, end, raw_group, _group_ids in spans:
        ids = ordered_ids[start:end + 1]
        if not ids:
            continue
        number = len(repaired) + 1
        repaired.append({
            "id": f"video_group_{number:03d}",
            "title": truncate_text(raw_group.get("title") or f"Video group {number}", 120),
            "summary": truncate_text(raw_group.get("summary"), 600),
            "chunk_ids": ids,
            "visual_prompt": truncate_text(raw_group.get("visual_prompt"), 900),
            "negative_prompt": truncate_text(raw_group.get("negative_prompt"), 500),
            "animation_positive_prompt": normalize_animation_positive_prompt(raw_group),
            "animation_negative_prompt": normalize_animation_negative_prompt(raw_group),
            "grok_video_prompt": normalize_grok_video_prompt(raw_group),
            "mood": truncate_text(raw_group.get("mood"), 80),
            "scene_type": truncate_text(raw_group.get("scene_type"), 80),
            "order": number - 1,
            "source": source,
            "repair_note": repair_note,
        })

    return normalize_video_groups(
        repaired,
        chunks,
        source=source,
        require_all_chunks=True,
        expected_ordered_ids=ordered_ids,
        scope_label=f"{scope_label} repaired",
    )


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(raw[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("AI response root must be a JSON object")
    return parsed


def extract_json_value(text: str) -> Any:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        starts = [idx for idx in (raw.find("["), raw.find("{")) if idx >= 0]
        start = min(starts) if starts else -1
        end = max(raw.rfind("]"), raw.rfind("}"))
        if start < 0 or end <= start:
            raise
        return json.loads(raw[start:end + 1])


def is_transient_xai_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout, urllib.error.URLError)):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc).lower()
        if any(token in message for token in ("timed out", "timeout", "temporarily unavailable", "connection reset", "remote end closed", "service unavailable")):
            return True
        match = re.search(r"http\s+(\d{3})", message, flags=re.IGNORECASE)
        if match and int(match.group(1)) in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True
    return False


def call_xai_video_groups_with_retry(
    chunks: list[dict[str, Any]],
    payload: VideoGroupsAiRequest,
    api_key: str,
    *,
    section_context: str = "",
    scope_label: str = "project",
    progress_callback: Any | None = None,
    progress_base: float | None = None,
    progress_span: float = 0.0,
) -> list[dict[str, Any]]:
    attempts = max(1, XAI_VIDEO_GROUPS_ATTEMPTS)
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        if progress_callback:
            progress = progress_base if progress_base is not None else 35
            if progress_base is not None and progress_span > 0:
                progress = progress_base + ((attempt - 1) / max(1, attempts)) * min(progress_span, 6)
            progress_callback(f"Grok grouping {scope_label} (attempt {attempt}/{attempts})", progress)
        try:
            return call_xai_video_groups(chunks, payload, api_key, section_context=section_context, scope_label=scope_label)
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts or not is_transient_xai_error(exc):
                break
            delay = XAI_VIDEO_GROUPS_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            if progress_callback:
                progress = progress_base if progress_base is not None else 35
                progress_callback(f"Grok retrying {scope_label} after transient error (attempt {attempt}/{attempts} failed): {exc}", progress)
            time.sleep(delay)
    raise RuntimeError(f"{scope_label} failed after {attempts} attempt{'s' if attempts != 1 else ''}: {last_exc}") from last_exc


def call_xai_video_groups(chunks: list[dict[str, Any]], payload: VideoGroupsAiRequest, api_key: str, *, section_context: str = "", scope_label: str = "project") -> list[dict[str, Any]]:
    api_key = (api_key or "").strip()
    if not api_key:
        raise RuntimeError("xAI API key is not configured for this project and XAI_API_KEY is not set")
    base_url = (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
    model = resolve_xai_text_model(None, payload.model)
    min_chunks = max(1, int(payload.min_chunks_per_group or 2))
    max_chunks = max(min_chunks, int(payload.max_chunks_per_group or 8))
    compact_chunks = compact_ai_chunks(chunks)
    exclude_people = bool(payload.exclude_people_from_images)
    system_prompt = (
        "You group narration chunks into visually coherent video scenes and write image-generation prompts plus simple loop animation prompts. "
        "For each group, imagine the single frame an SDXL/RealVisXL model should render from the narration. "
        "Also describe a calm seamless image-to-video loop using only subtle cyclic natural ambient motion, with the first and last frame matching naturally. "
        "Return strictly valid JSON only, with root object {\"groups\":[...]}."
    )
    group_schema = {
        "id": "string; any temporary id is accepted, server will renumber",
        "title": "short human-readable title",
        "summary": "1-2 sentence factual summary of the narration covered by this group",
        "chunk_ids": "array of provided chunk ids, one contiguous range, preserving order",
        "visual_prompt": (
            "English SDXL/RealVisXL positive prompt, 60-120 words. Describe one concrete unified scene, not an abstract list. "
            "Infer the lecture setting and era from this group's own narration; do not assume the whole project is ancient, modern, space, medical, or any other fixed theme. "
            "Include subject, location, historical era or time period when implied, lighting, composition/camera, characters, "
            "important objects/materials, atmosphere and mood. Use realistic documentary/cinematic language. "
            "For ancient, prehistory, Stone Age, hominid, hunter-gatherer, campfire, or historical scenes, name the people specifically "
            "instead of generic 'figures' (for example two prehistoric humans, early hominids, ancient villagers) and make clothing/materials "
            "explicitly visible: barefoot prehistoric humans, rough animal-hide wraps, fur cloaks, handmade leather, plant-fiber cordage, or linen tunics only if era-appropriate. "
            "For prehistoric scenes, include no modern objects visible and no tailored clothing visible in the positive prompt when people or camps are shown. "
            "Do not include text overlays, subtitles, watermarks, UI, markdown, or multiple alternative scenes."
            + (" If exclude_people_from_images is true, this field must contain no people, faces, bodies, hands, crowds, characters, portraits, or clothing; describe only environmental, object, nature, architecture, or artifact-focused scenes." if exclude_people else "")
        ),
        "negative_prompt": (
            "English comma-separated SDXL negative prompt, 18-35 concise terms. Include quality/anatomy/text artifacts and "
            "scene-specific exclusions selected for this group's inferred setting. For ancient/prehistory scenes, include modern clothing, "
            "business suit, office suit, shirt and tie, jacket, blazer, dress pants, modern shoes, sneakers, watch, glasses, phone, city, office, modern buildings, cars. "
            "For non-ancient lectures, choose different relevant exclusions instead of copying ancient-world exclusions. No sentences."
        ),
        "animation_positive_prompt": (
            "English image-to-video positive prompt, 40-85 words. Request a calm, subtle, seamless looping video / perfect loop where the first and last frame match naturally. "
            "Keep the camera locked or nearly locked, with no cuts, no scene change, no sudden camera movement, and no beginning/end reveal. "
            "Use only natural ambient motion appropriate to the still image, such as grass swaying, leaves moving, water ripple, smoke/fire/candle flicker, "
            "dust motes, clouds drifting, or fabric lightly moving in cyclic gentle patterns. Preserve the scene and avoid story action."
        ),
        "animation_negative_prompt": (
            "English comma-separated animation negative prompt, 18-35 concise terms. Exclude character motion, fast action, cuts, zooms, pans, camera shake, "
            "morphing, warping, new objects appearing, objects disappearing, non-looping motion, one-way motion, sudden ending, start/end mismatch, object popping, text, subtitles, watermarks, jitter, and flicker artifacts."
        ),
        "grok_video_prompt": "English Grok Imagine Video prompt, editable later; can reuse animation_positive_prompt but should stand alone and mention loop, locked camera, subtle ambient motion.",
        "mood": "2-6 English words describing the emotional tone",
        "scene_type": "2-6 English words describing the visual scene category",
    }
    user_prompt = {
        "task": "Create semantic video groups for XTTS Studio chunks.",
        "section_context": section_context,
        "output_schema": {"groups": [group_schema]},
        "rules": [
            "Root must be exactly an object with key groups.",
            "Each group fields: id, title, summary, chunk_ids, visual_prompt, negative_prompt, animation_positive_prompt, animation_negative_prompt, grok_video_prompt, mood, scene_type.",
            "Use every chunk exactly once.",
            "Do not omit any chunk id, even if a chunk is short or transitional.",
            "Keep original chunk order.",
            "Every group must be one contiguous range of chunks.",
            "Do not invent chunk ids.",
            "Do not reference chunks outside the provided chunks list.",
            "Prefer groups representing about 30-90 seconds of coherent visual meaning.",
            "For a sleepy lecture, do not change scenes too often; keep transitions calm and sparse.",
            f"Aim for {min_chunks}-{max_chunks} chunks per group unless semantic boundaries require otherwise.",
            f"exclude_people_from_images is {'true' if exclude_people else 'false'}.",
            "When exclude_people_from_images is true, it overrides all ancient/prehistory/historical examples and rules that would otherwise include humans or clothing.",
            "When exclude_people_from_images is true, visual_prompt must avoid people, faces, bodies, crowds, hands, characters, portraits, human silhouettes, skin, eyes, hair, and clothing; create calm environmental/object/nature/architecture/artifact-focused scenes instead.",
            "When exclude_people_from_images is true, negative_prompt must include people, person, human, face, body, crowd, hands, characters, clothing, portrait, skin, eyes, hair.",
            "visual_prompt must be written in English and be directly usable as the main SDXL/RealVisXL scene description.",
            "visual_prompt must be 60-120 words when possible, detailed enough to render a specific frame.",
            "visual_prompt must describe exactly one coherent image: what is visible, where it is, approximate era, light, composition, people, objects, materials, and mood.",
            "Infer the setting, era, and visual rules separately for each group from the provided chunk text and section context; never force one lecture theme globally across all groups.",
            "For prehistory, Stone Age, early human, hominid, hunter-gatherer, ancient camp, campfire, or historical scenes only, never rely on generic people words like 'figures' or 'persons'; write specific subjects such as two prehistoric humans, early hominids, ancient villagers, or hunter-gatherers.",
            "For ancient/prehistory people only, explicitly state visible clothing and materials: barefoot prehistoric humans, rough animal-hide wraps, fur cloaks, handmade leather, plant-fiber cordage, bone or stone tools, simple linen tunics only when era-appropriate.",
            "For prehistoric or ancient campfire scenes only, include no modern objects visible and no tailored clothing visible in visual_prompt, while still positively describing the correct clothing and materials.",
            "Avoid ambiguous modernizing words for ancient/prehistory scenes only, including outfit, trousers, pants, shirt, jacket, coat, uniform, formal wear, dressed figures, camping trip, tourists, or safari.",
            "Avoid abstract themes, bullet-like keyword dumps, vague phrases such as 'the concept of', and instructions to the viewer or model.",
            "If the narration is abstract, convert it into a plausible calm documentary scene anchored in the text instead of listing concepts.",
            "negative_prompt must be English, comma-separated, SDXL-friendly, and useful for RealVisXL quality control.",
            "negative_prompt should include common defects: text, watermark, logo, low quality, blurry, deformed hands, extra fingers, bad anatomy, oversaturated, cartoon, anime, cgi.",
            "negative_prompt must add exclusions relevant to the specific group setting: e.g. anachronistic objects for historical scenes, neon UI for calm nature scenes, spacesuits for naked-eye astronomy scenes, horror or action for sleep-documentary scenes, or other theme-specific problems inferred from context.",
            "For ancient/prehistory/historical scenes only, negative_prompt must strongly exclude modern clothing, business suit, office suit, shirt and tie, jacket, blazer, dress pants, modern shoes, sneakers, watch, glasses, phone, modern objects, city, office, modern buildings, cars, tourists, safari, modern campfire scene.",
            "For non-ancient lectures, do not copy ancient/prehistory exclusions unless that group's own visual setting actually implies them; choose exclusions that match that non-ancient topic.",
            "Do not put positive visual details inside negative_prompt.",
            "animation_positive_prompt must be written in English and must describe a simple calm seamless looping video, perfect loop, first and last frame match naturally.",
            "animation_positive_prompt must keep the camera locked or nearly locked, with very low camera movement, no cuts, no scene change, no sudden camera movement, no beginning/end reveal, and no object popping.",
            "animation_positive_prompt must use only cyclic natural ambient motion: grass swaying, leaves moving, water ripple, smoke/fire/candle flicker, dust motes, clouds drifting, or fabric lightly moving when appropriate.",
            "For landscape/environment scenes, animation_positive_prompt must say leaves, grass, water, or clouds move in a gentle cyclic pattern when those elements are visible.",
            "animation_positive_prompt must avoid character motion, gestures, walking, talking, fast action, cuts, zooms, pans, morphing, camera shake, new objects appearing, objects disappearing, text, and start/end mismatch.",
            "animation_negative_prompt must be English, comma-separated, and focused on preventing non-loop-friendly motion artifacts and scene changes; include cuts, jump cut, scene transition, camera zoom, camera pan, new objects appearing, objects disappearing, non-looping motion, one-way motion, sudden ending, start/end mismatch.",
            "grok_video_prompt must be populated for every group and usable directly by Grok Imagine Video; if unsure, adapt animation_positive_prompt into one standalone prompt.",
        ],
        "ancient_riverside_visual_prompt_example_for_historical_scenes_only": (
            "A quiet realistic reconstruction of an ancient riverside settlement at dawn, with two linen-clad figures preparing clay vessels beside a low mud-brick wall. "
            "Reeds and calm water frame the background, warm amber sunlight touches stone, wood, and woven baskets, and the camera sits at eye level with a gentle wide composition. "
            "The scene feels peaceful, historically plausible, softly cinematic, and suitable for a slow sleep documentary."
        ),
        "prehistoric_campfire_visual_prompt_example_for_prehistoric_scenes_only": (
            "A realistic archaeology-documentary reconstruction of two prehistoric humans sitting beside a small campfire at dusk outside a shallow cave. "
            "Both are barefoot and visibly wrapped in rough animal-hide garments and fur cloaks tied with simple plant-fiber cordage, with stone tools and unshaped branches near the fire. "
            "Warm ember light illuminates natural skin, ash, rock, dirt, and smoke; no modern objects visible, no tailored clothing visible. Calm eye-level composition, peaceful sleep documentary mood."
        ),
        "generic_quality_negative_prompt_example_for_all_scenes": DEFAULT_VIDEO_GROUP_NEGATIVE,
        "prehistoric_campfire_negative_prompt_example_for_prehistoric_scenes_only": append_unique_csv_terms(
            DEFAULT_VIDEO_GROUP_NEGATIVE,
            ANCIENT_PREHISTORY_NEGATIVE,
            limit=700,
        ),
        "non_ancient_negative_prompt_note": "For non-ancient lectures, choose different exclusions relevant to that setting instead of using prehistoric/ancient clothing or modern-object exclusions by default.",
        "good_animation_positive_prompt_example": (
            "Calm seamless image-to-video loop, perfect loop, first and last frame match naturally, with a locked eye-level camera. Reeds and grass move in a gentle cyclic breeze, calm river water forms slow repeating ripples, "
            "warm dawn light remains steady, and tiny dust motes drift subtly. No cuts, no beginning/end reveal, no object popping, peaceful realistic ambient movement only."
        ),
        "good_animation_negative_prompt_example": DEFAULT_ANIMATION_NEGATIVE_PROMPT,
        "optional_user_instruction": truncate_text(payload.instruction, 1000),
        "exclude_people_from_images": exclude_people,
        "chunks": compact_chunks,
    }
    if exclude_people:
        user_prompt["no_people_visual_prompt_example"] = (
            "A quiet prehistoric riverside at dawn with reeds, smooth stones, handmade clay vessels, scattered bone and stone tools, ash from an old fire, animal-hide bundles with no body present, "
            "soft mist over calm water, warm natural light, realistic archaeology-documentary composition, peaceful sleep documentary mood, no people or human figures visible."
        )
        user_prompt["no_people_negative_prompt_example"] = append_unique_csv_terms(DEFAULT_VIDEO_GROUP_NEGATIVE, NO_PEOPLE_IMAGE_NEGATIVE, limit=700)
    request_body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=XAI_VIDEO_GROUPS_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"xAI request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"xAI request failed: {exc.reason}") from exc
    completion = json.loads(response_body)
    content = completion.get("choices", [{}])[0].get("message", {}).get("content", "")
    ai_json = extract_json_object(content)
    raw_groups = ai_json.get("groups")
    expected_ids = chunk_order_ids(chunks)
    try:
        return normalize_video_groups(
            raw_groups,
            chunks,
            source="grok",
            require_all_chunks=True,
            expected_ordered_ids=expected_ids,
            scope_label=scope_label,
        )
    except ValueError:
        return repair_ai_video_groups(raw_groups, chunks, expected_ids, scope_label, source="grok_repaired", exclude_people=exclude_people)


def compact_stress_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": str(chunk.get("id") or ""), "order": idx, "text": str(chunk.get("text") or "")}
        for idx, chunk in enumerate(chunks)
        if str(chunk.get("id") or "")
    ]


@dataclass
class AiStressStats:
    total: int = 0
    marked: int = 0
    unchanged: int = 0
    rejected: int = 0
    retried_individually: int = 0
    failed_batches: int = 0
    errors: int = 0


def int_setting(settings: dict[str, Any], key: str, default: int, *, min_value: int, max_value: int) -> int:
    try:
        value = int(settings.get(key, default))
    except (TypeError, ValueError):
        value = int(default)
    return max(min_value, min(max_value, value))


def stress_chunk_request_chars(chunk: dict[str, Any]) -> int:
    return len(json.dumps({"id": str(chunk.get("id") or ""), "text": str(chunk.get("text") or "")}, ensure_ascii=False)) + 80


def split_chunks_for_stress_batches(chunks: list[dict[str, Any]], max_chunks: int = XAI_STRESS_MAX_CHUNKS_PER_BATCH, max_chars: int = XAI_STRESS_MAX_REQUEST_CHARS) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    max_chunks = max(1, int(max_chunks or XAI_STRESS_MAX_CHUNKS_PER_BATCH))
    max_chars = max(500, int(max_chars or XAI_STRESS_MAX_REQUEST_CHARS))
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_chars = stress_chunk_request_chars(chunk)
        if current and (chunk_chars >= XAI_STRESS_LONG_CHUNK_CHARS or len(current) >= max_chunks or current_chars + chunk_chars > max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(chunk)
        current_chars += chunk_chars
        if chunk_chars >= XAI_STRESS_LONG_CHUNK_CHARS:
            batches.append(current)
            current = []
            current_chars = 0
    if current:
        batches.append(current)
    return batches


def strip_stress_marks_for_validation(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text or ""))
    return unicodedata.normalize("NFC", normalized.replace("\u0301", ""))


def compact_stress_validation_text(text: str) -> str:
    return re.sub(r"\s+", " ", strip_stress_marks_for_validation(text)).strip()


def normalize_ai_stress_items(raw_items: Any, chunks: list[dict[str, Any]]) -> dict[str, str]:
    if isinstance(raw_items, dict) and isinstance(raw_items.get("chunks"), list):
        raw_items = raw_items.get("chunks")
    if not isinstance(raw_items, list):
        raise ValueError("AI response field 'chunks' must be a list")
    original_by_id = {str(chunk.get("id") or ""): str(chunk.get("text") or "") for chunk in chunks if isinstance(chunk, dict)}
    normalized: dict[str, str] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("id") or "")
        if chunk_id not in original_by_id:
            continue
        stressed = unicodedata.normalize("NFC", str(item.get("stressed_text") or item.get("text") or "").strip())
        original = original_by_id[chunk_id]
        if not stressed:
            continue
        original_compact = compact_stress_validation_text(original)
        stressed_compact = compact_stress_validation_text(stressed)
        if stressed_compact != original_compact:
            # Do not accept rewrites; stress marks are allowed, content changes are not.
            continue
        normalized[chunk_id] = stressed
    return normalized


def stress_response_missing_ids(stressed_by_id: dict[str, str], chunks: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_id = str(chunk.get("id") or "")
        if chunk_id and chunk_id not in stressed_by_id:
            missing.append(chunk_id)
    return missing


def stress_response_token_budget(chunks: list[dict[str, Any]]) -> int:
    text_chars = sum(len(str(chunk.get("text") or "")) for chunk in chunks if isinstance(chunk, dict))
    return max(1200, min(XAI_STRESS_MAX_TOKENS, int(text_chars * 1.8) + 1200))


def call_xai_stress_batch(chunks: list[dict[str, Any]], api_key: str, *, model: str = "") -> dict[str, str]:
    api_key = (api_key or "").strip()
    if not api_key:
        raise RuntimeError("xAI API key is not configured")
    base_url = (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
    selected_model = resolve_xai_text_model(None, model)
    payload = {
        "task": "Add Russian stress marks for TTS chunk synthesis.",
        "output_schema": [{"id": "same id", "stressed_text": "same text with combining acute marks U+0301 after stressed Russian vowels where possible"}],
        "rules": [
            "Return strictly valid JSON array only, with one object per input chunk and keys id and stressed_text only. No commentary and no root object.",
            "Preserve every character, word order, punctuation, capitalization, spacing meaning, numbers, and paragraph boundaries; do not rewrite, translate, normalize ё, or correct style.",
            "Only add Russian stress marks as combining acute accent U+0301 after stressed vowels, for example за́мок, холме́, мука́, or столе́.",
            "Add exactly one stress mark to every Russian word that contains at least one Russian vowel when the stress is known, obvious, dictionary-standard, or can be reasonably inferred from normal Russian pronunciation.",
            "Do not mark only unusual or uncertain words: common short words, function words, inflected forms, and repeated words must also receive stress marks when they contain Russian vowels.",
            "Do not add stress to abbreviations, numbers, symbols, foreign words, vowel-less words, or words where a stress mark would be inappropriate.",
            "If the correct stress for a word is genuinely unknown or uncertain, leave that word unchanged rather than guessing.",
            "Return every provided id exactly once and do not invent ids.",
        ],
        "chunks": compact_stress_chunks(chunks),
    }
    request_body = {
        "model": selected_model,
        "temperature": 0.0,
        "max_tokens": stress_response_token_budget(chunks),
        "messages": [
            {"role": "system", "content": "Return a JSON array only. Add Russian combining acute stress marks for TTS. Never rewrite text."},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=XAI_STRESS_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"xAI stress request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"xAI stress request failed: {exc.reason}") from exc
    completion = json.loads(response_body)
    content = completion.get("choices", [{}])[0].get("message", {}).get("content", "")
    ai_value = extract_json_value(content)
    return normalize_ai_stress_items(ai_value, chunks)


def apply_ai_stress_to_chunk(chunk: dict[str, Any], stressed: str, *, source: str = "grok") -> bool:
    if not isinstance(chunk, dict):
        return False
    original = str(chunk.get("text") or "")
    stressed_text = unicodedata.normalize("NFC", str(stressed or "").strip())
    if not original or not stressed_text or stressed_text == original:
        chunk.setdefault("tts_text", str(chunk.get("tts_text") or original))
        chunk.setdefault("stressed_text", str(chunk.get("stressed_text") or original))
        chunk.setdefault("stress_source", str(chunk.get("stress_source") or "original"))
        return False
    chunk["stressed_text"] = stressed_text
    chunk["tts_text"] = stressed_text
    chunk["stress_source"] = source
    return True


def ensure_chunk_stress_fields(chunks: list[dict[str, Any]], *, source: str = "original") -> None:
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        text = str(chunk.get("text") or "")
        chunk["text"] = text
        if chunk.get("stressed_text") in (None, ""):
            chunk["stressed_text"] = text
        if chunk.get("tts_text") in (None, ""):
            chunk["tts_text"] = str(chunk.get("stressed_text") or text)
        chunk["stress_source"] = str(chunk.get("stress_source") or source)


def sanitize_split_chunk_for_response(chunk: dict[str, Any]) -> None:
    """Keep split chunk data JSON-safe after optional post-processing."""
    if not isinstance(chunk, dict):
        return
    for key in ("id", "text", "boundary_type", "audio_path", "selected_version_id", "stressed_text", "tts_text", "stress_source"):
        chunk[key] = str(chunk.get(key) or "")
    try:
        chunk["order"] = int(chunk.get("order") or 0)
    except (TypeError, ValueError):
        chunk["order"] = 0
    for key in ("pause_after", "duration_sec"):
        try:
            value = float(chunk.get(key) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if not math.isfinite(value):
            value = 0.0
        chunk[key] = value
    if not isinstance(chunk.get("versions"), list):
        chunk["versions"] = []
    if chunk.get("generated_at") is not None:
        chunk["generated_at"] = str(chunk.get("generated_at") or "")


def call_xai_stress_batch_with_retry(chunks: list[dict[str, Any]], api_key: str, *, model: str = "", attempts: int | None = None) -> dict[str, str]:
    max_attempts = max(1, int(attempts if attempts is not None else XAI_STRESS_ATTEMPTS))
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return call_xai_stress_batch(chunks, api_key, model=model)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts or not is_transient_xai_error(exc):
                break
            time.sleep(XAI_VIDEO_GROUPS_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
    raise RuntimeError(f"Grok stress marking failed after {max_attempts} attempts: {last_exc}") from last_exc


def apply_ai_stress_result_to_chunk(chunk: dict[str, Any], stressed_by_id: dict[str, str], stats: AiStressStats) -> bool:
    chunk_id = str(chunk.get("id") or "")
    original = str(chunk.get("text") or "")
    stressed = stressed_by_id.get(chunk_id)
    if not stressed:
        stats.rejected += 1
        return False
    if compact_stress_validation_text(stressed) != compact_stress_validation_text(original):
        stats.rejected += 1
        return False
    if apply_ai_stress_to_chunk(chunk, stressed, source="grok"):
        stats.marked += 1
        return True
    stats.unchanged += 1
    return False


def retry_missing_stress_chunks_individually(
    missing_chunks: list[dict[str, Any]],
    api_key: str,
    *,
    model: str,
    attempts: int,
    stats: AiStressStats,
    errors: list[str],
) -> None:
    for single in missing_chunks:
        stats.retried_individually += 1
        try:
            stressed_by_id = call_xai_stress_batch_with_retry([single], api_key, model=model, attempts=attempts)
        except Exception as single_exc:
            stats.errors += 1
            errors.append(str(single_exc))
            stats.rejected += 1
            continue
        apply_ai_stress_result_to_chunk(single, stressed_by_id, stats)


def add_ai_stress_to_chunks(project: dict[str, Any], chunks: list[dict[str, Any]]) -> tuple[int, str]:
    ensure_chunk_stress_fields(chunks)
    settings = project.get("settings", {}) if isinstance(project.get("settings"), dict) else {}
    if not bool(settings.get("ai_add_russian_stress_marks", DEFAULT_SETTINGS["ai_add_russian_stress_marks"])):
        return 0, "disabled"
    stress_model = resolve_xai_text_model(project, str(settings.get("ai_stress_model") or ""))
    api_key = resolve_xai_api_key(project, safe_project_id(str(project.get("id") or active_project_id())))
    if not api_key:
        return 0, f"Grok/xAI key not configured; kept original chunks (model would be {stress_model})"
    batch_chunks = int_setting(settings, "ai_stress_batch_chunks", int(DEFAULT_SETTINGS["ai_stress_batch_chunks"]), min_value=1, max_value=12)
    max_request_chars = int_setting(settings, "ai_stress_max_request_chars", int(DEFAULT_SETTINGS["ai_stress_max_request_chars"]), min_value=500, max_value=20000)
    configured_retries = int_setting(settings, "ai_stress_retries", int(DEFAULT_SETTINGS["ai_stress_retries"]), min_value=0, max_value=5)
    attempts = max(1, configured_retries + 1)
    stats = AiStressStats(total=sum(1 for chunk in chunks if isinstance(chunk, dict) and str(chunk.get("id") or "")))
    errors: list[str] = []
    for batch in split_chunks_for_stress_batches(chunks, max_chunks=batch_chunks, max_chars=max_request_chars):
        try:
            stressed_by_id = call_xai_stress_batch_with_retry(batch, api_key, model=stress_model, attempts=attempts)
        except Exception as exc:
            stats.failed_batches += 1
            stats.errors += 1
            errors.append(str(exc))
            retry_missing_stress_chunks_individually(batch, api_key, model=stress_model, attempts=attempts, stats=stats, errors=errors)
            continue
        missing_ids = set(stress_response_missing_ids(stressed_by_id, batch))
        for chunk in batch:
            if str(chunk.get("id") or "") not in missing_ids:
                apply_ai_stress_result_to_chunk(chunk, stressed_by_id, stats)
        missing_chunks = [chunk for chunk in batch if str(chunk.get("id") or "") in missing_ids]
        if missing_chunks:
            retry_missing_stress_chunks_individually(missing_chunks, api_key, model=stress_model, attempts=attempts, stats=stats, errors=errors)
    unresolved = max(0, stats.total - stats.marked - stats.unchanged - stats.rejected)
    if unresolved:
        stats.rejected += unresolved
    note = (
        f"Grok stress: {stats.marked}/{stats.total} marked, {stats.unchanged} unchanged/skipped, "
        f"{stats.rejected} rejected, {stats.retried_individually} retried individually using {stress_model}"
    )
    if errors:
        note += f"; fallback kept originals for failed items ({stats.errors} error(s), {stats.failed_batches} failed batch(es))"
    return stats.marked, note


def add_ai_stress_to_chunks_safe(project: dict[str, Any], chunks: list[dict[str, Any]]) -> tuple[int, str]:
    try:
        return add_ai_stress_to_chunks(project, chunks)
    except Exception as exc:
        LOGGER.warning("Optional Grok stress marking failed during chunk split; keeping original chunks: %s: %s", type(exc).__name__, exc)
        ensure_chunk_stress_fields(chunks, source="original")
        detail = truncate_text(str(exc), 220)
        return 0, f"Grok stress marking skipped after non-fatal error: {type(exc).__name__}: {detail}; kept original chunks"


def renumber_video_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    renumbered: list[dict[str, Any]] = []
    for idx, group in enumerate(groups, start=1):
        item = dict(group)
        item["id"] = f"video_group_{idx:03d}"
        item["order"] = idx - 1
        renumbered.append(item)
    return renumbered


def generate_video_groups_ai(project: dict[str, Any], payload: VideoGroupsAiRequest, progress_callback: Any | None = None) -> list[dict[str, Any]]:
    chunks = ordered_project_chunks(project)
    if not chunks:
        raise HTTPException(status_code=400, detail="Project has no chunks to group")
    if payload.exclude_people_from_images is None:
        payload.exclude_people_from_images = bool(project.get("settings", {}).get("image_exclude_people", DEFAULT_SETTINGS["image_exclude_people"]))
    project_id = safe_project_id(str(project.get("id") or active_project_id()))
    api_key = resolve_xai_api_key(project, project_id)
    if not api_key:
        if payload.fallback_on_error:
            max_chunks = int(payload.max_chunks_per_group or 4)
            return fallback_video_groups(chunks, max_chunks if max_chunks > 0 else 4, exclude_people=bool(payload.exclude_people_from_images))
        raise HTTPException(status_code=400, detail="Grok/xAI API key is not configured")
    strategy = (payload.strategy or "auto").strip().lower()
    if strategy not in {"single", "batched", "auto"}:
        raise HTTPException(status_code=400, detail="strategy must be single, batched, or auto")
    should_batch = strategy == "batched" or (strategy == "auto" and compact_ai_payload_chars(chunks, payload) > int(payload.max_request_chars or 22000))
    try:
        if not should_batch:
            if progress_callback:
                progress_callback("Calling Grok for project", 35)
            return call_xai_video_groups_with_retry(chunks, payload, api_key, scope_label="project", progress_callback=progress_callback, progress_base=35)
        sections = split_chunks_for_ai_batches(chunks, payload)
        all_groups: list[dict[str, Any]] = []
        for idx, section_chunks in enumerate(sections, start=1):
            section_label = f"section {idx}/{len(sections)}"
            attempts = max(1, XAI_VIDEO_GROUPS_ATTEMPTS)
            if progress_callback:
                base = 20 + ((idx - 1) / max(1, len(sections))) * 70
                progress_callback(f"Grok grouping {section_label} (attempt 1/{attempts})", base)
            context = (
                f"This is section {idx} of {len(sections)} of a long lecture; "
                "keep visual groups coherent, do not reference chunks outside this section."
            )
            try:
                section_base = 20 + ((idx - 1) / max(1, len(sections))) * 70
                section_span = 70 / max(1, len(sections))
                section_groups = call_xai_video_groups_with_retry(
                    section_chunks,
                    payload,
                    api_key,
                    section_context=context,
                    scope_label=section_label,
                    progress_callback=progress_callback,
                    progress_base=section_base,
                    progress_span=section_span,
                )
            except Exception as exc:
                if payload.fallback_on_error:
                    if progress_callback:
                        progress_callback(f"Grok {section_label} failed after {attempts} attempts; using fallback groups", 20 + ((idx - 1) / max(1, len(sections))) * 70)
                    section_groups = fallback_video_groups(section_chunks, int(payload.max_chunks_per_group or 4), exclude_people=bool(payload.exclude_people_from_images))
                    section_groups = normalize_video_groups(
                        section_groups,
                        section_chunks,
                        source="fallback",
                        require_all_chunks=True,
                        expected_ordered_ids=chunk_order_ids(section_chunks),
                        scope_label=f"{section_label} fallback",
                    )
                else:
                    raise RuntimeError(f"Section {idx}/{len(sections)} failed after {attempts} attempts: {exc}") from exc
            all_groups.extend(section_groups)
            if progress_callback:
                done = 20 + (idx / max(1, len(sections))) * 70
                progress_callback(f"Grok grouped {section_label}", done)
        return normalize_video_groups(
            renumber_video_groups(all_groups),
            chunks,
            source="grok-batched",
            require_all_chunks=True,
            expected_ordered_ids=chunk_order_ids(chunks),
            scope_label="project after merging sections",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate video groups via xAI: {exc}") from exc


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


def project_secrets_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.secrets.json"


def load_project_secrets(project_id: str) -> dict[str, Any]:
    path = project_secrets_path(project_id)
    if not path.exists():
        return {}
    try:
        data = load_json_file(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_project_secrets(project_id: str, data: dict[str, Any]) -> None:
    clean = {str(key): value for key, value in (data or {}).items() if value not in (None, "")}
    path = project_secrets_path(project_id)
    if clean:
        atomic_write_json(path, clean)
    elif path.exists():
        path.unlink()


def resolve_xai_api_key(project: dict[str, Any], project_id: str) -> str:
    secrets = load_project_secrets(project_id)
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


def xai_api_key_hint(project_id: str) -> str:
    project_key = str(load_project_secrets(project_id).get("xai_api_key") or "").strip()
    if project_key:
        return f"Project key configured ({mask_secret(project_key)})"
    env_key = os.environ.get("XAI_API_KEY", "").strip()
    if env_key:
        return f"Using XAI_API_KEY from environment ({mask_secret(env_key)})"
    return "Not configured"


def apply_safe_secret_settings(project: dict[str, Any], project_id: str) -> None:
    settings = project.setdefault("settings", {})
    settings.pop("xai_api_key", None)
    configured = bool(resolve_xai_api_key(project, project_id))
    settings["xai_api_key_configured"] = configured
    settings["xai_api_key_hint"] = xai_api_key_hint(project_id)


def project_outputs_dir(project_id: str) -> Path:
    return project_dir(project_id) / "outputs"


def project_chunks_dir(project_id: str) -> Path:
    return project_outputs_dir(project_id) / "chunks"


def project_images_dir(project_id: str) -> Path:
    return project_outputs_dir(project_id) / "images"


def project_videos_dir(project_id: str) -> Path:
    return project_outputs_dir(project_id) / "videos"


def project_exports_dir(project_id: str) -> Path:
    return project_outputs_dir(project_id) / "export"


def project_uploads_dir(project_id: str) -> Path:
    return project_dir(project_id) / "uploads"


def ensure_project_dirs(project_id: str) -> None:
    project_dir(project_id).mkdir(parents=True, exist_ok=True)
    project_outputs_dir(project_id).mkdir(parents=True, exist_ok=True)
    project_chunks_dir(project_id).mkdir(parents=True, exist_ok=True)
    project_images_dir(project_id).mkdir(parents=True, exist_ok=True)
    project_exports_dir(project_id).mkdir(parents=True, exist_ok=True)
    project_uploads_dir(project_id).mkdir(parents=True, exist_ok=True)


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
    index = load_json_file(PROJECTS_INDEX_PATH)
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
            legacy_project = load_json_file(DEFAULT_PROJECT_PATH)
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
    project = load_json_file(path)
    repaired_mojibake_fields = repair_project_mojibake_fields(project)
    project["id"] = pid
    project.setdefault("name", pid)
    project.setdefault("created_at", time.time())
    project.setdefault("updated_at", time.time())
    project.setdefault("settings", DEFAULT_SETTINGS.copy())
    for key, value in DEFAULT_SETTINGS.items():
        project["settings"].setdefault(key, value)
    if (
        str(project["settings"].get("image_provider") or DEFAULT_SETTINGS["image_provider"]).strip().lower() == "comfyui"
        and not project["settings"].get("image_comfyui_autostart_user_set")
        and project["settings"].get("image_comfyui_autostart") is False
    ):
        project["settings"]["image_comfyui_autostart"] = True
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
    if repaired_mojibake_fields:
        project.setdefault("status", {})["message"] = f"Repaired text encoding in {repaired_mojibake_fields} field(s)"
        project.setdefault("status", {})["updated_at"] = time.time()
        save_project(project, pid)
    return project


def normalize_arrangement(project: dict[str, Any]) -> None:
    arrangement = project.setdefault("arrangement", {})
    video = arrangement.setdefault("video", {})
    video["groups"] = normalize_video_groups(video.get("groups") if isinstance(video.get("groups"), list) else [], ordered_project_chunks(project))
    migrate_ungrouped_chunks_to_video_groups(project)
    raw_speed_points = video.get("speed_envelope") if isinstance(video.get("speed_envelope"), list) else []
    speed_points: list[dict[str, float]] = []
    for point in raw_speed_points:
        try:
            speed_points.append({
                "time": round(max(0.0, float(point.get("time", 0.0))), 3),
                "speed": round(max(0.25, min(2.0, float(point.get("speed", point.get("playback_rate", 1.0)) or 1.0))), 3),
            })
        except (AttributeError, TypeError, ValueError):
            continue
    video["speed_envelope"] = sorted(speed_points or [{"time": 0.0, "speed": 1.0}], key=lambda p: p["time"])
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


def migrate_ungrouped_chunks_to_video_groups(project: dict[str, Any]) -> None:
    chunks = ordered_project_chunks(project)
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
    with PROJECT_SAVE_LOCK:
        pid = safe_project_id(project_id or str(project.get("id") or active_project_id()))
        project["id"] = pid
        project["updated_at"] = time.time()
        project.setdefault("settings", {}).pop("xai_api_key", None)
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


def pause_range_for_boundary(boundary_type: Any, low: float, high: float) -> tuple[float, float]:
    low = clamp_pause(low)
    high = clamp_pause(high)
    if high < low:
        low, high = high, low
    span = max(0.01, high - low)
    kind = str(boundary_type or "sentence").lower()
    if kind == "section":
        return clamp_pause(max(0.9, high + span * 2.0)), clamp_pause(max(1.4, high + span * 3.8))
    if kind == "paragraph":
        return clamp_pause(max(0.45, high + span * 0.9)), clamp_pause(max(0.9, high + span * 2.2))
    return low, high


def stable_split_pause_after(project: dict[str, Any], text: str, order: int, low: float, high: float, boundary_type: Any = "sentence") -> float:
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
        "boundary_type": boundary_type or "sentence",
    }, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(seed_payload.encode("utf-8")).digest()
    unit = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
    return round(low + (high - low) * unit, 3)


def normalize_chunk_pauses(project: dict[str, Any], chunk: dict[str, Any]) -> None:
    fallback = chunk.get("pause_after_resolved", chunk.get("pause_after", 0.0))
    chunk["pause_after"] = clamp_pause(chunk.get("pause_after"), float(fallback or 0.0))
    chunk["pause_after_resolved"] = chunk["pause_after"]
    if chunk.get("boundary_type") not in {"sentence", "paragraph", "section"}:
        chunk["boundary_type"] = "sentence"
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
    apply_safe_secret_settings(project, safe_project_id(str(project.get("id") or active_project_id())))
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


def image_settings(project: dict[str, Any]) -> dict[str, Any]:
    raw = project.get("settings", {}) if isinstance(project.get("settings"), dict) else {}
    provider = str(raw.get("image_provider") or DEFAULT_SETTINGS["image_provider"]).strip().lower()
    if provider not in {"placeholder", "comfyui", "grok", "xai"}:
        provider = "comfyui"
    if provider == "xai":
        provider = "grok"
    model = str(raw.get("image_model") or DEFAULT_SETTINGS["image_model"]).strip().lower()
    if provider == "grok":
        model = "grok"
    if model not in {"realvisxl", "sdxl", "juggernautxl", "dreamshaperxl", "flux", "custom", "grok"}:
        model = "custom"
    if model == "sdxl" and str(raw.get("image_model_checkpoint") or DEFAULT_SETTINGS["image_model_checkpoint"]).strip() == REALVISXL_CHECKPOINT:
        model = "realvisxl"
    quality_preset = str(raw.get("image_quality_preset") or DEFAULT_SETTINGS["image_quality_preset"]).strip().lower()
    if quality_preset not in IMAGE_QUALITY_PRESETS:
        quality_preset = "balanced"
    aspect_ratio = str(raw.get("image_aspect_ratio") or DEFAULT_SETTINGS["image_aspect_ratio"]).strip().lower()
    if aspect_ratio not in {"vertical", "horizontal"}:
        aspect_ratio = "vertical"
    preset = IMAGE_QUALITY_PRESETS[quality_preset]
    preset_size = preset[aspect_ratio]
    default_width, default_height = int(preset_size["width"]), int(preset_size["height"])
    try:
        width = int(raw.get("image_width") or default_width)
        height = int(raw.get("image_height") or default_height)
    except (TypeError, ValueError):
        width, height = default_width, default_height
    width, height = default_width, default_height
    if aspect_ratio == "horizontal" and height > width:
        width, height = max(width, height), min(width, height)
    if aspect_ratio == "vertical" and width > height:
        width, height = min(width, height), max(width, height)
    try:
        seed = int(raw.get("image_seed") or 0)
    except (TypeError, ValueError):
        seed = 0
    if seed <= 0:
        seed = int(time.time() * 1000) % 2147483647
    workflow_mode = str(raw.get("image_workflow_mode") or DEFAULT_SETTINGS["image_workflow_mode"]).strip().lower()
    if workflow_mode not in {"generated", "template", "disabled"}:
        workflow_mode = "generated"
    try:
        steps = int(raw.get("image_steps") or DEFAULT_SETTINGS["image_steps"])
    except (TypeError, ValueError):
        steps = int(DEFAULT_SETTINGS["image_steps"])
    try:
        cfg = float(raw.get("image_cfg") or DEFAULT_SETTINGS["image_cfg"])
    except (TypeError, ValueError):
        cfg = float(DEFAULT_SETTINGS["image_cfg"])
    steps = int(preset["steps"])
    cfg = float(preset["cfg"])
    sampler = str(preset["sampler"])
    scheduler = str(preset["scheduler"])
    return {
        "provider": provider,
        "model": model,
        "grok_model": str(raw.get("image_grok_model") or DEFAULT_SETTINGS["image_grok_model"]).strip() or GROK_IMAGE_MODEL,
        "quality_preset": quality_preset,
        "aspect_ratio": aspect_ratio,
        "width": max(64, min(4096, width)),
        "height": max(64, min(4096, height)),
        "style_preset": str(raw.get("image_style_preset") or DEFAULT_SETTINGS["image_style_preset"]).strip(),
        "comfyui_url": str(raw.get("image_comfyui_url") or DEFAULT_SETTINGS["image_comfyui_url"]).strip().rstrip("/"),
        "comfyui_path": str(raw.get("image_comfyui_path") or DEFAULT_SETTINGS["image_comfyui_path"]).strip(),
        "comfyui_python": str(raw.get("image_comfyui_python") or DEFAULT_SETTINGS["image_comfyui_python"]).strip(),
        "comfyui_launch_cmd": str(raw.get("image_comfyui_launch_cmd") or DEFAULT_SETTINGS["image_comfyui_launch_cmd"]).strip(),
        "comfyui_autostart": bool(raw.get("image_comfyui_autostart", DEFAULT_SETTINGS["image_comfyui_autostart"])),
        "workflow_mode": workflow_mode,
        "workflow_path": str(raw.get("image_workflow_path") or "").strip(),
        "model_checkpoint": str(raw.get("image_model_checkpoint") or DEFAULT_SETTINGS["image_model_checkpoint"] or REALVISXL_CHECKPOINT).strip(),
        "negative_preset": str(raw.get("image_negative_preset") or DEFAULT_SETTINGS["image_negative_preset"]).strip().lower(),
        "seed": seed,
        "exclude_people": bool(raw.get("image_exclude_people", DEFAULT_SETTINGS["image_exclude_people"])),
        "steps": max(1, min(150, steps)),
        "cfg": max(0.0, min(30.0, cfg)),
        "sampler": sampler,
        "scheduler": scheduler,
    }


def video_i2v_settings(project: dict[str, Any]) -> dict[str, Any]:
    raw = project.get("settings", {}) if isinstance(project.get("settings"), dict) else {}
    workflow_mode = str(raw.get("video_i2v_workflow_mode") or DEFAULT_SETTINGS["video_i2v_workflow_mode"]).strip().lower()
    if workflow_mode not in {"generated_svd", "generated_animatediff", "generated_hotshotxl", "generated_grok_imagine_video", "disabled"}:
        workflow_mode = "generated_svd"
    quality_preset = str(raw.get("video_i2v_quality_preset") or DEFAULT_SETTINGS["video_i2v_quality_preset"]).strip().lower()
    if quality_preset not in VIDEO_I2V_QUALITY_PRESETS:
        quality_preset = "balanced"
    preset = VIDEO_I2V_QUALITY_PRESETS[quality_preset]
    motion_style = str(raw.get("video_i2v_motion_style") or DEFAULT_SETTINGS["video_i2v_motion_style"]).strip().lower()
    if motion_style not in VIDEO_I2V_MOTION_STYLE_PRESETS:
        motion_style = "ambient_nature"
    style_preset = VIDEO_I2V_MOTION_STYLE_PRESETS[motion_style]
    def int_setting(key: str, min_value: int, max_value: int) -> int:
        raw_value = raw.get(key)
        try:
            value = int(raw_value) if raw_value not in (None, "") else int(preset.get(key.replace("video_i2v_", ""), DEFAULT_SETTINGS[key]))
        except (TypeError, ValueError):
            value = int(preset.get(key.replace("video_i2v_", ""), DEFAULT_SETTINGS[key]))
        return max(min_value, min(max_value, value))
    def float_setting(key: str, min_value: float, max_value: float) -> float:
        raw_value = raw.get(key)
        try:
            value = float(raw_value) if raw_value not in (None, "") else float(preset.get(key.replace("video_i2v_", ""), DEFAULT_SETTINGS[key]))
        except (TypeError, ValueError):
            value = float(preset.get(key.replace("video_i2v_", ""), DEFAULT_SETTINGS[key]))
        return max(min_value, min(max_value, value))
    frames = min(int_setting("video_i2v_frames", 2, 256), int(style_preset.get("max_frames") or 256))
    fps = min(int_setting("video_i2v_fps", 1, 60), int(style_preset.get("max_fps") or 60))
    motion_bucket_id = max(1, min(1023, int(style_preset.get("motion_bucket_id") or int_setting("video_i2v_motion_bucket_id", 1, 1023))))
    augmentation_level = max(0.0, min(1.0, float(style_preset.get("augmentation_level", float_setting("video_i2v_augmentation_level", 0.0, 1.0)))))
    cfg = max(0.0, min(30.0, float(style_preset.get("cfg", float_setting("video_i2v_cfg", 0.0, 30.0)))))
    steps = max(1, min(150, int_setting("video_i2v_steps", 1, 150) + int(style_preset.get("steps_delta") or 0)))
    try:
        target_duration_sec = float(raw.get("video_i2v_target_duration_sec") or DEFAULT_SETTINGS["video_i2v_target_duration_sec"])
    except (TypeError, ValueError):
        target_duration_sec = float(DEFAULT_SETTINGS["video_i2v_target_duration_sec"])
    target_duration_sec = max(2.0, min(60.0, target_duration_sec))
    try:
        grok_duration_sec = int(raw.get("video_i2v_grok_duration_sec") or DEFAULT_SETTINGS["video_i2v_grok_duration_sec"])
    except (TypeError, ValueError):
        grok_duration_sec = int(DEFAULT_SETTINGS["video_i2v_grok_duration_sec"])
    grok_duration_sec = max(1, min(30, grok_duration_sec))
    grok_resolution = str(raw.get("video_i2v_grok_resolution") or "").strip().lower()
    if not grok_resolution:
        grok_resolution = GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS.get(quality_preset, "480p")
    if grok_resolution not in GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS:
        grok_resolution = GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS.get(quality_preset, "480p")
    grok_aspect_ratio_mode = str(raw.get("video_i2v_grok_aspect_ratio_mode") or DEFAULT_SETTINGS["video_i2v_grok_aspect_ratio_mode"]).strip().lower()
    if grok_aspect_ratio_mode not in {"auto", "16:9", "9:16"}:
        grok_aspect_ratio_mode = "auto"
    grok_loop_postprocess = str(raw.get("video_i2v_grok_loop_postprocess") or DEFAULT_SETTINGS["video_i2v_grok_loop_postprocess"]).strip().lower()
    if grok_loop_postprocess not in {"off", "pingpong", "crossfade"}:
        grok_loop_postprocess = str(DEFAULT_SETTINGS["video_i2v_grok_loop_postprocess"])
    try:
        grok_crossfade_sec = float(raw.get("video_i2v_grok_crossfade_sec") or DEFAULT_SETTINGS["video_i2v_grok_crossfade_sec"])
    except (TypeError, ValueError):
        grok_crossfade_sec = float(DEFAULT_SETTINGS["video_i2v_grok_crossfade_sec"])
    grok_crossfade_sec = max(0.1, min(2.0, grok_crossfade_sec))
    pingpong = bool(raw.get("video_i2v_pingpong", DEFAULT_SETTINGS["video_i2v_pingpong"]))
    base_output_frames = max(1, frames * 2 - 2) if pingpong and frames > 1 else max(1, frames)
    base_duration = base_output_frames / float(max(1, fps))
    loop_count = max(0, min(30, int(max(1, round(target_duration_sec / max(0.001, base_duration)))) - 1))
    return {
        "enabled": bool(raw.get("video_i2v_enabled", DEFAULT_SETTINGS["video_i2v_enabled"])),
        "quality_preset": quality_preset,
        "motion_style": motion_style,
        "workflow_mode": workflow_mode,
        "model_checkpoint": str(raw.get("video_i2v_model_checkpoint") or DEFAULT_SETTINGS["video_i2v_model_checkpoint"]).strip(),
        "grok_model": str(raw.get("video_i2v_grok_model") or DEFAULT_SETTINGS["video_i2v_grok_model"]).strip() or GROK_IMAGINE_VIDEO_MODEL,
        "grok_duration_sec": grok_duration_sec,
        "grok_resolution": grok_resolution,
        "grok_aspect_ratio_mode": grok_aspect_ratio_mode,
        "grok_loop_postprocess": grok_loop_postprocess,
        "grok_crossfade_sec": grok_crossfade_sec,
        "grok_resolution_options": sorted(GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS),
        "frames": frames,
        "fps": fps,
        "motion_bucket_id": motion_bucket_id,
        "augmentation_level": augmentation_level,
        "min_cfg": float_setting("video_i2v_min_cfg", 0.0, 30.0),
        "cfg": cfg,
        "steps": steps,
        "sampler": str(preset.get("sampler") or DEFAULT_SETTINGS["video_i2v_sampler"]).strip(),
        "scheduler": str(preset.get("scheduler") or DEFAULT_SETTINGS["video_i2v_scheduler"]).strip(),
        "pingpong": pingpong,
        "target_duration_sec": target_duration_sec,
        "loop_count": loop_count,
        "output_fps": fps,
    }


def video_i2v_backend_label(video_settings: dict[str, Any] | None = None) -> str:
    mode = str((video_settings or {}).get("workflow_mode") or DEFAULT_SETTINGS["video_i2v_workflow_mode"]).strip().lower()
    if mode == "generated_grok_imagine_video":
        return "Grok Imagine Video"
    if mode == "generated_animatediff":
        return "AnimateDiff SD1.5"
    if mode == "generated_hotshotxl":
        return "HotshotXL / AnimateDiff SDXL"
    return "SVD/SVD-XT"


def comfyui_url(settings: dict[str, Any]) -> str:
    return str(settings.get("comfyui_url") or DEFAULT_SETTINGS["image_comfyui_url"]).strip().rstrip("/")


def http_json_request(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 10.0) -> Any:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def comfyui_health(settings: dict[str, Any]) -> dict[str, Any]:
    base_url = comfyui_url(settings)
    last_error = ""
    for endpoint in ("/system_stats", "/queue"):
        try:
            data = http_json_request(f"{base_url}{endpoint}", timeout=2.0)
            return {"running": True, "url": base_url, "endpoint": endpoint, "data": data, "error": ""}
        except Exception as exc:
            last_error = str(exc)
    return {"running": False, "url": base_url, "endpoint": "", "data": None, "error": last_error}


def comfyui_model_check(settings: dict[str, Any]) -> dict[str, str]:
    checkpoint = str(settings.get("model_checkpoint") or "").strip()
    if not checkpoint:
        return {"model_checkpoint": "", "model_check": "unknown", "note": "Checkpoint is not configured"}
    comfy_root = resolve_user_path(str(settings.get("comfyui_path") or DEFAULT_SETTINGS["image_comfyui_path"]))
    if not comfy_root:
        return {"model_checkpoint": checkpoint, "model_check": "configured", "note": "Checkpoint name configured; path not resolved"}
    exact_path = comfy_root / "ComfyUI" / "models" / "checkpoints" / checkpoint
    alt_path = comfy_root / "models" / "checkpoints" / checkpoint
    if exact_path.exists() or alt_path.exists():
        return {"model_checkpoint": checkpoint, "model_check": "configured", "note": "Checkpoint exact path exists"}
    return {"model_checkpoint": checkpoint, "model_check": "missing_exact_path", "note": "Checkpoint configured but exact expected path was not found; no directory scan performed"}


def comfyui_models_dir(settings: dict[str, Any], subdir: str) -> Path | None:
    comfy_root = resolve_user_path(str(settings.get("comfyui_path") or DEFAULT_SETTINGS["image_comfyui_path"]))
    if not comfy_root:
        return None
    for candidate in (comfy_root / "ComfyUI" / "models" / subdir, comfy_root / "models" / subdir):
        if candidate.exists():
            return candidate
    return comfy_root / "ComfyUI" / "models" / subdir


def comfyui_model_files(settings: dict[str, Any], subdir: str, suffixes: tuple[str, ...]) -> list[str]:
    models_dir = comfyui_models_dir(settings, subdir)
    if not models_dir or not models_dir.exists():
        return []
    return sorted([str(path.relative_to(models_dir)).replace("\\", "/") for path in models_dir.rglob("*") if path.is_file() and path.suffix.lower() in suffixes], key=str.lower)


def looks_like_sd15_checkpoint(name: str) -> bool:
    lower = Path(str(name)).name.lower()
    if any(token in lower for token in ("xl", "sdxl", "svd", "stable-video", "video", "flux")):
        return False
    return any(token in lower for token in ("sd15", "sd1.5", "sd_1.5", "v1-5", "v1_5", "dreamshaper", "realisticvision", "deliberate", "epicrealism", "majicmix", "revanimated"))


def find_sd15_checkpoint(settings: dict[str, Any]) -> str:
    checkpoints = comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt"))
    configured = str(settings.get("animatediff_sd15_checkpoint") or os.environ.get("XTTS_ANIMATEDIFF_SD15_CHECKPOINT") or "").strip()
    if configured and configured in checkpoints:
        return configured
    return next((checkpoint for checkpoint in checkpoints if looks_like_sd15_checkpoint(checkpoint)), "")


def find_sdxl_checkpoint(settings: dict[str, Any]) -> str:
    checkpoints = comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt"))
    configured = str(settings.get("model_checkpoint") or os.environ.get("XTTS_ANIMATEDIFF_SDXL_CHECKPOINT") or REALVISXL_CHECKPOINT).strip()
    if configured and configured in checkpoints:
        return configured
    return next((checkpoint for checkpoint in checkpoints if "xl" in Path(str(checkpoint)).name.lower() or "sdxl" in Path(str(checkpoint)).name.lower()), "")


def find_sdxl_motion_model(settings: dict[str, Any]) -> str:
    motion_models = comfyui_model_files(settings, "animatediff_models", (".safetensors", ".ckpt", ".pt", ".pth"))
    configured = str(os.environ.get(ANIMATEDIFF_SDXL_ENV_MODEL) or "").strip()
    if configured and configured in motion_models:
        return configured
    for candidate in ANIMATEDIFF_SDXL_MODEL_CANDIDATES:
        if candidate in motion_models:
            return candidate
    return next((model for model in motion_models if any(token in Path(str(model)).name.lower() for token in ("hotshot", "hsxl", "sdxl", "animatediffxl", "adxl"))), "")


def animatediff_node_diagnostics(settings: dict[str, Any]) -> dict[str, Any]:
    required_nodes = ["CheckpointLoaderSimple", "LoadImage", "ImageScale", "RepeatImageBatch", "VAEEncode", "CLIPTextEncode", "KSampler", "VAEDecode", "VHS_VideoCombine", "ADE_LoadAnimateDiffModel", "ADE_ApplyAnimateDiffModelSimple", "ADE_UseEvolvedSampling"]
    try:
        object_info = http_json_request(f"{comfyui_url(settings)}/object_info", timeout=5.0)
        return {"object_info_available": True, "object_info_error": "", "required_nodes": required_nodes, "missing_nodes": [node for node in required_nodes if node not in object_info], "node_inputs": {node: object_info.get(node, {}).get("input") for node in required_nodes if isinstance(object_info.get(node), dict)}}
    except Exception as exc:
        return {"object_info_available": False, "object_info_error": str(exc), "required_nodes": required_nodes, "missing_nodes": required_nodes, "node_inputs": {}}


def animatediff_environment_diagnostics(settings: dict[str, Any]) -> dict[str, Any]:
    checkpoints = comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt"))
    motion_models = comfyui_model_files(settings, "animatediff_models", (".safetensors", ".ckpt", ".pt", ".pth"))
    selected_sd15 = find_sd15_checkpoint(settings)
    selected_motion = ANIMATEDIFF_MOTION_MODEL if ANIMATEDIFF_MOTION_MODEL in motion_models else ""
    nodes = animatediff_node_diagnostics(settings)
    blockers: list[str] = []
    if nodes.get("object_info_available") and nodes.get("missing_nodes"):
        blockers.append(f"Missing ComfyUI node class(es): {', '.join(nodes['missing_nodes'])}")
    elif not nodes.get("object_info_available"):
        blockers.append(f"ComfyUI /object_info unavailable: {nodes.get('object_info_error') or 'unknown error'}")
    if not selected_motion:
        blockers.append(f"Missing AnimateDiff SD1.5 motion model {ANIMATEDIFF_MOTION_MODEL} in ComfyUI/models/animatediff_models")
    if not selected_sd15:
        blockers.append(f"No compatible SD1.5 checkpoint detected in ComfyUI/models/checkpoints. Installed checkpoints are: {', '.join(checkpoints) or 'none'}. Do not use {REALVISXL_CHECKPOINT} with {ANIMATEDIFF_MOTION_MODEL}; RealVisXL is SDXL.")
    return {"ready": not blockers, "blockers": blockers, "selected_sd15_checkpoint": selected_sd15, "selected_motion_model": selected_motion, "checkpoints": checkpoints, "motion_models": motion_models, "nodes": nodes}


def animatediff_sdxl_node_diagnostics(settings: dict[str, Any]) -> dict[str, Any]:
    required_nodes = ["CheckpointLoaderSimple", "LoadImage", "ImageScale", "RepeatImageBatch", "VAEEncode", "CLIPTextEncode", "KSampler", "VAEDecode", "VHS_VideoCombine", "ADE_LoadAnimateDiffModel", "ADE_ApplyAnimateDiffModelSimple", "ADE_UseEvolvedSampling"]
    optional_nodes = ["ADE_StandardUniformContextOptions", "ADE_LoopedUniformContextOptions", "ADE_PerBlock_SDXL_LowLevel", "ADE_PerBlock_SDXL_MidLevel"]
    try:
        object_info = http_json_request(f"{comfyui_url(settings)}/object_info", timeout=5.0)
        return {
            "object_info_available": True,
            "object_info_error": "",
            "required_nodes": required_nodes,
            "optional_nodes": optional_nodes,
            "missing_nodes": [node for node in required_nodes if node not in object_info],
            "missing_optional_nodes": [node for node in optional_nodes if node not in object_info],
            "node_inputs": {node: object_info.get(node, {}).get("input") for node in required_nodes + optional_nodes if isinstance(object_info.get(node), dict)},
        }
    except Exception as exc:
        return {"object_info_available": False, "object_info_error": str(exc), "required_nodes": required_nodes, "optional_nodes": optional_nodes, "missing_nodes": required_nodes, "missing_optional_nodes": optional_nodes, "node_inputs": {}}


def animatediff_sdxl_environment_diagnostics(settings: dict[str, Any]) -> dict[str, Any]:
    checkpoints = comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt"))
    motion_models = comfyui_model_files(settings, "animatediff_models", (".safetensors", ".ckpt", ".pt", ".pth"))
    selected_sdxl = find_sdxl_checkpoint(settings)
    selected_motion = find_sdxl_motion_model(settings)
    nodes = animatediff_sdxl_node_diagnostics(settings)
    blockers: list[str] = []
    warnings: list[str] = []
    if nodes.get("object_info_available") and nodes.get("missing_nodes"):
        blockers.append(f"Missing ComfyUI node class(es): {', '.join(nodes['missing_nodes'])}")
    elif not nodes.get("object_info_available"):
        blockers.append(f"ComfyUI /object_info unavailable: {nodes.get('object_info_error') or 'unknown error'}")
    if not selected_sdxl:
        blockers.append(f"No SDXL checkpoint detected in ComfyUI/models/checkpoints. Expected {REALVISXL_CHECKPOINT} or another SDXL checkpoint.")
    if not selected_motion:
        blockers.append("No SDXL-compatible AnimateDiff/HotshotXL motion model detected in ComfyUI/models/animatediff_models. Expected a file such as hsxl_temporal_layers.safetensors, hotshotxl.safetensors, or mm_sdxl_v10_beta.safetensors; set XTTS_ANIMATEDIFF_SDXL_MOTION_MODEL if using a different filename.")
    if selected_motion and selected_motion == ANIMATEDIFF_MOTION_MODEL:
        blockers.append(f"Detected only the SD1.5 motion model {ANIMATEDIFF_MOTION_MODEL}; it is not compatible with SDXL/RealVisXL.")
    if nodes.get("missing_optional_nodes"):
        warnings.append(f"Optional SDXL/context helper nodes unavailable: {', '.join(nodes['missing_optional_nodes'])}; a minimal graph may still run, but long clips or fine control can be weaker.")
    warnings.append("This path is experimental and usually needs substantially more VRAM than SVD-XT or SD1.5 AnimateDiff; start with Fast quality and short clips.")
    return {
        "ready": not blockers,
        "implemented": bool(not blockers),
        "blockers": blockers,
        "warnings": warnings,
        "selected_sdxl_checkpoint": selected_sdxl,
        "selected_motion_model": selected_motion,
        "motion_model_env": ANIMATEDIFF_SDXL_ENV_MODEL,
        "known_motion_model_candidates": list(ANIMATEDIFF_SDXL_MODEL_CANDIDATES),
        "checkpoints": checkpoints,
        "motion_models": motion_models,
        "nodes": nodes,
    }


def grok_imagine_video_diagnostics(project: dict[str, Any]) -> dict[str, Any]:
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    settings = image_settings(project)
    video_settings = video_i2v_settings(project)
    groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
    sample_group = next((group for group in groups if isinstance(group, dict)), {})
    sample_image_meta = sample_group.get("image") if isinstance(sample_group.get("image"), dict) else {}
    return {
        "ready": bool(resolve_xai_api_key(project, pid)),
        "implemented": True,
        "api_key_configured": bool(resolve_xai_api_key(project, pid)),
        "api_key_hint": xai_api_key_hint(pid),
        "model": video_settings.get("grok_model") or GROK_IMAGINE_VIDEO_MODEL,
        "endpoint": "/v1/videos/generations",
        "poll_endpoint": "/v1/videos/{request_id}",
        "docs": {
            "video_generation": "https://docs.x.ai/developers/model-capabilities/video/generation",
            "image_to_video": "https://docs.x.ai/developers/model-capabilities/video/image-to-video",
        },
        "defaults": {
            "duration_sec": video_settings.get("grok_duration_sec"),
            "resolution": video_settings.get("grok_resolution"),
            "aspect_ratio_mode": video_settings.get("grok_aspect_ratio_mode"),
            "loop_postprocess": video_settings.get("grok_loop_postprocess"),
            "crossfade_sec": video_settings.get("grok_crossfade_sec"),
            "poll_timeout_sec": XAI_IMAGINE_VIDEO_POLL_TIMEOUT_SECONDS,
            "poll_interval_sec": XAI_IMAGINE_VIDEO_POLL_INTERVAL_SECONDS,
        },
        "quality_options": {
            "presets": GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS,
            "confirmed_resolutions": sorted(GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS),
            "note": "Docs/examples confirm 480p and 720p; 1080p is intentionally not exposed until official docs confirm it.",
        },
        "aspect_ratio_behavior": {
            "auto": "16:9 for landscape/source width >= height; 9:16 for portrait/source height > width; square/unknown defaults to 16:9.",
            "confirmed_aspect_ratios": sorted(GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS),
            "sample_resolved_aspect_ratio": source_image_aspect_ratio(settings, sample_image_meta, mode=str(video_settings.get("grok_aspect_ratio_mode") or "auto")),
        },
        "blockers": [] if resolve_xai_api_key(project, pid) else ["Grok/xAI API key is not configured; set a project key in XTTS Studio settings or XAI_API_KEY."],
        "warnings": [
            "This backend calls a paid hosted xAI video endpoint when generation is queued.",
            "Generated xAI URLs are temporary; XTTS Studio downloads the result into project video storage immediately after polling returns done.",
        ],
    }


def animatediff_target_dimensions(settings: dict[str, Any], image_meta: dict[str, Any] | None = None) -> tuple[int, int]:
    width, height = svd_source_dimensions(settings, image_meta)
    return (512, 768) if height >= width else (768, 512)


def format_animatediff_prompt(group: dict[str, Any]) -> dict[str, str]:
    positive = append_unique_csv_terms(truncate_text(group.get("animation_positive_prompt") or group.get("visual_prompt") or group.get("summary"), 1200), "locked camera, static camera, stable composition, subtle natural ambient motion only, slow peaceful loop", limit=1400)
    negative = append_unique_csv_terms(truncate_text(group.get("animation_negative_prompt") or group.get("negative_prompt"), 900), "camera pan, camera zoom, camera orbit, dolly, camera shake, whole image moving, drifting frame, fast action, cuts, scene change, morphing, warping, new objects, text, subtitles, watermark, flicker, jitter", limit=1100)
    return {"positive_prompt": positive, "negative_prompt": negative}


def compile_animatediff_i2v_workflow(settings: dict[str, Any], video_settings: dict[str, Any], group: dict[str, Any], source_image_path: Path, output_prefix: str, sd15_checkpoint: str, motion_model: str, image_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    width, height = animatediff_target_dimensions(settings, image_meta)
    frames = max(2, min(64, int(video_settings.get("frames") or 16)))
    fps = max(1, min(24, int(video_settings.get("fps") or 8)))
    prompt = format_animatediff_prompt(group)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": sd15_checkpoint}},
        "2": {"class_type": "LoadImage", "inputs": {"image": str(source_image_path)}},
        "3": {"class_type": "ImageScale", "inputs": {"image": ["2", 0], "upscale_method": "lanczos", "width": width, "height": height, "crop": "center"}},
        "4": {"class_type": "RepeatImageBatch", "inputs": {"image": ["3", 0], "amount": frames}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt["positive_prompt"], "clip": ["1", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt["negative_prompt"], "clip": ["1", 1]}},
        "8": {"class_type": "ADE_LoadAnimateDiffModel", "inputs": {"model_name": motion_model}},
        "9": {"class_type": "ADE_ApplyAnimateDiffModelSimple", "inputs": {"motion_model": ["8", 0]}},
        "10": {"class_type": "ADE_UseEvolvedSampling", "inputs": {"model": ["1", 0], "beta_schedule": "autoselect", "m_models": ["9", 0]}},
        "11": {"class_type": "KSampler", "inputs": {"seed": int(settings.get("seed") or 1), "steps": int(video_settings.get("steps") or 20), "cfg": float(video_settings.get("cfg") or 7.0), "sampler_name": str(video_settings.get("sampler") or "euler"), "scheduler": str(video_settings.get("scheduler") or "normal"), "denoise": 0.72, "model": ["10", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["1", 2]}},
        "13": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["12", 0], "frame_rate": fps, "loop_count": max(0, min(30, int(video_settings.get("loop_count") or 0))), "filename_prefix": output_prefix, "format": "video/h264-mp4", "pingpong": bool(video_settings.get("pingpong", True)), "save_output": True}},
    }


def animatediff_sdxl_target_dimensions(settings: dict[str, Any], image_meta: dict[str, Any] | None = None) -> tuple[int, int]:
    width, height = svd_source_dimensions(settings, image_meta)
    if height >= width:
        return (768, 1024)
    return (1024, 768)


def compile_animatediff_sdxl_i2v_workflow(settings: dict[str, Any], video_settings: dict[str, Any], group: dict[str, Any], source_image_path: Path, output_prefix: str, sdxl_checkpoint: str, motion_model: str, image_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    width, height = animatediff_sdxl_target_dimensions(settings, image_meta)
    frames = max(2, min(32, int(video_settings.get("frames") or 16)))
    fps = max(1, min(16, int(video_settings.get("fps") or 8)))
    prompt = format_animatediff_prompt(group)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": sdxl_checkpoint}},
        "2": {"class_type": "LoadImage", "inputs": {"image": str(source_image_path)}},
        "3": {"class_type": "ImageScale", "inputs": {"image": ["2", 0], "upscale_method": "lanczos", "width": width, "height": height, "crop": "center"}},
        "4": {"class_type": "RepeatImageBatch", "inputs": {"image": ["3", 0], "amount": frames}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt["positive_prompt"], "clip": ["1", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt["negative_prompt"], "clip": ["1", 1]}},
        "8": {"class_type": "ADE_LoadAnimateDiffModel", "inputs": {"model_name": motion_model}},
        "9": {"class_type": "ADE_ApplyAnimateDiffModelSimple", "inputs": {"motion_model": ["8", 0]}},
        "10": {"class_type": "ADE_UseEvolvedSampling", "inputs": {"model": ["1", 0], "beta_schedule": "autoselect", "m_models": ["9", 0]}},
        "11": {"class_type": "KSampler", "inputs": {"seed": int(settings.get("seed") or 1), "steps": int(video_settings.get("steps") or 16), "cfg": min(6.0, float(video_settings.get("cfg") or 5.0)), "sampler_name": str(video_settings.get("sampler") or "euler"), "scheduler": str(video_settings.get("scheduler") or "normal"), "denoise": 0.68, "model": ["10", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["1", 2]}},
        "13": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["12", 0], "frame_rate": fps, "loop_count": max(0, min(30, int(video_settings.get("loop_count") or 0))), "filename_prefix": output_prefix, "format": "video/h264-mp4", "pingpong": bool(video_settings.get("pingpong", True)), "save_output": True}},
    }


def comfyui_default_launch_candidates(settings: dict[str, Any]) -> dict[str, Any]:
    configured_path = resolve_user_path(str(settings.get("comfyui_path") or DEFAULT_SETTINGS["image_comfyui_path"]))
    checked: list[str] = []
    if not configured_path:
        return {"candidate": None, "checked": checked, "note": "ComfyUI path is not configured"}
    portable_root = configured_path

    nvidia_bat = portable_root / "run_nvidia_gpu.bat"
    checked.append(rel_path(nvidia_bat))
    if nvidia_bat.exists():
        return {
            "candidate": {"kind": "bat", "path": str(nvidia_bat), "cwd": str(portable_root), "label": rel_path(nvidia_bat)},
            "checked": checked,
            "note": f"Default launch candidate found: {rel_path(nvidia_bat)}",
        }

    cpu_bat = portable_root / "run_cpu.bat"
    checked.append(rel_path(cpu_bat))
    if cpu_bat.exists():
        return {
            "candidate": {"kind": "bat", "path": str(cpu_bat), "cwd": str(portable_root), "label": rel_path(cpu_bat)},
            "checked": checked,
            "note": f"Default launch candidate found: {rel_path(cpu_bat)}",
        }

    embedded_python = portable_root / "python_embeded" / "python.exe"
    main_py = portable_root / "ComfyUI" / "main.py"
    checked.extend([rel_path(embedded_python), rel_path(main_py)])
    if embedded_python.exists() and main_py.exists():
        comfyui_cwd = portable_root / "ComfyUI"
        return {
            "candidate": {
                "kind": "python",
                "python": str(embedded_python),
                "main_py": str(main_py),
                "cwd": str(comfyui_cwd),
                "label": f"{rel_path(embedded_python)} + {rel_path(main_py)}",
            },
            "checked": checked,
            "note": f"Default launch candidate found: {rel_path(embedded_python)} + {rel_path(main_py)}",
        }

    return {"candidate": None, "checked": checked, "note": f"No default ComfyUI launch candidate found; checked: {', '.join(checked)}"}


def launch_comfyui_candidate(candidate: dict[str, Any]) -> None:
    kind = str(candidate.get("kind") or "")
    cwd = str(candidate.get("cwd") or ROOT)
    if kind == "bat":
        bat_path = str(candidate.get("path") or "")
        subprocess.Popen(f'start "ComfyUI" "{bat_path}"', cwd=cwd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if kind == "python":
        python_path = str(candidate.get("python") or "")
        main_py = str(candidate.get("main_py") or "")
        subprocess.Popen([python_path, main_py, "--listen", "127.0.0.1", "--port", "8188"], cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    raise RuntimeError(f"Unsupported ComfyUI launch candidate type: {kind or 'unknown'}")


def start_comfyui_if_needed(settings: dict[str, Any]) -> dict[str, Any]:
    health = comfyui_health(settings)
    if health.get("running"):
        return health | {"started": False, "note": "ComfyUI is already running"}
    if not settings.get("comfyui_autostart"):
        return health | {"started": False, "note": "Autostart is disabled"}
    launch_cmd = str(settings.get("comfyui_launch_cmd") or "").strip()
    configured_path = resolve_user_path(str(settings.get("comfyui_path") or DEFAULT_SETTINGS["image_comfyui_path"]))
    cwd = configured_path if configured_path and configured_path.exists() else ROOT
    if launch_cmd:
        subprocess.Popen(launch_cmd, cwd=str(cwd), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return health | {"started": True, "note": f"ComfyUI launch command started with cwd={rel_path(cwd)}"}
    candidate_info = comfyui_default_launch_candidates(settings)
    candidate = candidate_info.get("candidate")
    if not isinstance(candidate, dict):
        return health | {"started": False, "note": candidate_info.get("note") or "No launch command or default ComfyUI launch candidate found", "checked_paths": candidate_info.get("checked", [])}
    launch_comfyui_candidate(candidate)
    return health | {"started": True, "note": f"ComfyUI default launch started: {candidate.get('label')}", "checked_paths": candidate_info.get("checked", []), "default_launch_candidate": candidate.get("label")}


def wait_for_comfyui(settings: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
    start_info = start_comfyui_if_needed(settings)
    deadline = time.time() + max(0.1, timeout)
    last = comfyui_health(settings)
    while time.time() < deadline:
        last = comfyui_health(settings)
        if last.get("running"):
            return last
        time.sleep(1.0)
    start_note = str(start_info.get("note") or "")
    checked = start_info.get("checked_paths") if isinstance(start_info.get("checked_paths"), list) else []
    detail = last.get("error") or "timeout"
    if start_note:
        detail = f"{detail}; {start_note}"
    if checked:
        detail = f"{detail}; checked paths: {', '.join(str(item) for item in checked)}"
    raise RuntimeError(f"ComfyUI is not reachable at {comfyui_url(settings)}: {detail}")


def comfyui_status(settings: dict[str, Any]) -> dict[str, Any]:
    health = comfyui_health(settings)
    model_info = comfyui_model_check(settings)
    default_launch = comfyui_default_launch_candidates(settings)
    return {
        "running": bool(health.get("running")),
        "url": comfyui_url(settings),
        "autostart_enabled": bool(settings.get("comfyui_autostart")),
        "launch_command_configured": bool(str(settings.get("comfyui_launch_cmd") or "").strip()),
        "default_launch_candidate": (default_launch.get("candidate") or {}).get("label") if isinstance(default_launch.get("candidate"), dict) else "",
        "default_launch_checked_paths": default_launch.get("checked", []),
        "workflow_mode": settings.get("workflow_mode"),
        "model": settings.get("model"),
        "model_checkpoint": model_info.get("model_checkpoint", ""),
        "model_check": model_info.get("model_check", "unknown"),
        "note": model_info.get("note") if health.get("running") else (health.get("error") or default_launch.get("note") or model_info.get("note") or "ComfyUI is not reachable"),
    }


def compile_sdxl_txt2img_workflow(settings: dict[str, Any], prompt_bundle: dict[str, str], output_prefix: str) -> dict[str, Any]:
    checkpoint = str(settings.get("model_checkpoint") or "").strip()
    if not checkpoint:
        raise RuntimeError("SDXL checkpoint is not configured; set image_model_checkpoint to a .safetensors filename")
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt_bundle.get("positive_prompt", ""), "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt_bundle.get("negative_prompt", ""), "clip": ["1", 1]},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": int(settings.get("width") or 1024),
                "height": int(settings.get("height") or 1024),
                "batch_size": 1,
            },
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": int(settings.get("seed") or 1),
                "steps": int(settings.get("steps") or DEFAULT_SETTINGS["image_steps"]),
                "cfg": float(settings.get("cfg") or DEFAULT_SETTINGS["image_cfg"]),
                "sampler_name": str(settings.get("sampler") or DEFAULT_SETTINGS["image_sampler"]),
                "scheduler": str(settings.get("scheduler") or DEFAULT_SETTINGS["image_scheduler"]),
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": output_prefix, "images": ["6", 0]},
        },
    }


def comfyui_submit_prompt(settings: dict[str, Any], workflow: dict[str, Any]) -> str:
    client_id = f"xtts-studio-{uuid.uuid4().hex[:12]}"
    response = http_json_request(f"{comfyui_url(settings)}/prompt", method="POST", payload={"prompt": workflow, "client_id": client_id}, timeout=20.0)
    prompt_id = str(response.get("prompt_id") or "") if isinstance(response, dict) else ""
    if not prompt_id:
        raise RuntimeError(f"ComfyUI /prompt did not return prompt_id: {truncate_text(response, 500)}")
    return prompt_id


def comfyui_wait_history(settings: dict[str, Any], prompt_id: str, timeout: float = 240.0) -> dict[str, Any]:
    wait_timeout = max(1.0, float(timeout))
    started_at = time.time()
    deadline = started_at + wait_timeout
    last_error = ""
    while time.time() < deadline:
        try:
            history = http_json_request(f"{comfyui_url(settings)}/history/{urllib.parse.quote(prompt_id)}", timeout=10.0)
            item = history.get(prompt_id) if isinstance(history, dict) else None
            if isinstance(item, dict):
                status = item.get("status") if isinstance(item.get("status"), dict) else {}
                if status.get("status_str") == "error" or status.get("completed") is False and item.get("outputs"):
                    raise RuntimeError(f"ComfyUI prompt failed: {truncate_text(status, 700)}")
                if item.get("outputs"):
                    return item
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1.0)
    elapsed = time.time() - started_at
    raise RuntimeError(
        f"Timed out waiting {elapsed:.0f}s/{wait_timeout:.0f}s for ComfyUI prompt {prompt_id}: "
        f"{last_error or 'no history output'}"
    )


def comfyui_first_output_image(history_item: dict[str, Any]) -> dict[str, str]:
    outputs = history_item.get("outputs") if isinstance(history_item.get("outputs"), dict) else {}
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        images = output.get("images") if isinstance(output.get("images"), list) else []
        for image in images:
            if isinstance(image, dict) and image.get("filename"):
                return {
                    "filename": str(image.get("filename") or ""),
                    "subfolder": str(image.get("subfolder") or ""),
                    "type": str(image.get("type") or "output"),
                }
    raise RuntimeError("ComfyUI history contains no output images")


def comfyui_first_output_video(history_item: dict[str, Any]) -> dict[str, str]:
    outputs = history_item.get("outputs") if isinstance(history_item.get("outputs"), dict) else {}
    candidates: list[dict[str, str]] = []

    def collect_item(item: Any) -> None:
        if not isinstance(item, dict):
            return
        filename = str(item.get("filename") or item.get("file") or item.get("name") or "")
        if not filename:
            url = str(item.get("url") or "")
            parsed_path = urllib.parse.urlparse(url).path if url else ""
            filename = Path(urllib.parse.unquote(parsed_path)).name if parsed_path else ""
        if not filename or not filename.lower().endswith((".mp4", ".webm", ".gif")):
            return
        candidates.append({
            "filename": filename,
            "subfolder": str(item.get("subfolder") or ""),
            "type": str(item.get("type") or "output"),
        })

    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        for key in ("gifs", "videos", "animated", "video", "files", "outputs"):
            items = output.get(key) if isinstance(output.get(key), list) else []
            for item in items:
                collect_item(item)
        images = output.get("images") if isinstance(output.get("images"), list) else []
        for image in images:
            collect_item(image)
        for value in output.values():
            if isinstance(value, dict):
                collect_item(value)
            elif isinstance(value, list):
                for item in value:
                    collect_item(item)
    if candidates:
        candidates.sort(key=lambda item: 0 if item["filename"].lower().endswith(".mp4") else 1)
        return candidates[0]
    output_keys = sorted({str(key) for output in outputs.values() if isinstance(output, dict) for key in output.keys()})
    raise RuntimeError(f"ComfyUI history contains no output video; output keys: {', '.join(output_keys) or 'none'}")


def comfyui_download_image(settings: dict[str, Any], image_info: dict[str, str], out_path: Path) -> None:
    query = urllib.parse.urlencode({
        "filename": image_info.get("filename", ""),
        "subfolder": image_info.get("subfolder", ""),
        "type": image_info.get("type", "output"),
    })
    with urllib.request.urlopen(f"{comfyui_url(settings)}/view?{query}", timeout=60.0) as response:
        data = response.read()
    if not data:
        raise RuntimeError("ComfyUI returned an empty image")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)


def comfyui_download_output(settings: dict[str, Any], output_info: dict[str, str], out_path: Path) -> None:
    query = urllib.parse.urlencode({
        "filename": output_info.get("filename", ""),
        "subfolder": output_info.get("subfolder", ""),
        "type": output_info.get("type", "output"),
    })
    with urllib.request.urlopen(f"{comfyui_url(settings)}/view?{query}", timeout=120.0) as response:
        data = response.read()
    if not data:
        raise RuntimeError("ComfyUI returned an empty output")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)


def comfyui_output_dir(settings: dict[str, Any]) -> Path | None:
    comfy_root = resolve_user_path(str(settings.get("comfyui_path") or DEFAULT_SETTINGS["image_comfyui_path"]))
    if not comfy_root:
        return None
    for candidate in (comfy_root / "ComfyUI" / "output", comfy_root / "output"):
        if candidate.exists():
            return candidate
    return None


def comfyui_newest_video_by_prefix(settings: dict[str, Any], output_prefix: str, since: float = 0.0) -> Path | None:
    output_dir = comfyui_output_dir(settings)
    if not output_dir or not output_prefix:
        return None
    matches: list[Path] = []
    for suffix in ("*.mp4", "*.webm", "*.gif"):
        matches.extend(output_dir.rglob(f"{output_prefix}*{suffix[1:]}"))
    fresh = [path for path in matches if path.is_file() and path.stat().st_mtime >= since - 2.0]
    return max(fresh or matches, key=lambda path: path.stat().st_mtime, default=None)


def copy_comfyui_prefix_video_to_project(project: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], group: dict[str, Any], output_prefix: str, source: Path, prompt_id: str = "", model_name: str | None = None, model_checkpoint: str | None = None, motion_model: str = "") -> dict[str, Any]:
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    out_dir = project_videos_dir(pid)
    source_suffix = source.suffix.lower()
    suffix = source_suffix if source_suffix in {".mp4", ".webm", ".gif"} else ".mp4"
    token = prompt_id[:10] if prompt_id else "recovered"
    out = out_dir / f"{output_prefix}_{token}{suffix}"
    if source.resolve() != out.resolve():
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, out)
    image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
    source_path = resolve_user_path(image_meta.get("path")) if image_meta.get("path") else None
    width, height = svd_source_dimensions(settings, image_meta)
    frames = int(video_settings.get("frames") or 0)
    fps = int(video_settings.get("fps") or 0)
    pingpong = bool(video_settings.get("pingpong", True))
    loop_count = max(0, int(video_settings.get("loop_count") or 0))
    output_fps = max(1, int(video_settings.get("output_fps") or fps or 1))
    single_loop_frames = max(0, frames * 2 - 2) if pingpong and frames > 1 else frames
    output_frames = single_loop_frames * (loop_count + 1)
    duration_sec = round(output_frames / float(output_fps), 3) if output_fps > 0 and output_frames > 0 else 0.0
    path = rel_path(out)
    now = time.time()
    return {
        "status": "ready",
        "provider": "comfyui",
        "model": model_name or ("svd_xt" if "xt" in str(video_settings.get("model_checkpoint") or "").lower() else "svd"),
        "model_checkpoint": model_checkpoint or video_settings.get("model_checkpoint", ""),
        "motion_model": motion_model,
        "motion_style": str(video_settings.get("motion_style") or ""),
        "width": width,
        "height": height,
        "seed": int(settings.get("seed") or 0),
        "frames": frames,
        "fps": fps,
        "output_fps": output_fps,
        "output_frames": output_frames,
        "loop_count": loop_count,
        "target_duration_sec": float(video_settings.get("target_duration_sec") or 0.0),
        "duration_sec": duration_sec,
        "loop": True,
        "pingpong": pingpong,
        "motion_bucket_id": int(video_settings.get("motion_bucket_id") or 0),
        "augmentation_level": float(video_settings.get("augmentation_level") or 0.0),
        "min_cfg": float(video_settings.get("min_cfg") or 0.0),
        "cfg": float(video_settings.get("cfg") or 0.0),
        "steps": int(video_settings.get("steps") or 0),
        "source_image_path": rel_path(source_path) if source_path else str(image_meta.get("path") or ""),
        "path": path,
        "url": f"/api/video?path={path}&v={int(out.stat().st_mtime)}",
        "prompt_id": prompt_id,
        "recovered_from": rel_path(source),
        "created_at": now,
        "updated_at": now,
    }


def copy_comfyui_animatediff_video_to_project(project: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], group: dict[str, Any], output_prefix: str, source: Path, prompt_id: str = "", model_checkpoint: str = "", motion_model: str = "", model_name: str = "animatediff_sd15") -> dict[str, Any]:
    return copy_comfyui_prefix_video_to_project(project, settings, video_settings, group, output_prefix, source, prompt_id, model_name=model_name, model_checkpoint=model_checkpoint, motion_model=motion_model)


def run_comfyui_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], prompt_bundle: dict[str, str], workflow: dict[str, Any], output_prefix: str) -> dict[str, Any]:
    wait_for_comfyui(settings, timeout=60.0)
    prompt_id = comfyui_submit_prompt(settings, workflow)
    history_item = comfyui_wait_history(settings, prompt_id, timeout=300.0)
    image_info = comfyui_first_output_image(history_item)
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    out_dir = project_images_dir(pid)
    out = out_dir / f"{output_prefix}_{prompt_id[:10]}.png"
    comfyui_download_image(settings, image_info, out)
    path = rel_path(out)
    return {
        "status": "ready",
        "provider": "comfyui",
        "model": settings.get("model"),
        "model_checkpoint": settings.get("model_checkpoint", ""),
        "aspect_ratio": settings.get("aspect_ratio"),
        "width": int(settings.get("width") or 0),
        "height": int(settings.get("height") or 0),
        "seed": int(settings.get("seed") or 0),
        "path": path,
        "url": f"/api/image?path={path}&v={int(out.stat().st_mtime)}",
        "positive_prompt": prompt_bundle.get("positive_prompt", ""),
        "negative_prompt": prompt_bundle.get("negative_prompt", ""),
        "prompt_id": prompt_id,
        "created_at": time.time(),
        "updated_at": time.time(),
    }


def compile_svd_i2v_workflow(settings: dict[str, Any], video_settings: dict[str, Any], source_image_path: Path, output_prefix: str, image_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    checkpoint = str(video_settings.get("model_checkpoint") or "").strip()
    if not checkpoint:
        raise RuntimeError("SVD/SVD-XT checkpoint is not configured; set video_i2v_model_checkpoint")
    width, height = svd_source_dimensions(settings, image_meta)
    pingpong = bool(video_settings.get("pingpong", True))
    output_fps = max(1, int(video_settings.get("output_fps") or video_settings.get("fps") or 6))
    loop_count = max(0, min(30, int(video_settings.get("loop_count") or 0)))
    return {
        "1": {"class_type": "ImageOnlyCheckpointLoader", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "LoadImage", "inputs": {"image": str(source_image_path)}},
        "3": {"class_type": "SVD_img2vid_Conditioning", "inputs": {
            "width": width,
            "height": height,
            "video_frames": int(video_settings.get("frames") or 25),
            "motion_bucket_id": int(video_settings.get("motion_bucket_id") or 127),
            "fps": int(video_settings.get("fps") or 6),
            "augmentation_level": float(video_settings.get("augmentation_level") or 0.02),
            "clip_vision": ["1", 1],
            "init_image": ["2", 0],
            "vae": ["1", 2],
        }},
        "4": {"class_type": "KSampler", "inputs": {
            "seed": int(settings.get("seed") or 1),
            "steps": int(video_settings.get("steps") or 20),
            "cfg": float(video_settings.get("cfg") or 2.5),
            "sampler_name": str(video_settings.get("sampler") or "euler"),
            "scheduler": str(video_settings.get("scheduler") or "normal"),
            "denoise": 1.0,
            "model": ["1", 0],
            "positive": ["3", 0],
            "negative": ["3", 1],
            "latent_image": ["3", 2],
        }},
        "5": {"class_type": "VAEDecode", "inputs": {"samples": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "VHS_VideoCombine", "inputs": {
            "images": ["5", 0],
            "frame_rate": output_fps,
            "loop_count": loop_count,
            "filename_prefix": output_prefix,
            "format": "video/h264-mp4",
            "pingpong": pingpong,
            "save_output": True,
        }},
    }


def animatediff_missing_dependency_error(group: dict[str, Any], video_settings: dict[str, Any]) -> RuntimeError:
    positive = truncate_text(group.get("animation_positive_prompt") or group.get("visual_prompt") or group.get("summary"), 260)
    negative = truncate_text(group.get("animation_negative_prompt") or group.get("negative_prompt"), 220)
    frames = int(video_settings.get("frames") or 16)
    fps = int(video_settings.get("fps") or 8)
    steps = int(video_settings.get("steps") or 20)
    cfg = float(video_settings.get("cfg") or 7.0)
    return RuntimeError(
        "AnimateDiff backend is selectable as an experimental option, but generated output is guarded because XTTS Studio "
        "cannot safely infer the installed ComfyUI AnimateDiff-Evolved node class names, loader inputs, ControlNet/IPAdapter "
        "stack, and motion model names from this environment. Keep Workflow=generated_svd for the current working SVD-XT path, "
        "or install ComfyUI-AnimateDiff-Evolved and VideoHelperSuite, place a motion module such as mm_sd_v15_v2.ckpt or "
        "temporaldiff-v1-animatediff.ckpt under ComfyUI/models/animatediff_models, then validate a custom AnimateDiff "
        "workflow in ComfyUI before wiring it into XTTS Studio. For object motion, use prompts like locked camera, static camera, "
        "no camera movement, objects move naturally, leaves swaying, water ripples, smoke drifting; negative terms should include "
        "camera pan, camera zoom, camera orbit, dolly, drift, whole image moving. "
        f"Prepared AnimateDiff inputs from this group: frames={frames}, fps={fps}, steps={steps}, cfg={cfg}, "
        f"positive_prompt='{positive}', negative_prompt='{negative}'."
    )


def run_comfyui_animatediff_i2v_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], output_prefix: str) -> dict[str, Any]:
    image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
    source_path = resolve_user_path(image_meta.get("path")) if image_meta.get("path") else None
    if not source_path or not source_path.exists():
        raise RuntimeError("Generate the group image before AnimateDiff image-to-video")
    wait_for_comfyui(settings, timeout=60.0)
    diagnostics = animatediff_environment_diagnostics(settings)
    if not diagnostics.get("ready"):
        raise RuntimeError("AnimateDiff is not ready: " + " | ".join(str(item) for item in diagnostics.get("blockers", [])))
    sd15_checkpoint = str(diagnostics.get("selected_sd15_checkpoint") or "")
    motion_model = str(diagnostics.get("selected_motion_model") or ANIMATEDIFF_MOTION_MODEL)
    workflow = compile_animatediff_i2v_workflow(settings, video_settings, group, source_path, output_prefix, sd15_checkpoint, motion_model, image_meta)
    submitted_at = time.time()
    prompt_id = comfyui_submit_prompt(settings, workflow)
    try:
        history_item = comfyui_wait_history(settings, prompt_id, timeout=SVD_HISTORY_WAIT_TIMEOUT_SECONDS)
    except RuntimeError:
        fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
        if fallback_output and fallback_output.exists():
            return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, fallback_output, prompt_id, sd15_checkpoint, motion_model)
        raise
    try:
        video_info = comfyui_first_output_video(history_item)
    except RuntimeError:
        fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
        if not fallback_output:
            raise
        video_info = {"filename": fallback_output.name, "subfolder": rel_path(fallback_output.parent), "type": "output"}
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    out_dir = project_videos_dir(pid)
    suffix = Path(video_info.get("filename") or "").suffix.lower()
    out = out_dir / f"{output_prefix}_{prompt_id[:10]}{suffix if suffix in {'.mp4', '.webm', '.gif'} else '.mp4'}"
    try:
        comfyui_download_output(settings, video_info, out)
    except Exception:
        fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
        if not fallback_output or not fallback_output.exists():
            raise
        return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, fallback_output, prompt_id, sd15_checkpoint, motion_model)
    return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, out, prompt_id, sd15_checkpoint, motion_model)


def run_comfyui_animatediff_sdxl_i2v_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], output_prefix: str) -> dict[str, Any]:
    image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
    source_path = resolve_user_path(image_meta.get("path")) if image_meta.get("path") else None
    if not source_path or not source_path.exists():
        raise RuntimeError("Generate the group image before HotshotXL / AnimateDiff SDXL image-to-video")
    wait_for_comfyui(settings, timeout=60.0)
    diagnostics = animatediff_sdxl_environment_diagnostics(settings)
    if not diagnostics.get("ready"):
        raise RuntimeError("HotshotXL / AnimateDiff SDXL is not ready: " + " | ".join(str(item) for item in diagnostics.get("blockers", [])))
    sdxl_checkpoint = str(diagnostics.get("selected_sdxl_checkpoint") or REALVISXL_CHECKPOINT)
    motion_model = str(diagnostics.get("selected_motion_model") or "")
    workflow = compile_animatediff_sdxl_i2v_workflow(settings, video_settings, group, source_path, output_prefix, sdxl_checkpoint, motion_model, image_meta)
    submitted_at = time.time()
    prompt_id = comfyui_submit_prompt(settings, workflow)
    try:
        history_item = comfyui_wait_history(settings, prompt_id, timeout=SVD_HISTORY_WAIT_TIMEOUT_SECONDS)
    except RuntimeError:
        fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
        if fallback_output and fallback_output.exists():
            return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, fallback_output, prompt_id, sdxl_checkpoint, motion_model, model_name="hotshotxl_sdxl")
        raise
    try:
        video_info = comfyui_first_output_video(history_item)
    except RuntimeError:
        fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
        if not fallback_output:
            raise
        video_info = {"filename": fallback_output.name, "subfolder": rel_path(fallback_output.parent), "type": "output"}
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    out_dir = project_videos_dir(pid)
    suffix = Path(video_info.get("filename") or "").suffix.lower()
    out = out_dir / f"{output_prefix}_{prompt_id[:10]}{suffix if suffix in {'.mp4', '.webm', '.gif'} else '.mp4'}"
    try:
        comfyui_download_output(settings, video_info, out)
    except Exception:
        fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
        if not fallback_output or not fallback_output.exists():
            raise
        return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, fallback_output, prompt_id, sdxl_checkpoint, motion_model, model_name="hotshotxl_sdxl")
    return copy_comfyui_animatediff_video_to_project(project, settings, video_settings, group, output_prefix, out, prompt_id, sdxl_checkpoint, motion_model, model_name="hotshotxl_sdxl")


def locate_ffprobe_for_ffmpeg(ffmpeg: str) -> str:
    ffmpeg_path = Path(ffmpeg) if ffmpeg else Path()
    if ffmpeg_path.name.lower() == "ffmpeg.exe":
        sibling = ffmpeg_path.with_name("ffprobe.exe")
        if sibling.exists():
            return str(sibling)
    if ffmpeg_path.name.lower() == "ffmpeg":
        sibling = ffmpeg_path.with_name("ffprobe")
        if sibling.exists():
            return str(sibling)
    return shutil.which("ffprobe") or ""


def ffprobe_duration_sec(ffmpeg: str, source: Path) -> float:
    ffprobe = locate_ffprobe_for_ffmpeg(ffmpeg)
    if not ffprobe:
        return 0.0
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return 0.0
    try:
        return max(0.0, float((proc.stdout or "").strip()))
    except (TypeError, ValueError):
        return 0.0


def postprocess_grok_loop_video(project: dict[str, Any], source: Path, mode: str, *, crossfade_sec: float = 0.5) -> tuple[Path, dict[str, Any]]:
    safe_mode = str(mode or "pingpong").strip().lower()
    if safe_mode not in {"off", "pingpong", "crossfade"}:
        safe_mode = "pingpong"
    if safe_mode == "off":
        return source, {"loop_postprocess": "off", "loop": False}
    ffmpeg = locate_ffmpeg(project)
    if not ffmpeg:
        raise RuntimeError("ffmpeg was not found; Grok loop post-processing requires ffmpeg on PATH or bundled with ComfyUI_windows_portable")
    out = source.with_name(f"{source.stem}_{safe_mode}_loop.mp4")
    if safe_mode == "pingpong":
        vf = "[0:v]fps=30,format=yuv420p,split=2[f][r];[r]reverse[rv];[f][rv]concat=n=2:v=1:a=0[v]"
        run_ffmpeg([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-filter_complex", vf, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-movflags", "+faststart", str(out)])
        duration = ffprobe_duration_sec(ffmpeg, out)
        return out, {"loop_postprocess": "pingpong", "loop": True, "pingpong": True, "duration_sec": duration or 0.0}
    source_duration = ffprobe_duration_sec(ffmpeg, source)
    if source_duration <= 0.25:
        raise RuntimeError("Could not determine Grok video duration for crossfade loop post-processing")
    fade = max(0.1, min(float(crossfade_sec or 0.5), min(2.0, source_duration / 2.5)))
    offset = max(0.0, source_duration - fade)
    vf = f"[0:v]fps=30,format=yuv420p,split=2[main][loop];[loop]trim=0:{fade:.3f},setpts=PTS-STARTPTS[first];[main][first]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f},trim=duration={source_duration:.3f},format=yuv420p[v]"
    run_ffmpeg([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-filter_complex", vf, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-movflags", "+faststart", str(out)])
    return out, {"loop_postprocess": "crossfade", "loop": True, "pingpong": False, "crossfade_sec": fade, "duration_sec": source_duration}


def run_xai_grok_imagine_video_i2v_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], output_prefix: str) -> dict[str, Any]:
    image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
    source_path = resolve_user_path(image_meta.get("path")) if image_meta.get("path") else None
    if not source_path or not source_path.exists():
        raise RuntimeError("Generate the group image before Grok Imagine Video image-to-video")
    project_id = safe_project_id(str(project.get("id") or active_project_id()))
    api_key = resolve_xai_api_key(project, project_id)
    if not api_key:
        raise RuntimeError("Grok/xAI API key is not configured; set a project key in XTTS Studio settings or XAI_API_KEY")
    model = str(video_settings.get("grok_model") or GROK_IMAGINE_VIDEO_MODEL).strip() or GROK_IMAGINE_VIDEO_MODEL
    duration = max(1, min(30, int(video_settings.get("grok_duration_sec") or 5)))
    resolution = str(video_settings.get("grok_resolution") or "480p").strip().lower()
    if resolution not in GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS:
        raise RuntimeError(f"Unsupported Grok Imagine Video resolution '{resolution}'. Confirmed options are: {', '.join(sorted(GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS))}")
    aspect_ratio = source_image_aspect_ratio(settings, image_meta, mode=str(video_settings.get("grok_aspect_ratio_mode") or "auto"))
    prompt = format_grok_imagine_video_prompt(group)
    base_url = (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
    request_payload = {
        "model": model,
        "prompt": prompt,
        "image": {"url": image_data_uri(source_path)},
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
    }
    start_response = xai_json_request(base_url, "/videos/generations", api_key, method="POST", payload=request_payload, timeout=120.0)
    request_id = str(start_response.get("request_id") or "") if isinstance(start_response, dict) else ""
    if not request_id:
        raise RuntimeError(f"xAI Imagine Video start response did not include request_id: {truncate_text(start_response, 500)}")
    deadline = time.time() + XAI_IMAGINE_VIDEO_POLL_TIMEOUT_SECONDS
    poll_response: dict[str, Any] = {}
    video_url = ""
    while time.time() < deadline:
        result = xai_json_request(base_url, f"/videos/{urllib.parse.quote(request_id)}", api_key, timeout=60.0)
        poll_response = result if isinstance(result, dict) else {}
        status = str(poll_response.get("status") or "").strip().lower()
        if status == "done":
            video_info = poll_response.get("video") if isinstance(poll_response.get("video"), dict) else {}
            video_url = str(video_info.get("url") or "")
            if not video_url:
                raise RuntimeError(f"xAI Imagine Video completed without video.url: {truncate_text(poll_response, 700)}")
            break
        if status in {"failed", "expired"}:
            raise RuntimeError(f"xAI Imagine Video {status}: {truncate_text(poll_response.get('error') or poll_response, 700)}")
        time.sleep(XAI_IMAGINE_VIDEO_POLL_INTERVAL_SECONDS)
    if not video_url:
        raise RuntimeError(f"Timed out waiting for xAI Imagine Video request {request_id} after {XAI_IMAGINE_VIDEO_POLL_TIMEOUT_SECONDS:.0f}s")
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    out_dir = project_videos_dir(pid)
    suffix = Path(urllib.parse.urlparse(video_url).path).suffix.lower()
    if suffix not in {".mp4", ".webm", ".gif"}:
        suffix = ".mp4"
    raw_out = out_dir / f"{output_prefix}_{request_id[:10]}_grok_raw{suffix}"
    download_http_file(video_url, raw_out)
    loop_mode = str(video_settings.get("grok_loop_postprocess") or DEFAULT_SETTINGS["video_i2v_grok_loop_postprocess"]).strip().lower()
    out, loop_meta = postprocess_grok_loop_video(project, raw_out, loop_mode, crossfade_sec=float(video_settings.get("grok_crossfade_sec") or DEFAULT_SETTINGS["video_i2v_grok_crossfade_sec"]))
    width, height = svd_source_dimensions(settings, image_meta)
    video_info = poll_response.get("video") if isinstance(poll_response.get("video"), dict) else {}
    path = rel_path(out)
    now = time.time()
    return {
        "status": "ready",
        "provider": "xai",
        "model": model,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration_sec": float(loop_meta.get("duration_sec") or video_info.get("duration") or duration),
        "width": width,
        "height": height,
        "source_image_path": rel_path(source_path),
        "original_path": rel_path(raw_out),
        "path": path,
        "url": f"/api/video?path={path}&v={int(out.stat().st_mtime)}",
        "prompt_id": request_id,
        "request_id": request_id,
        "positive_prompt": prompt,
        "loop": bool(loop_meta.get("loop", False)),
        "pingpong": bool(loop_meta.get("pingpong", False)),
        "loop_postprocess": loop_meta.get("loop_postprocess", loop_mode),
        "crossfade_sec": loop_meta.get("crossfade_sec"),
        "created_at": now,
        "updated_at": now,
    }


def run_comfyui_video_i2v_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], output_prefix: str) -> dict[str, Any]:
    workflow_mode = str(video_settings.get("workflow_mode") or "generated_svd").strip().lower()
    if workflow_mode == "generated_grok_imagine_video":
        return run_xai_grok_imagine_video_i2v_workflow(project, group, settings, video_settings, output_prefix)
    if workflow_mode == "generated_animatediff":
        return run_comfyui_animatediff_i2v_workflow(project, group, settings, video_settings, output_prefix)
    if workflow_mode == "generated_hotshotxl":
        return run_comfyui_animatediff_sdxl_i2v_workflow(project, group, settings, video_settings, output_prefix)
    return run_comfyui_svd_i2v_workflow(project, group, settings, video_settings, output_prefix)


def run_comfyui_svd_i2v_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], video_settings: dict[str, Any], output_prefix: str) -> dict[str, Any]:
    image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
    source_path = resolve_user_path(image_meta.get("path")) if image_meta.get("path") else None
    if not source_path or not source_path.exists():
        raise RuntimeError("Generate the group image before SVD/SVD-XT image-to-video")
    wait_for_comfyui(settings, timeout=60.0)
    width, height = svd_source_dimensions(settings, image_meta)
    workflow = compile_svd_i2v_workflow(settings, video_settings, source_path, output_prefix, image_meta)
    submitted_at = time.time()
    prompt_id = comfyui_submit_prompt(settings, workflow)
    try:
        history_item = comfyui_wait_history(settings, prompt_id, timeout=SVD_HISTORY_WAIT_TIMEOUT_SECONDS)
    except RuntimeError:
        fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
        if fallback_output and fallback_output.exists():
            return copy_comfyui_prefix_video_to_project(project, settings, video_settings, group, output_prefix, fallback_output, prompt_id)
        raise
    try:
        video_info = comfyui_first_output_video(history_item)
    except RuntimeError as exc:
        fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
        if not fallback_output:
            raise
        video_info = {"filename": fallback_output.name, "subfolder": rel_path(fallback_output.parent), "type": "output"}
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    out_dir = project_videos_dir(pid)
    source_suffix = Path(video_info.get("filename") or "").suffix.lower()
    suffix = source_suffix if source_suffix in {".mp4", ".webm", ".gif"} else ".mp4"
    out = out_dir / f"{output_prefix}_{prompt_id[:10]}{suffix}"
    fallback_source = comfyui_newest_video_by_prefix(settings, output_prefix, submitted_at)
    try:
        comfyui_download_output(settings, video_info, out)
    except Exception:
        if not fallback_source or not fallback_source.exists():
            raise
        return copy_comfyui_prefix_video_to_project(project, settings, video_settings, group, output_prefix, fallback_source, prompt_id)
    path = rel_path(out)
    frames = int(video_settings.get("frames") or 0)
    fps = int(video_settings.get("fps") or 0)
    pingpong = bool(video_settings.get("pingpong", True))
    loop_count = max(0, int(video_settings.get("loop_count") or 0))
    output_fps = max(1, int(video_settings.get("output_fps") or fps or 1))
    single_loop_frames = max(0, frames * 2 - 2) if pingpong and frames > 1 else frames
    output_frames = single_loop_frames * (loop_count + 1)
    duration_sec = round(output_frames / float(output_fps), 3) if output_fps > 0 and output_frames > 0 else 0.0
    return {
        "status": "ready",
        "provider": "comfyui",
        "model": "svd_xt" if "xt" in str(video_settings.get("model_checkpoint") or "").lower() else "svd",
        "model_checkpoint": video_settings.get("model_checkpoint", ""),
        "motion_style": str(video_settings.get("motion_style") or ""),
        "width": width,
        "height": height,
        "seed": int(settings.get("seed") or 0),
        "frames": frames,
        "fps": fps,
        "output_fps": output_fps,
        "output_frames": output_frames,
        "loop_count": loop_count,
        "target_duration_sec": float(video_settings.get("target_duration_sec") or 0.0),
        "duration_sec": duration_sec,
        "loop": True,
        "pingpong": pingpong,
        "motion_bucket_id": int(video_settings.get("motion_bucket_id") or 0),
        "augmentation_level": float(video_settings.get("augmentation_level") or 0.0),
        "min_cfg": float(video_settings.get("min_cfg") or 0.0),
        "cfg": float(video_settings.get("cfg") or 0.0),
        "steps": int(video_settings.get("steps") or 0),
        "source_image_path": rel_path(source_path),
        "path": path,
        "url": f"/api/video?path={path}&v={int(out.stat().st_mtime)}",
        "prompt_id": prompt_id,
        "created_at": time.time(),
        "updated_at": time.time(),
    }


def image_orientation_phrase(settings: dict[str, Any]) -> str:
    return "vertical portrait composition, 9:16 frame" if settings.get("aspect_ratio") == "vertical" else "wide horizontal composition, 16:9 frame"


def format_image_prompt(group: dict[str, Any], settings: dict[str, Any]) -> dict[str, str]:
    visual = truncate_text(group.get("visual_prompt") or group.get("summary") or group.get("title"), 1400)
    negative_group = truncate_text(group.get("negative_prompt"), 700)
    mood = truncate_text(group.get("mood") or "calm", 120)
    scene_type = truncate_text(group.get("scene_type") or "sleep lecture", 120)
    ancient_prehistory = looks_like_ancient_prehistory_scene(visual, scene_type)
    group_already_uses_ancient_negative = bool(negative_group) and looks_like_ancient_prehistory_scene(negative_group)
    orientation = image_orientation_phrase(settings)
    model = str(settings.get("model") or "sdxl")
    exclude_people = bool(settings.get("exclude_people"))
    style = IMAGE_STYLE_PRESETS.get(str(settings.get("style_preset") or DEFAULT_SETTINGS["image_style_preset"]).strip(), IMAGE_STYLE_PRESETS["sleep_documentary"])
    style_negative = str(style.get("negative") or "")
    negatives = ", ".join(part for part in [negative_group, style_negative, COMMON_REALVISXL_NEGATIVE] if part)
    if exclude_people:
        visual = truncate_text(f"{NO_PEOPLE_VISUAL_INSTRUCTION}{visual}", 1400)
        negatives = append_unique_csv_terms(negatives, NO_PEOPLE_IMAGE_NEGATIVE, limit=1500)
    if ancient_prehistory and group_already_uses_ancient_negative:
        negatives = append_unique_csv_terms(negatives, ANCIENT_PREHISTORY_NEGATIVE)
    if model in {"realvisxl", "sdxl", "juggernautxl", "dreamshaperxl"}:
        era_positive = ""
        if ancient_prehistory and not exclude_people:
            era_positive = (
                "ancient/prehistory authenticity, era-appropriate humans, visible natural-material clothing, "
                "barefoot prehistoric humans or ancient villagers as appropriate, rough animal-hide wraps or fur cloaks for Stone Age scenes, "
                "linen tunics only when historically appropriate, no modern objects visible, no tailored clothing visible"
            )
        positive = ", ".join(part for part in [
            visual,
            era_positive,
            style.get("positive_prefix"),
            "single clear subject-focused frame",
            "realistic documentary photography",
            "soft natural light",
            mood,
            scene_type,
            orientation,
            style.get("positive_suffix"),
            "high detail, gentle colors",
        ] if part)
        negative = negatives
    elif model == "flux":
        positive = (
            f"Create a calm cinematic image for a sleep lecture. Show: {visual}. "
            f"Mood: {mood}. Scene type: {scene_type}. Use {orientation}, soft natural light, "
            "documentary-inspired atmosphere, no visible text."
        )
        negative = negative_group or "text, watermark, logo"
    else:
        positive = f"{visual}. {orientation}".strip()
        negative = negative_group
    return {"positive_prompt": positive.strip(), "negative_prompt": negative.strip()}


def update_group_prompts(project: dict[str, Any], group_id: str, payload: GroupUpdate) -> dict[str, Any]:
    group = find_video_group(project, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Video group not found")
    data = payload.dict(exclude_unset=True)
    limits = {
        "title": 120,
        "summary": 600,
        "visual_prompt": 1400,
        "negative_prompt": 1500,
        "animation_positive_prompt": 900,
        "animation_negative_prompt": 700,
        "grok_video_prompt": 1800,
        "mood": 80,
        "scene_type": 80,
        "video_motion_intensity": 80,
        "video_loop_notes": 700,
    }
    valid_chunk_ids = set(chunk_order_ids(ordered_project_chunks(project)))
    for key, value in data.items():
        if value is None:
            continue
        if key == "chunk_ids":
            group["chunk_ids"] = [str(chunk_id) for chunk_id in value if str(chunk_id) in valid_chunk_ids]
            continue
        if key == "media_items":
            group["media_items"] = normalize_group_media_items([item.dict() if hasattr(item, "dict") else item for item in value], group)
            continue
        if key == "media_layout":
            group["media_layout"] = normalize_group_media_layout(value)
            continue
        if key == "default_media_duration_sec":
            group["default_media_duration_sec"] = normalize_group_media_duration(value, 0.0)
            continue
        group[key] = truncate_text(value, limits.get(key, 500))
    normalize_arrangement(project)
    return find_video_group(project, group_id) or group


def create_video_group_dict(title: str, summary: str, chunk_ids: list[str], *, order: int = 0, source: str = "manual") -> dict[str, Any]:
    visual_prompt = truncate_text(summary or title or "Manual visual scene", 900)
    animation_positive = build_animation_positive_prompt(summary, visual_prompt)
    group = {
        "id": f"video_group_{order + 1:03d}",
        "title": truncate_text(title or f"Video group {order + 1}", 120),
        "summary": truncate_text(summary, 600),
        "chunk_ids": [str(chunk_id) for chunk_id in chunk_ids if str(chunk_id)],
        "visual_prompt": visual_prompt,
        "negative_prompt": DEFAULT_VIDEO_GROUP_NEGATIVE,
        "animation_positive_prompt": animation_positive,
        "animation_negative_prompt": DEFAULT_ANIMATION_NEGATIVE_PROMPT,
        "grok_video_prompt": format_grok_imagine_video_prompt({"animation_positive_prompt": animation_positive, "visual_prompt": visual_prompt, "summary": summary, "title": title}),
        "mood": "calm",
        "scene_type": "sleep lecture",
        "order": order,
        "source": source,
        "media_items": [],
        "media_layout": "sequence",
        "default_media_duration_sec": 0.0,
    }
    return group


def find_video_group(project: dict[str, Any], group_id: str) -> dict[str, Any] | None:
    groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
    return next((group for group in groups if isinstance(group, dict) and group.get("id") == group_id), None)


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


def active_image_task_for_group(project_id: str, group_id: str) -> dict[str, Any] | None:
    pid = safe_project_id(project_id)
    with _queue_lock:
        for task in _tasks:
            payload = task.get("payload") or task.get("params") or {}
            if task.get("kind") == "image_group" and task.get("project_id") == pid and payload.get("group_id") == group_id and task.get("status") in {"queued", "running"}:
                return dict(task)
    return None


def active_video_task_for_group(project_id: str, group_id: str) -> dict[str, Any] | None:
    pid = safe_project_id(project_id)
    with _queue_lock:
        for task in _tasks:
            payload = task.get("payload") or task.get("params") or {}
            if task.get("kind") == "video_group" and task.get("project_id") == pid and payload.get("group_id") == group_id and task.get("status") in {"queued", "running"}:
                return dict(task)
    return None


def generate_group_placeholder_svg(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], prompt_bundle: dict[str, str], error: str = "") -> dict[str, Any]:
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    out_dir = project_images_dir(pid)
    out_dir.mkdir(parents=True, exist_ok=True)
    group_id = str(group.get("id") or uuid.uuid4().hex[:10])
    out = out_dir / f"{group_id}_{int(time.time())}.svg"
    width = int(settings.get("width") or 1024)
    height = int(settings.get("height") or 1792)
    title = html.escape(str(group.get("title") or group_id))
    summary = html.escape(truncate_text(group.get("summary") or group.get("visual_prompt") or "", 260))
    positive = html.escape(truncate_text(prompt_bundle.get("positive_prompt"), 520))
    error_text = html.escape(truncate_text(error, 300))
    accent = "#7aa2ff" if settings.get("aspect_ratio") == "vertical" else "#8ee6c9"
    fallback_line = ""
    if error_text:
        fallback_line = (
            f'<text x="{int(width * 0.09)}" y="{int(height * 0.90)}" fill="#ffb4a8" '
            f'font-family="Segoe UI, Arial, sans-serif" font-size="{max(18, int(width * 0.022))}">'
            f'Fallback reason: {error_text}</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#141827"/>
      <stop offset="55%" stop-color="#26304d"/>
      <stop offset="100%" stop-color="#0f1320"/>
    </linearGradient>
    <radialGradient id="moon" cx="50%" cy="35%" r="55%">
      <stop offset="0%" stop-color="#fff6d6" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#fff6d6" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <circle cx="{int(width * 0.72)}" cy="{int(height * 0.18)}" r="{max(80, int(min(width, height) * 0.12))}" fill="url(#moon)"/>
  <path d="M0 {int(height * 0.72)} C {int(width * 0.18)} {int(height * 0.62)}, {int(width * 0.34)} {int(height * 0.82)}, {int(width * 0.52)} {int(height * 0.70)} S {int(width * 0.82)} {int(height * 0.64)}, {width} {int(height * 0.74)} L {width} {height} L 0 {height} Z" fill="#0b1020" opacity="0.72"/>
  <rect x="{int(width * 0.07)}" y="{int(height * 0.08)}" width="{int(width * 0.86)}" height="{int(height * 0.84)}" rx="28" fill="none" stroke="{accent}" stroke-width="4" opacity="0.55"/>
  <text x="{int(width * 0.09)}" y="{int(height * 0.13)}" fill="{accent}" font-family="Segoe UI, Arial, sans-serif" font-size="{max(28, int(width * 0.035))}" font-weight="700">XTTS Studio placeholder</text>
  <text x="{int(width * 0.09)}" y="{int(height * 0.19)}" fill="#f4f1e8" font-family="Segoe UI, Arial, sans-serif" font-size="{max(34, int(width * 0.047))}" font-weight="700">{title}</text>
  <foreignObject x="{int(width * 0.09)}" y="{int(height * 0.24)}" width="{int(width * 0.82)}" height="{int(height * 0.20)}">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: Segoe UI, Arial, sans-serif; color: #dbe4ff; font-size: {max(24, int(width * 0.030))}px; line-height: 1.35;">{summary}</div>
  </foreignObject>
  <foreignObject x="{int(width * 0.09)}" y="{int(height * 0.50)}" width="{int(width * 0.82)}" height="{int(height * 0.23)}">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: Consolas, monospace; color: #aebcf2; font-size: {max(18, int(width * 0.022))}px; line-height: 1.35;">Prompt: {positive}</div>
  </foreignObject>
  <text x="{int(width * 0.09)}" y="{int(height * 0.86)}" fill="#bcc7e8" font-family="Segoe UI, Arial, sans-serif" font-size="{max(20, int(width * 0.025))}">provider={html.escape(str(settings.get('provider')))} · model={html.escape(str(settings.get('model')))} · seed={int(settings.get('seed') or 0)}</text>
  {fallback_line}
</svg>
'''
    out.write_text(svg, encoding="utf-8")
    path = rel_path(out)
    return {
        "status": "ready",
        "provider": "placeholder",
        "model": settings.get("model"),
        "aspect_ratio": settings.get("aspect_ratio"),
        "width": width,
        "height": height,
        "seed": int(settings.get("seed") or 0),
        "path": path,
        "url": f"/api/image?path={path}&v={int(out.stat().st_mtime)}",
        "positive_prompt": prompt_bundle.get("positive_prompt", ""),
        "negative_prompt": prompt_bundle.get("negative_prompt", ""),
        "error": error,
        "created_at": time.time(),
        "updated_at": time.time(),
    }


def generate_group_image(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], prompt_bundle: dict[str, str]) -> dict[str, Any]:
    if settings.get("provider") == "grok":
        try:
            return run_xai_grok_image_workflow(project, group, settings, prompt_bundle)
        except Exception as exc:
            return generate_group_placeholder_svg(project, group, settings, prompt_bundle, f"Grok image generation failed or endpoint schema unsupported: {exc}")
    if settings.get("provider") != "comfyui":
        return generate_group_placeholder_svg(project, group, settings, prompt_bundle)
    if settings.get("model") == "flux":
        return generate_group_placeholder_svg(project, group, settings, prompt_bundle, "FLUX generated workflow is not implemented yet; use SDXL/Juggernaut/DreamShaper")
    workflow_mode = str(settings.get("workflow_mode") or "generated")
    output_prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", f"xtts_{safe_project_id(str(project.get('id') or active_project_id()))}_{group.get('id', 'group')}").strip("_")
    if workflow_mode == "disabled":
        return generate_group_placeholder_svg(project, group, settings, prompt_bundle, "ComfyUI workflow mode is disabled")
    if workflow_mode == "generated":
        try:
            workflow = compile_sdxl_txt2img_workflow(settings, prompt_bundle, output_prefix)
            return run_comfyui_workflow(project, group, settings, prompt_bundle, workflow, output_prefix)
        except Exception as exc:
            return generate_group_placeholder_svg(project, group, settings, prompt_bundle, f"ComfyUI generated workflow failed: {exc}")
    if workflow_mode != "template":
        return generate_group_placeholder_svg(project, group, settings, prompt_bundle, f"Unsupported ComfyUI workflow mode: {workflow_mode}")
    workflow_path = resolve_user_path(settings.get("workflow_path")) if settings.get("workflow_path") else None
    if not workflow_path or not workflow_path.exists():
        return generate_group_placeholder_svg(project, group, settings, prompt_bundle, "ComfyUI workflow template is not configured")
    try:
        template = workflow_path.read_text(encoding="utf-8")
        rendered = template
        for key, value in {
            "positive_prompt": prompt_bundle.get("positive_prompt", ""),
            "negative_prompt": prompt_bundle.get("negative_prompt", ""),
            "width": str(settings.get("width")),
            "height": str(settings.get("height")),
            "seed": str(settings.get("seed")),
            "output_prefix": output_prefix,
            "model_checkpoint": settings.get("model_checkpoint", ""),
            "steps": str(settings.get("steps")),
            "cfg": str(settings.get("cfg")),
            "sampler": settings.get("sampler", ""),
            "scheduler": settings.get("scheduler", ""),
        }.items():
            rendered = rendered.replace("{{" + key + "}}", str(value))
        workflow = json.loads(rendered)
        if not isinstance(workflow, dict):
            raise RuntimeError("Workflow template root must be a JSON object")
        return run_comfyui_workflow(project, group, settings, prompt_bundle, workflow, output_prefix)
    except Exception as exc:
        return generate_group_placeholder_svg(project, group, settings, prompt_bundle, f"ComfyUI workflow template failed: {exc}")


def extract_xai_image_url(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    data = response.get("data")
    if isinstance(data, list) and data:
        first = data[0] if isinstance(data[0], dict) else {}
        if first.get("url"):
            return str(first.get("url") or "")
        if first.get("b64_json"):
            return "data:image/png;base64," + str(first.get("b64_json") or "")
    image = response.get("image") if isinstance(response.get("image"), dict) else {}
    return str(image.get("url") or response.get("url") or "")


def save_xai_image_url(image_url: str, out: Path) -> None:
    if image_url.startswith("data:image/"):
        _header, encoded = image_url.split(",", 1)
        out.write_bytes(base64.b64decode(encoded))
        return
    download_http_file(image_url, out, timeout=180.0)


def run_xai_grok_image_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], prompt_bundle: dict[str, str]) -> dict[str, Any]:
    project_id = safe_project_id(str(project.get("id") or active_project_id()))
    api_key = resolve_xai_api_key(project, project_id)
    if not api_key:
        raise RuntimeError("Grok/xAI API key is not configured; set a project key in XTTS Studio settings or XAI_API_KEY")
    base_url = (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
    model = str(settings.get("grok_model") or GROK_IMAGE_MODEL).strip() or GROK_IMAGE_MODEL
    width = int(settings.get("width") or 1024)
    height = int(settings.get("height") or 1024)
    request_payload = {
        "model": model,
        "prompt": prompt_bundle.get("positive_prompt", ""),
        "n": 1,
        "response_format": "url",
        "size": f"{width}x{height}",
    }
    response = xai_json_request(base_url, "/images/generations", api_key, method="POST", payload=request_payload, timeout=180.0)
    image_url = extract_xai_image_url(response)
    if not image_url:
        raise RuntimeError(f"xAI image response did not include a URL or b64_json: {truncate_text(response, 700)}")
    out_dir = project_images_dir(project_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{group.get('id', 'group')}_{int(time.time())}_grok.png"
    save_xai_image_url(image_url, out)
    path = rel_path(out)
    now = time.time()
    return {
        "status": "ready",
        "provider": "xai",
        "model": model,
        "aspect_ratio": settings.get("aspect_ratio"),
        "width": width,
        "height": height,
        "path": path,
        "url": f"/api/image?path={path}&v={int(out.stat().st_mtime)}",
        "positive_prompt": prompt_bundle.get("positive_prompt", ""),
        "negative_prompt": prompt_bundle.get("negative_prompt", ""),
        "created_at": now,
        "updated_at": now,
    }


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


def enqueue_task(
    kind: str,
    chunk_id: str | None = None,
    project_id: str | None = None,
    payload: dict[str, Any] | None = None,
    label: str | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    ensure_worker()
    pid = safe_project_id(project_id or active_project_id())
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


def active_task_by_kind_project(kind: str, project_id: str) -> dict[str, Any] | None:
    pid = safe_project_id(project_id)
    with _queue_lock:
        for task in _tasks:
            if task.get("kind") == kind and task.get("project_id") == pid and task.get("status") in {"queued", "running"}:
                return dict(task)
    return None


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
        update_task(task["id"], progress_percent=5, stage="starting")
        try:
            if task["kind"] == "generate_chunk" and task.get("chunk_id"):
                project = load_project(task.get("project_id"))
                chunk = next((c for c in project["chunks"] if c["id"] == task["chunk_id"]), None)
                if not chunk:
                    raise RuntimeError("Chunk not found")
                set_status(project, f"Queued generation running: chunk {chunk.get('order', 0) + 1}", True)
                set_progress(active=True, percent=20, message="Loading/generating XTTS chunk…", current_task_id=task["id"])
                update_task(task["id"], progress_percent=20, message="Loading/generating XTTS chunk…", stage="generating")
                before_versions = {v.get("id") for v in chunk.get("versions", [])}
                generate_tts_chunk(project, chunk)
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
                payload_data = task.get("payload") or task.get("params") or {}
                payload = ExportRequest(**payload_data) if isinstance(payload_data, dict) and payload_data else ExportRequest()
                export_label = "video with audio" if str(payload.export_type).startswith("video") else f"audio {payload.audio_format.upper()}"
                set_progress(active=True, percent=40, message=f"Exporting {export_label}…", current_task_id=task["id"])
                update_task(task["id"], progress_percent=40, message=f"Exporting {export_label}…", stage="exporting")
                result = export_project_with_settings(project, payload)
                project = load_project(task.get("project_id"))
                set_status(project, f"Export complete: {result.get('path')}")
                update_task(task["id"], result_kind="export", result_path=result.get("path", ""), stage="saved")
            elif task["kind"] == "grok_groups":
                project = load_project(task.get("project_id"))
                payload_data = task.get("payload") or task.get("params") or {}
                payload = VideoGroupsAiRequest(**payload_data)
                set_status(project, "Grok AI grouping running", True)
                set_progress(active=True, percent=10, message="Preparing Grok AI grouping…", current_task_id=task["id"])
                update_task(task["id"], progress_percent=10, message="Preparing Grok AI grouping…", stage="preparing")

                def grok_progress(stage_message: str, percent: float) -> None:
                    set_progress(active=True, percent=percent, message=stage_message, current_task_id=task["id"])
                    update_task(task["id"], progress_percent=percent, message=stage_message, stage=stage_message)

                groups = generate_video_groups_ai(project, payload, progress_callback=grok_progress)
                grok_progress("Saving Grok AI groups…", 95)
                video = project.setdefault("arrangement", {}).setdefault("video", {})
                video["groups"] = groups
                normalize_arrangement(project)
                set_status(project, f"Video groups saved: {len(groups)} group(s)")
                update_task(
                    task["id"],
                    result_kind="video_groups",
                    result_group_count=len(groups),
                    stage="saved",
                )
            elif task["kind"] == "image_group":
                project = load_project(task.get("project_id"))
                payload_data = task.get("payload") or task.get("params") or {}
                group_id = str(payload_data.get("group_id") or "")
                group = find_video_group(project, group_id)
                if not group:
                    raise RuntimeError("Video group not found")
                set_status(project, f"Image generation running: {group.get('title') or group_id}", True)
                running_meta = normalize_group_image_meta(group.get("image") if isinstance(group.get("image"), dict) else {})
                running_meta.update({"status": "running", "updated_at": time.time()})
                update_video_group_image(project, group_id, running_meta)
                save_project(project)
                set_progress(active=True, percent=25, message="Formatting image prompt…", current_task_id=task["id"])
                update_task(task["id"], progress_percent=25, message="Formatting image prompt…", stage="prompt")
                settings = image_settings(project)
                prompt_bundle = format_image_prompt(group, settings)
                set_progress(active=True, percent=55, message="Generating image artifact…", current_task_id=task["id"])
                update_task(task["id"], progress_percent=55, message="Generating image artifact…", stage="generating")
                image_meta = generate_group_image(project, group, settings, prompt_bundle)
                image_meta["status"] = "ready"
                update_video_group_image(project, group_id, image_meta)
                normalize_arrangement(project)
                save_project(project)
                set_status(project, f"Image ready: {group.get('title') or group_id}")
                update_task(
                    task["id"],
                    result_kind="image_group",
                    result_group_id=group_id,
                    result_image_path=image_meta.get("path", ""),
                    stage="saved",
                )
            elif task["kind"] == "video_group":
                project = load_project(task.get("project_id"))
                payload_data = task.get("payload") or task.get("params") or {}
                group_id = str(payload_data.get("group_id") or "")
                group = find_video_group(project, group_id)
                if not group:
                    raise RuntimeError("Video group not found")
                settings = image_settings(project)
                vsettings = video_i2v_settings(project)
                backend_label = video_i2v_backend_label(vsettings)
                set_status(project, f"{backend_label} video generation running: {group.get('title') or group_id}", True)
                running_meta = normalize_group_video_meta(group.get("video") if isinstance(group.get("video"), dict) else {})
                running_meta.update({"status": "running", "updated_at": time.time()})
                update_video_group_video(project, group_id, running_meta)
                save_project(project)
                set_progress(active=True, percent=35, message=f"Preparing {backend_label} image-to-video workflow…", current_task_id=task["id"])
                update_task(task["id"], progress_percent=35, message=f"Preparing {backend_label} image-to-video workflow…", stage="workflow")
                if not vsettings.get("enabled"):
                    raise RuntimeError(f"{backend_label} image-to-video is disabled in settings")
                if vsettings.get("workflow_mode") == "disabled":
                    raise RuntimeError(f"{backend_label} workflow mode is disabled")
                set_progress(active=True, percent=55, message=f"Generating {backend_label} video…", current_task_id=task["id"])
                update_task(task["id"], progress_percent=55, message=f"Generating {backend_label} video…", stage="generating")
                output_prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", f"xtts_i2v_{safe_project_id(str(project.get('id') or active_project_id()))}_{group_id}").strip("_")
                video_meta = run_comfyui_video_i2v_workflow(project, group, settings, vsettings, output_prefix)
                video_meta["status"] = "ready"
                update_video_group_video(project, group_id, video_meta)
                normalize_arrangement(project)
                save_project(project)
                set_status(project, f"{backend_label} video ready: {group.get('title') or group_id}")
                update_task(
                    task["id"],
                    result_kind="video_group",
                    result_group_id=group_id,
                    result_video_path=video_meta.get("path", ""),
                    stage="saved",
                )
            update_task(task["id"], status="done", message="Done", progress_percent=100, stage="done")
            set_progress(active=False, percent=100, message="Done", current_task_id=None)
        except Exception as exc:
            update_task(task["id"], status="failed", message=str(exc), stage="failed")
            set_progress(active=False, percent=0, message=f"Failed: {exc}", current_task_id=None)
            try:
                project = load_project(task.get("project_id"))
                if task.get("kind") == "video_group":
                    payload_data = task.get("payload") or task.get("params") or {}
                    group_id = str(payload_data.get("group_id") or "")
                    group = find_video_group(project, group_id) if group_id else None
                    if group:
                        settings = image_settings(project)
                        vsettings = video_i2v_settings(project)
                        output_prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", f"xtts_i2v_{safe_project_id(str(project.get('id') or active_project_id()))}_{group_id}").strip("_")
                        fallback_output = comfyui_newest_video_by_prefix(settings, output_prefix, 0.0)
                        if fallback_output and fallback_output.exists():
                            video_meta = copy_comfyui_prefix_video_to_project(project, settings, vsettings, group, output_prefix, fallback_output, "")
                            video_meta["status"] = "ready"
                            update_video_group_video(project, group_id, video_meta)
                            normalize_arrangement(project)
                            save_project(project)
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
                            set_status(project, f"SVD/SVD-XT video recovered: {group.get('title') or group_id}")
                            continue
                        failed_meta = normalize_group_video_meta(group.get("video") if isinstance(group.get("video"), dict) else {})
                        failed_meta.update({"status": "failed", "error": str(exc), "updated_at": time.time()})
                        update_video_group_video(project, group_id, failed_meta)
                        save_project(project)
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


def generate_silero_chunk(project: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
    settings = project["settings"]
    out_dir = project_chunks_dir(project.get("id") or active_project_id())
    out_dir.mkdir(parents=True, exist_ok=True)
    versions = chunk.setdefault("versions", [])
    normalize_chunk_versions(chunk)
    next_index = max([int(v.get("index") or 0) for v in versions] + [0]) + 1
    version_id = uuid.uuid4().hex[:10]
    out = out_dir / f"chunk_{chunk['id']}_v{next_index:03d}_{version_id}_silero.wav"
    text_for_tts = tts_input_text(project, chunk_tts_source_text(chunk))
    base_url = str(settings.get("silero_api_url") or DEFAULT_SETTINGS["silero_api_url"]).strip().rstrip("/")
    if not base_url:
        raise RuntimeError("Silero API URL is empty")
    payload = {
        "text": text_for_tts,
        "speaker": str(settings.get("silero_speaker") or DEFAULT_SETTINGS["silero_speaker"]),
        "sample_rate": int(settings.get("silero_sample_rate") or DEFAULT_SETTINGS["silero_sample_rate"]),
        "output_path": str(out),
        "return_file": False,
        "realism_enabled": bool(settings.get("silero_realism_enabled", DEFAULT_SETTINGS["silero_realism_enabled"])),
        "preset": str(settings.get("silero_realism_preset") or DEFAULT_SETTINGS["silero_realism_preset"]),
        "seed": int(settings.get("seed", DEFAULT_SETTINGS["seed"])),
        "speed": settings.get("speed", DEFAULT_SETTINGS["speed"]),
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
    chunk["audio_path"] = rel_path(out)
    chunk["generated_at"] = time.time()
    chunk["duration_sec"] = stats["duration_sec"]
    return chunk


def generate_tts_chunk(project: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
    backend = normalize_tts_backend(project.get("settings", {}))
    if backend == "silero":
        return generate_silero_chunk(project, chunk)
    return generate_xtts_chunk(project, chunk)


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
    text_for_tts = tts_input_text(project, chunk_tts_source_text(chunk))
    kwargs = {
        "text": text_for_tts,
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
            "tts_backend": "xtts",
            "text": clean_text(chunk.get("text", "")),
            "tts_text": text_for_tts,
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


def sanitize_bitrate(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip().lower()
    if re.fullmatch(r"[1-9][0-9]{1,3}k", text):
        return text
    return fallback


def locate_ffmpeg(project: dict[str, Any] | None = None) -> str:
    settings = image_settings(project) if isinstance(project, dict) else {}
    candidates: list[Path] = []
    comfy_root = resolve_user_path(str(settings.get("comfyui_path") or DEFAULT_SETTINGS["image_comfyui_path"])) if settings else resolve_user_path(DEFAULT_SETTINGS["image_comfyui_path"])
    if comfy_root:
        candidates.extend([
            comfy_root / "ffmpeg.exe",
            comfy_root / "ComfyUI" / "ffmpeg.exe",
            comfy_root / "python_embeded" / "ffmpeg.exe",
        ])
    candidates.extend([ROOT / "ComfyUI_windows_portable" / "ffmpeg.exe", ROOT / "ffmpeg.exe"])
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffmpeg") or ""


def run_ffmpeg(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ffmpeg failed").strip()[:2000])


def export_dimensions(project: dict[str, Any], payload: ExportRequest) -> tuple[int, int, str]:
    orientation = str(payload.orientation or "auto").strip().lower()
    if orientation not in {"auto", "landscape", "portrait", "square"}:
        orientation = "auto"
    if orientation == "auto":
        img_settings = image_settings(project)
        orientation = "landscape" if img_settings.get("aspect_ratio") == "horizontal" else "portrait"
    res = str(payload.resolution or "720p").strip().lower()
    long_edge = 1080 if "1080" in res else 720
    if orientation == "square":
        return long_edge, long_edge, orientation
    if orientation == "portrait":
        return int(round(long_edge * 9 / 16)) // 2 * 2, long_edge, orientation
    return long_edge, int(round(long_edge * 9 / 16)) // 2 * 2, orientation


def group_time_ranges(project: dict[str, Any]) -> list[tuple[dict[str, Any], float, float]]:
    chunks = sorted(project.get("chunks", []), key=lambda c: c.get("order", 0))
    cursor = 0.0
    chunk_times: dict[str, tuple[float, float]] = {}
    for chunk in chunks:
        duration = float(chunk.get("duration_sec", 0.0) or 0.0)
        start = cursor
        end = start + duration
        if chunk.get("id"):
            chunk_times[str(chunk.get("id"))] = (start, end)
        cursor = end + float(chunk.get("pause_after", 0.0) or 0.0)
    groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
    ranges: list[tuple[dict[str, Any], float, float]] = []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        ids = [str(item) for item in (group.get("chunk_ids") or [])]
        spans = [chunk_times[item] for item in ids if item in chunk_times]
        if not spans:
            continue
        ranges.append((group, min(item[0] for item in spans), max(item[1] for item in spans)))
    ranges.sort(key=lambda item: item[1])
    return ranges


def ffmpeg_visual_filter(width: int, height: int, fit: str) -> str:
    if str(fit or "cover").lower() == "contain":
        return f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    return f"scale=w={width}:h={height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"


def clamp_video_speed(value: Any) -> float:
    try:
        return round(max(0.25, min(2.0, float(value))), 3)
    except (TypeError, ValueError):
        return 1.0


def normalized_video_speed_envelope(project: dict[str, Any]) -> list[dict[str, float]]:
    raw_points = project.get("arrangement", {}).get("video", {}).get("speed_envelope", [])
    points: list[dict[str, float]] = []
    if isinstance(raw_points, list):
        for point in raw_points:
            if not isinstance(point, dict):
                continue
            try:
                points.append({
                    "time": round(max(0.0, float(point.get("time", 0.0))), 3),
                    "speed": clamp_video_speed(point.get("speed", point.get("playback_rate", 1.0))),
                })
            except (TypeError, ValueError):
                continue
    points = sorted(points or [{"time": 0.0, "speed": 1.0}], key=lambda item: item["time"])
    if points[0]["time"] > 0.001:
        points.insert(0, {"time": 0.0, "speed": points[0]["speed"]})
    return points


def video_speed_at(points: list[dict[str, float]], time_sec: float) -> float:
    if not points:
        return 1.0
    time_value = max(0.0, float(time_sec or 0.0))
    for idx in range(1, len(points)):
        prev = points[idx - 1]
        next_point = points[idx]
        if time_value <= next_point["time"]:
            span = max(0.0001, next_point["time"] - prev["time"])
            ratio = max(0.0, min(1.0, (time_value - prev["time"]) / span))
            return clamp_video_speed(prev["speed"] + (next_point["speed"] - prev["speed"]) * ratio)
    return clamp_video_speed(points[-1]["speed"])


def split_range_by_speed_envelope(start: float, end: float, points: list[dict[str, float]]) -> list[tuple[float, float]]:
    if end <= start:
        return []
    cuts = [start]
    for point in points:
        point_time = float(point.get("time", 0.0))
        if start + 0.001 < point_time < end - 0.001:
            cuts.append(point_time)
    cuts.append(end)
    cuts = sorted(set(round(cut, 3) for cut in cuts))
    return [(cuts[idx], cuts[idx + 1]) for idx in range(len(cuts) - 1) if cuts[idx + 1] - cuts[idx] > 0.01]


def build_visual_segment(project: dict[str, Any], group: dict[str, Any], duration: float, width: int, height: int, fps: int, fit: str, out: Path, speed: float = 1.0) -> bool:
    ffmpeg = locate_ffmpeg(project)
    video_meta = group.get("video") if isinstance(group.get("video"), dict) else {}
    image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
    media_items = normalize_group_media_items(group.get("media_items"), group)
    selected_media = next((item for item in media_items if item.get("type") == "video" and item.get("path")), None) or next((item for item in media_items if item.get("path")), None)
    source_value = (selected_media or {}).get("path") or video_meta.get("path") or image_meta.get("path") or ""
    source_path = resolve_user_path(source_value) if source_value else None
    if not source_path or not source_path.exists():
        return False
    vf = ffmpeg_visual_filter(width, height, fit)
    speed_value = clamp_video_speed(speed)
    out.parent.mkdir(parents=True, exist_ok=True)
    if source_path.suffix.lower() in {".mp4", ".webm", ".gif", ".mov", ".mkv"}:
        speed_filter = f"setpts=(PTS-STARTPTS)/{speed_value:.3f}"
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1", "-i", str(source_path), "-t", f"{duration:.3f}", "-vf", f"{speed_filter},{vf},fps={fps},trim=duration={duration:.3f},setpts=PTS-STARTPTS", "-an", "-pix_fmt", "yuv420p", str(out)]
    else:
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-i", str(source_path), "-t", f"{duration:.3f}", "-vf", f"{vf},fps={fps}", "-an", "-pix_fmt", "yuv420p", str(out)]
    run_ffmpeg(cmd)
    return True


def write_concat_file(paths: list[Path], concat_file: Path) -> None:
    def esc(path: Path) -> str:
        return str(path).replace("\\", "/").replace("'", "'\\''")
    concat_file.write_text("".join(f"file '{esc(path)}'\n" for path in paths), encoding="utf-8")


def render_project_audio(project: dict[str, Any], *, target_sr: int | None = None, channels: int = 1) -> tuple[np.ndarray, int]:
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
    if target_sr and sr != target_sr:
        final = librosa.resample(final, orig_sr=sr, target_sr=target_sr).astype(np.float32)
        sr = target_sr
    if channels == 2:
        final = np.column_stack([final, final]).astype(np.float32)
    return final, sr


def export_audio_file(project: dict[str, Any], payload: ExportRequest | None = None) -> dict[str, Any]:
    request = payload or ExportRequest()
    audio_format = str(request.audio_format or "wav").strip().lower()
    if audio_format not in {"wav", "mp3", "m4a", "aac", "flac", "ogg", "opus"}:
        raise HTTPException(status_code=400, detail="audio_format must be wav, mp3, m4a, aac, flac, ogg, or opus")
    channels = 2 if int(request.channels or 1) == 2 else 1
    final, sr = render_project_audio(project, target_sr=request.sample_rate, channels=channels)
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    out_dir = project_exports_dir(pid)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = "m4a" if audio_format in {"m4a", "aac"} else "ogg" if audio_format == "opus" else audio_format
    base = out_dir / f"final_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    wav_source = base.with_suffix(".wav")
    sf.write(wav_source, final, sr, subtype="PCM_16")
    if audio_format == "wav":
        out = wav_source
        result = wav_stats(out)
        result.update({"media_type": "audio", "format": "wav", "channels": channels})
    else:
        ffmpeg = locate_ffmpeg(project)
        if not ffmpeg:
            raise HTTPException(status_code=400, detail="ffmpeg was not found. Install ffmpeg on PATH or configure ComfyUI_windows_portable with ffmpeg.exe.")
        out = base.with_suffix(f".{ext}")
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_source)]
        bitrate = sanitize_bitrate(request.audio_bitrate, "192k")
        if audio_format == "mp3":
            cmd += ["-codec:a", "libmp3lame", "-b:a", bitrate]
        elif audio_format in {"m4a", "aac"}:
            cmd += ["-codec:a", "aac", "-b:a", bitrate]
        elif audio_format == "flac":
            cmd += ["-codec:a", "flac"]
        elif audio_format in {"ogg", "opus"}:
            cmd += ["-codec:a", "libopus", "-b:a", sanitize_bitrate(request.audio_bitrate, "128k")]
        run_ffmpeg(cmd + [str(out)])
        try:
            wav_source.unlink()
        except OSError:
            pass
        result = media_stats(out, sample_rate=sr, duration_sec=(len(final) / sr), media_type="audio")
        result.update({"channels": channels, "bitrate": bitrate})
    project["export"] = result
    project.setdefault("exports", []).append(result)
    save_project(project)
    return result


def export_video_file(project: dict[str, Any], payload: ExportRequest) -> dict[str, Any]:
    ffmpeg = locate_ffmpeg(project)
    if not ffmpeg:
        raise HTTPException(status_code=400, detail="ffmpeg was not found. Install ffmpeg on PATH or configure ComfyUI_windows_portable with ffmpeg.exe.")
    video_format = str(payload.video_format or "mp4").strip().lower()
    if video_format not in {"mp4", "webm", "mov"}:
        raise HTTPException(status_code=400, detail="video_format must be mp4, webm, or mov")
    width, height, orientation = export_dimensions(project, payload)
    fps = max(1, min(60, int(payload.fps or 30)))
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    out_dir = project_exports_dir(pid)
    work_dir = out_dir / f"work_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    work_dir.mkdir(parents=True, exist_ok=True)
    final_audio, sr = render_project_audio(project, target_sr=int(payload.sample_rate or 48000), channels=2)
    duration = len(final_audio) / float(sr)
    audio_wav = work_dir / "audio.wav"
    sf.write(audio_wav, final_audio, sr, subtype="PCM_16")
    ranges = group_time_ranges(project)
    speed_points = normalized_video_speed_envelope(project)
    speed_curve_applied = any(abs(point.get("speed", 1.0) - 1.0) > 0.001 for point in speed_points)
    segments: list[Path] = []
    current = 0.0
    segment_index = 1
    for index, (group, start, end) in enumerate(ranges, start=1):
        if start > current + 0.05:
            # Fill timeline gaps with the next group's still image/video if available; otherwise skip to the group.
            current = start
        range_end = min(end, duration)
        if range_end - current <= 0:
            continue
        for seg_start, seg_end in split_range_by_speed_envelope(current, range_end, speed_points):
            segment_duration = max(0.1, seg_end - seg_start)
            if segment_duration <= 0:
                continue
            segment_speed = video_speed_at(speed_points, seg_start + segment_duration / 2.0)
            segment_path = work_dir / f"segment_{segment_index:04d}.mp4"
            segment_index += 1
            if build_visual_segment(project, group, segment_duration, width, height, fps, payload.video_fit, segment_path, speed=segment_speed):
                segments.append(segment_path)
                current = seg_end
        if current >= duration:
            break
    if not segments:
        raise HTTPException(status_code=400, detail="No group video/image assets found for video export. Generate at least one group image or video first.")
    if current < duration - 0.05:
        last_group = ranges[-1][0] if ranges else {}
        for seg_start, seg_end in split_range_by_speed_envelope(current, duration, speed_points):
            tail_path = work_dir / f"segment_{segment_index:04d}.mp4"
            segment_index += 1
            tail_duration = max(0.1, seg_end - seg_start)
            tail_speed = video_speed_at(speed_points, seg_start + tail_duration / 2.0)
            if build_visual_segment(project, last_group, tail_duration, width, height, fps, payload.video_fit, tail_path, speed=tail_speed):
                segments.append(tail_path)
    concat_file = work_dir / "segments.txt"
    write_concat_file(segments, concat_file)
    visual_mp4 = work_dir / "visual.mp4"
    run_ffmpeg([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(visual_mp4)])
    ext = "mov" if video_format == "mov" else "webm" if video_format == "webm" else "mp4"
    out = out_dir / f"final_video_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"
    if video_format == "webm":
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(visual_mp4), "-i", str(audio_wav), "-t", f"{duration:.3f}", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34" if payload.video_quality == "small" else "30", "-c:a", "libopus", "-b:a", sanitize_bitrate(payload.audio_bitrate, "128k"), "-shortest", str(out)]
    else:
        crf = "28" if payload.video_quality == "small" else "18" if payload.video_quality == "high" else "23"
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(visual_mp4), "-i", str(audio_wav), "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", sanitize_bitrate(payload.audio_bitrate, "192k"), "-movflags", "+faststart", "-shortest", str(out)]
    run_ffmpeg(cmd)
    try:
        shutil.rmtree(work_dir)
    except OSError:
        pass
    result = media_stats(out, sample_rate=sr, duration_sec=duration, media_type="video")
    result.update({
        "width": width,
        "height": height,
        "orientation": orientation,
        "fps": fps,
        "container": video_format,
        "visual_segments": len(segments),
        "fit": str(payload.video_fit or "cover"),
        "speed_curve_applied": speed_curve_applied,
        "speed_curve_points": len(speed_points),
        "timeline_fidelity": "group ranges from chunk timings; group video assets are split at video speed-envelope points, speed-adjusted with ffmpeg setpts, then looped/trimmed to preserve the audio timeline",
    })
    project["export"] = result
    project.setdefault("exports", []).append(result)
    save_project(project)
    return result


def export_project_with_settings(project: dict[str, Any], payload: ExportRequest | None = None) -> dict[str, Any]:
    request = payload or ExportRequest()
    export_type = str(request.export_type or "audio").strip().lower()
    if export_type in {"video", "video_audio", "video_with_audio"}:
        return export_video_file(project, request)
    return export_audio_file(project, request)


def export_project(project: dict[str, Any]) -> dict[str, Any]:
    out = project_exports_dir(project.get("id") or active_project_id()) / f"final_{int(time.time())}.wav"
    final, sr = render_project_audio(project)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, final, sr, subtype="PCM_16")
    result = wav_stats(out)
    result.update({"media_type": "audio", "format": "wav", "channels": 1})
    project["export"] = result
    project.setdefault("exports", []).append(result)
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
        "POST /api/project/arrangement/video": ("POST", "/api/project/arrangement/video"),
        "POST /api/project/groups/ai": ("POST", "/api/project/groups/ai"),
        "PATCH /api/project/groups/{group_id}": ("PATCH", "/api/project/groups/{group_id}"),
        "POST /api/project/groups/{group_id}/image": ("POST", "/api/project/groups/{group_id}/image"),
        "POST /api/project/groups/{group_id}/video": ("POST", "/api/project/groups/{group_id}/video"),
        "POST /api/project/groups/images": ("POST", "/api/project/groups/images"),
        "POST /api/project/groups/videos": ("POST", "/api/project/groups/videos"),
        "GET /api/comfyui/status": ("GET", "/api/comfyui/status"),
        "GET /api/xai/imagine-video/diagnostics": ("GET", "/api/xai/imagine-video/diagnostics"),
        "GET /api/image": ("GET", "/api/image"),
        "GET /api/video": ("GET", "/api/video"),
        "GET /api/health": ("GET", "/api/health"),
    }
    registered: dict[str, set[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = set(getattr(route, "methods", []) or [])
        if path:
            registered.setdefault(path, set()).update(methods)
    return {
        name: {"available": method in registered.get(path, []), "path": path, "method": method}
        for name, (method, path) in expected.items()
    } | {"registered_api_paths": {path: sorted(methods) for path, methods in registered.items() if path.startswith("/api/")}}


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


@app.get("/api/comfyui/status")
def get_comfyui_status(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    settings = image_settings(project)
    return comfyui_status(settings)


@app.get("/api/comfyui/animatediff/diagnostics")
def get_comfyui_animatediff_diagnostics(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    settings = image_settings(project)
    health = comfyui_health(settings)
    diagnostics = animatediff_environment_diagnostics(settings) if health.get("running") else {
        "ready": False,
        "blockers": [f"ComfyUI is not reachable at {comfyui_url(settings)}: {health.get('error') or 'not running'}"],
        "selected_sd15_checkpoint": find_sd15_checkpoint(settings),
        "selected_motion_model": ANIMATEDIFF_MOTION_MODEL if ANIMATEDIFF_MOTION_MODEL in comfyui_model_files(settings, "animatediff_models", (".safetensors", ".ckpt", ".pt", ".pth")) else "",
        "checkpoints": comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt")),
        "motion_models": comfyui_model_files(settings, "animatediff_models", (".safetensors", ".ckpt", ".pt", ".pth")),
        "nodes": {"object_info_available": False, "object_info_error": health.get("error") or "ComfyUI is not running"},
    }
    return {"comfyui": {"running": bool(health.get("running")), "url": comfyui_url(settings)}, "animatediff": diagnostics}


@app.get("/api/comfyui/animatediff-sdxl/diagnostics")
def get_comfyui_animatediff_sdxl_diagnostics(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    settings = image_settings(project)
    health = comfyui_health(settings)
    diagnostics = animatediff_sdxl_environment_diagnostics(settings) if health.get("running") else {
        "ready": False,
        "implemented": False,
        "blockers": [f"ComfyUI is not reachable at {comfyui_url(settings)}: {health.get('error') or 'not running'}"],
        "warnings": ["Start ComfyUI, then reload this endpoint to inspect live AnimateDiff-Evolved/HotshotXL node schemas."],
        "selected_sdxl_checkpoint": find_sdxl_checkpoint(settings),
        "selected_motion_model": find_sdxl_motion_model(settings),
        "motion_model_env": ANIMATEDIFF_SDXL_ENV_MODEL,
        "known_motion_model_candidates": list(ANIMATEDIFF_SDXL_MODEL_CANDIDATES),
        "checkpoints": comfyui_model_files(settings, "checkpoints", (".safetensors", ".ckpt")),
        "motion_models": comfyui_model_files(settings, "animatediff_models", (".safetensors", ".ckpt", ".pt", ".pth")),
        "nodes": {"object_info_available": False, "object_info_error": health.get("error") or "ComfyUI is not running"},
    }
    return {"comfyui": {"running": bool(health.get("running")), "url": comfyui_url(settings)}, "animatediff_sdxl": diagnostics}


@app.get("/api/xai/imagine-video/diagnostics")
def get_xai_imagine_video_diagnostics(project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    return {"xai_imagine_video": grok_imagine_video_diagnostics(project)}


def project_has_active_tasks(project_id: str) -> bool:
    pid = safe_project_id(project_id)
    with _queue_lock:
        return any(task.get("project_id") == pid and task.get("status") in {"queued", "running"} for task in _tasks)


def validate_grok_groups_enqueue_request(project: dict[str, Any], payload: VideoGroupsAiRequest) -> None:
    chunks = ordered_project_chunks(project)
    if not chunks:
        raise HTTPException(status_code=400, detail="Project has no chunks to group")
    if not any(clean_text(chunk.get("text", "")) for chunk in chunks):
        raise HTTPException(status_code=400, detail="Project chunks are empty")
    project_id = safe_project_id(str(project.get("id") or active_project_id()))
    if not resolve_xai_api_key(project, project_id) and not payload.fallback_on_error:
        raise HTTPException(status_code=400, detail="Grok/xAI API key is not configured")
    strategy = (payload.strategy or "auto").strip().lower()
    if strategy not in {"single", "batched", "auto"}:
        raise HTTPException(status_code=400, detail="strategy must be single, batched, or auto")


def image_file_response(path: str) -> FileResponse:
    if not path:
        raise HTTPException(status_code=400, detail="Image path is required")
    resolved = resolve_user_path(path, must_exist=True)
    if not resolved or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")
    suffix = resolved.suffix.lower()
    if suffix not in {".svg", ".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported image file type")
    allowed_roots = [PROJECTS_ROOT.resolve(), PROJECTS_DIR.resolve()]
    try:
        for root in allowed_roots:
            try:
                resolved.resolve().relative_to(root)
                break
            except ValueError:
                continue
        else:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=403, detail="Image path is outside project storage")
    media_types = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    return FileResponse(str(resolved), media_type=media_types[suffix], filename=resolved.name)


def video_file_response(path: str) -> FileResponse:
    if not path:
        raise HTTPException(status_code=400, detail="Video path is required")
    resolved = resolve_user_path(path, must_exist=True)
    if not resolved or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    suffix = resolved.suffix.lower()
    if suffix not in {".mp4", ".webm", ".gif", ".mov"}:
        raise HTTPException(status_code=400, detail="Unsupported video file type")
    allowed_roots = [PROJECTS_ROOT.resolve(), PROJECTS_DIR.resolve()]
    try:
        for root in allowed_roots:
            try:
                resolved.resolve().relative_to(root)
                break
            except ValueError:
                continue
        else:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=403, detail="Video path is outside project storage")
    media_types = {".mp4": "video/mp4", ".webm": "video/webm", ".gif": "image/gif", ".mov": "video/quicktime"}
    return FileResponse(str(resolved), media_type=media_types[suffix], filename=resolved.name)


def enqueue_group_image_task(project: dict[str, Any], group_id: str, *, force: bool = False) -> dict[str, Any] | None:
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    group = find_video_group(project, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Video group not found")
    existing = active_image_task_for_group(pid, group_id)
    if existing and not force:
        return existing
    task = enqueue_task(
        "image_group",
        project_id=pid,
        payload={"group_id": group_id},
        label=f"Image: {group.get('title') or group_id}",
        stage="queued",
    )
    return task


def enqueue_group_video_task(project: dict[str, Any], group_id: str, *, force: bool = False) -> dict[str, Any] | None:
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    group = find_video_group(project, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Video group not found")
    if not isinstance(group.get("image"), dict) or not group.get("image", {}).get("path"):
        backend_label = video_i2v_backend_label(video_i2v_settings(project))
        raise HTTPException(status_code=400, detail=f"Generate the group image before {backend_label} video")
    existing = active_video_task_for_group(pid, group_id)
    if existing and not force:
        return existing
    task = enqueue_task(
        "video_group",
        project_id=pid,
        payload={"group_id": group_id},
        label=f"{video_i2v_backend_label(video_i2v_settings(project))} video: {group.get('title') or group_id}",
        stage="queued",
    )
    return task


def renumber_chunks(project: dict[str, Any]) -> None:
    project["chunks"] = sorted([chunk for chunk in project.get("chunks", []) if isinstance(chunk, dict)], key=lambda c: c.get("order", 0))
    for idx, chunk in enumerate(project["chunks"]):
        chunk["order"] = idx


def create_chunk_dict(project: dict[str, Any], payload: ChunkCreate, order: int) -> dict[str, Any]:
    text = repair_mojibake_text(payload.text or "")[0]
    tts_text = repair_mojibake_text(payload.tts_text)[0] if payload.tts_text is not None else text
    chunk = {
        "id": uuid.uuid4().hex[:12],
        "order": order,
        "text": text,
        "boundary_type": "sentence",
        "pause_after": clamp_pause(payload.pause_after),
        "audio_path": "",
        "audio_url": "",
        "versions": [],
        "selected_version_id": "",
        "duration_sec": 0.0,
        "generated_at": None,
    }
    if tts_text and compact_stress_validation_text(tts_text) == compact_stress_validation_text(text):
        chunk["tts_text"] = unicodedata.normalize("NFC", tts_text)
        chunk["stressed_text"] = chunk["tts_text"]
        chunk["stress_source"] = "manual" if chunk["tts_text"] != text else "original"
    normalize_chunk_pauses(project, chunk)
    return chunk


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
    project["full_text"] = repair_mojibake_text(payload.initial_text or "")[0]
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
    incoming = repair_mojibake_text(payload.text or "")[0]
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
    project["full_text"] = repair_mojibake_text(payload.text)[0]
    set_status(project, "Text saved")
    return enrich_project(project)


@app.post("/api/project/settings")
def update_settings(payload: SettingsUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    data = payload.dict(exclude_unset=True)
    xai_secret_action = "kept"
    if "xai_api_key" in data:
        secrets = load_project_secrets(pid)
        xai_value = data.pop("xai_api_key")
        clean_key = str(xai_value or "").strip()
        if clean_key:
            secrets["xai_api_key"] = clean_key
            xai_secret_action = "saved"
        else:
            secrets.pop("xai_api_key", None)
            xai_secret_action = "cleared"
        save_project_secrets(pid, secrets)
    if "image_comfyui_autostart" in data:
        project.setdefault("settings", {})["image_comfyui_autostart_user_set"] = True
    for key, value in data.items():
        if value is not None:
            project["settings"][key] = value
    apply_safe_secret_settings(project, pid)
    normalize_arrangement(project)
    if xai_secret_action == "saved":
        status_message = f"Settings saved · Grok/xAI project key saved for {pid}"
    elif xai_secret_action == "cleared":
        status_message = f"Settings saved · Grok/xAI project key cleared for {pid}"
    else:
        status_message = "Settings saved · Grok/xAI project key unchanged"
    set_status(project, status_message)
    return enrich_project(project)


@app.post("/api/project/arrangement/music")
def update_music_arrangement(payload: MusicArrangementUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    music = project.setdefault("arrangement", {}).setdefault("music", {})
    data = payload.dict(exclude_unset=True)
    if "mode" in data and data["mode"] is not None:
        music["mode"] = data["mode"] if data["mode"] in {"loop", "once", "chain_loop"} else "loop"
    if "volume_envelope" in data and payload.volume_envelope is not None:
        music["volume_envelope"] = [point.dict() for point in payload.volume_envelope]
    for key in ("sources", "lanes", "tracks"):
        if key in data and data[key] is not None:
            music[key] = data[key]
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


@app.post("/api/project/arrangement/video")
def update_video_arrangement(payload: VideoArrangementUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    video = project.setdefault("arrangement", {}).setdefault("video", {})
    data = payload.dict(exclude_unset=True)
    if "speed_envelope" in data and payload.speed_envelope is not None:
        video["speed_envelope"] = [point.dict() for point in payload.speed_envelope]
    normalize_arrangement(project)
    set_status(project, "Video playback speed automation saved")
    return enrich_project(project)


@app.post("/api/project/groups/ai")
def generate_ai_video_groups(payload: VideoGroupsAiRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    if payload.exclude_people_from_images is None:
        payload.exclude_people_from_images = bool(project.get("settings", {}).get("image_exclude_people", DEFAULT_SETTINGS["image_exclude_people"]))
    project.setdefault("settings", {})["image_exclude_people"] = bool(payload.exclude_people_from_images)
    validate_grok_groups_enqueue_request(project, payload)
    existing = active_task_by_kind_project("grok_groups", pid)
    if existing:
        set_status(project, "Grok AI grouping already queued/running", True)
        return {"queued_task": existing, "queue": queue_snapshot(pid), "progress": progress_snapshot(), "project": enrich_project(load_project(pid))}
    payload_data = payload.dict()
    task = enqueue_task(
        "grok_groups",
        project_id=pid,
        payload=payload_data,
        label="Grok AI grouping",
        stage="queued",
    )
    set_status(project, "Grok AI grouping queued", True)
    return {"queued_task": task, "queue": queue_snapshot(pid), "progress": progress_snapshot(), "project": enrich_project(load_project(pid))}


@app.patch("/api/project/groups/{group_id}")
def update_group_endpoint(group_id: str, payload: GroupUpdate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    group = update_group_prompts(project, group_id, payload)
    set_status(project, f"Group prompts saved for {group.get('title') or group_id}")
    return {"group": group, "project": enrich_project(load_project(pid))}


@app.post("/api/project/groups")
def create_group_endpoint(payload: GroupCreate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    video = project.setdefault("arrangement", {}).setdefault("video", {})
    groups = video.setdefault("groups", [])
    insert_at = len(groups)
    if payload.insert_after_group_id:
        existing_idx = next((idx for idx, group in enumerate(groups) if isinstance(group, dict) and group.get("id") == payload.insert_after_group_id), None)
        if existing_idx is not None:
            insert_at = existing_idx + 1
    valid_ids = set(chunk_order_ids(ordered_project_chunks(project)))
    chunk_ids = [str(chunk_id) for chunk_id in payload.chunk_ids if str(chunk_id) in valid_ids]
    group = create_video_group_dict(payload.title or f"Manual group {insert_at + 1}", payload.summary, chunk_ids, order=insert_at, source="manual")
    groups.insert(insert_at, group)
    video["groups"] = renumber_video_groups(groups)
    normalize_arrangement(project)
    set_status(project, f"Group added: {group.get('title')}")
    return enrich_project(project)


@app.delete("/api/project/groups/{group_id}")
def delete_group_endpoint(group_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    video = project.setdefault("arrangement", {}).setdefault("video", {})
    groups = video.setdefault("groups", [])
    next_groups = [group for group in groups if not (isinstance(group, dict) and group.get("id") == group_id)]
    if len(next_groups) == len(groups):
        raise HTTPException(status_code=404, detail="Video group not found")
    video["groups"] = renumber_video_groups(next_groups)
    normalize_arrangement(project)
    set_status(project, f"Group deleted: {group_id}")
    return enrich_project(project)


@app.post("/api/project/groups/{group_id}/move")
def move_group_endpoint(group_id: str, payload: GroupMoveRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
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
    video["groups"] = renumber_video_groups(groups)
    normalize_arrangement(project)
    set_status(project, "Group order updated")
    return enrich_project(project)


@app.post("/api/project/groups/{group_id}/image")
def generate_group_image_endpoint(group_id: str, payload: GroupImageRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    task = enqueue_group_image_task(project, group_id, force=payload.force)
    set_status(project, f"Image generation queued for {group_id}", True)
    return {"queued_tasks": [task] if task else [], "queue": queue_snapshot(pid), "progress": progress_snapshot(), "project": enrich_project(load_project(pid))}


@app.post("/api/project/groups/{group_id}/video")
def generate_group_video_endpoint(group_id: str, payload: GroupVideoRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    task = enqueue_group_video_task(project, group_id, force=payload.force)
    set_status(project, f"{video_i2v_backend_label(video_i2v_settings(project))} video generation queued for {group_id}", True)
    return {"queued_tasks": [task] if task else [], "queue": queue_snapshot(pid), "progress": progress_snapshot(), "project": enrich_project(load_project(pid))}


@app.post("/api/project/groups/images")
def generate_group_images_endpoint(payload: GroupImagesRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
    queued: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict) or not group.get("id"):
            continue
        image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
        has_ready_image = bool(image_meta.get("path")) and image_meta.get("status") == "ready"
        if payload.missing_only and has_ready_image and not payload.force:
            continue
        task = enqueue_group_image_task(project, str(group.get("id")), force=payload.force)
        if task:
            queued.append(task)
    set_status(project, f"Queued {len(queued)} image generation task(s)", bool(queued))
    return {"queued_tasks": queued, "skipped": [], "skipped_count": 0, "queue": queue_snapshot(pid), "progress": progress_snapshot(), "project": enrich_project(load_project(pid))}


@app.post("/api/project/groups/videos")
def generate_group_videos_endpoint(payload: GroupVideosRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    pid = safe_project_id(str(project.get("id") or active_project_id()))
    groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
    queued: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict) or not group.get("id"):
            skipped.append({"group_id": str(group.get("id") if isinstance(group, dict) else ""), "reason": "invalid group"})
            continue
        group_id = str(group.get("id"))
        image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
        has_ready_image = bool(image_meta.get("path")) and str(image_meta.get("status") or "ready").lower() in {"ready", "done", "fallback"}
        if not has_ready_image:
            skipped.append({"group_id": group_id, "reason": "missing generated image"})
            continue
        video_meta = group.get("video") if isinstance(group.get("video"), dict) else {}
        has_ready_video = bool(video_meta.get("path")) and str(video_meta.get("status") or "ready").lower() in {"ready", "done"}
        if payload.missing_only and has_ready_video and not payload.force:
            skipped.append({"group_id": group_id, "reason": "video already exists"})
            continue
        try:
            task = enqueue_group_video_task(project, group_id, force=payload.force)
        except HTTPException as exc:
            skipped.append({"group_id": group_id, "reason": str(exc.detail)})
            continue
        if task:
            queued.append(task)
    set_status(project, f"Queued {len(queued)} {video_i2v_backend_label(video_i2v_settings(project))} video generation task(s), skipped {len(skipped)}", bool(queued))
    return {"queued_tasks": queued, "skipped": skipped, "skipped_count": len(skipped), "queue": queue_snapshot(pid), "progress": progress_snapshot(), "project": enrich_project(load_project(pid))}


@app.post("/api/chunks/split")
def split_chunks(payload: SplitRequest, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    try:
        # Strict two-phase flow:
        # 1) perform the normal deterministic splitter and assign final chunk ids/order/pauses;
        # 2) optionally ask Grok to post-process only those existing chunk texts with stress marks.
        # Grok never receives the full source text and cannot influence boundaries/count/order.
        chunks = []
        split_min = clamp_pause(payload.split_pause_after_min)
        split_max = clamp_pause(payload.split_pause_after_max)
        if split_max < split_min:
            split_min, split_max = split_max, split_min
        source_text = repair_mojibake_text(payload.text)[0]
        split_items = split_text_into_chunks(source_text, payload.max_chars)
        for idx, item in enumerate(split_items):
            text = str(item.get("text") or "")
            boundary_type = str(item.get("boundary_type") or "sentence")
            pause_min, pause_max = pause_range_for_boundary(boundary_type, split_min, split_max)
            pause_after = stable_split_pause_after(project, text, idx, pause_min, pause_max, boundary_type)
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
            normalize_chunk_pauses(project, chunks[-1])
        stress_note = "disabled"
        try:
            stress_marked, stress_note = add_ai_stress_to_chunks_safe(project, chunks)
        except Exception as exc:
            stress_marked = 0
            detail = truncate_text(str(exc), 220)
            stress_note = f"Grok stress marking skipped after non-fatal error: {type(exc).__name__}: {detail}; kept original chunks"
            LOGGER.warning("Optional Grok stress marking block failed during chunk split; keeping original chunks: %s: %s", type(exc).__name__, exc)
            ensure_chunk_stress_fields(chunks, source="original")
        for chunk in chunks:
            sanitize_split_chunk_for_response(chunk)
        project["full_text"] = source_text
        project["chunks"] = chunks
        status = f"Standard split into {len(chunks)} chunks"
        if stress_note != "disabled":
            status += f" · {stress_note}"
        set_status(project, status)
        return enrich_project(project)
    except Exception as exc:
        detail = truncate_text(str(exc), 400)
        LOGGER.exception("Chunk split failed: %s: %s", type(exc).__name__, exc)
        set_status(project, f"Chunk split failed: {type(exc).__name__}: {detail}")
        raise HTTPException(status_code=400, detail=f"Chunk split failed: {type(exc).__name__}: {detail}") from exc


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


@app.post("/api/chunks")
def create_chunk_endpoint(payload: ChunkCreate, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    chunks = sorted(project.get("chunks", []), key=lambda c: c.get("order", 0))
    insert_at = len(chunks)
    if payload.insert_after_chunk_id:
        idx = next((i for i, chunk in enumerate(chunks) if chunk.get("id") == payload.insert_after_chunk_id), None)
        if idx is not None:
            insert_at = idx + 1
    elif payload.order is not None:
        insert_at = max(0, min(len(chunks), int(payload.order)))
    chunk = create_chunk_dict(project, payload, insert_at)
    chunks.insert(insert_at, chunk)
    project["chunks"] = chunks
    renumber_chunks(project)
    normalize_arrangement(project)
    set_status(project, f"Chunk added at position {insert_at + 1}")
    return enrich_project(project)


@app.delete("/api/chunks/{chunk_id}")
def delete_chunk_endpoint(chunk_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    before = len(project.get("chunks", []))
    project["chunks"] = [chunk for chunk in project.get("chunks", []) if chunk.get("id") != chunk_id]
    if len(project["chunks"]) == before:
        raise HTTPException(status_code=404, detail="Chunk not found")
    for group in project.setdefault("arrangement", {}).setdefault("video", {}).setdefault("groups", []):
        if isinstance(group, dict) and isinstance(group.get("chunk_ids"), list):
            group["chunk_ids"] = [item for item in group["chunk_ids"] if item != chunk_id]
    renumber_chunks(project)
    normalize_arrangement(project)
    set_status(project, "Chunk deleted")
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
def queue_export(payload: ExportRequest | None = None, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    request = payload or ExportRequest()
    task = enqueue_task("export", project_id=project.get("id"), payload=request.dict(), label="Export video" if str(request.export_type).startswith("video") else f"Export {request.audio_format.upper()}")
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
    repaired_text = repair_mojibake_text(payload.text)[0] if payload.text is not None else None
    if repaired_text is not None and repaired_text != chunk.get("text"):
        chunk["text"] = repaired_text
        if payload.tts_text is None:
            chunk.pop("tts_text", None)
            chunk.pop("stressed_text", None)
            chunk.pop("stress_source", None)
        chunk["audio_path"] = ""
        chunk["audio_url"] = ""
        chunk["versions"] = []
        chunk["selected_version_id"] = ""
        chunk["duration_sec"] = 0.0
    if payload.tts_text is not None:
        repaired_tts_text = repair_mojibake_text(payload.tts_text)[0]
        base_text = str(chunk.get("text") or "")
        if compact_stress_validation_text(repaired_tts_text) != compact_stress_validation_text(base_text):
            raise HTTPException(status_code=400, detail="TTS text may only add or remove stress marks; edit Original text to rewrite content")
        chunk["tts_text"] = unicodedata.normalize("NFC", repaired_tts_text)
        chunk["stressed_text"] = chunk["tts_text"]
        chunk["stress_source"] = "manual" if chunk["tts_text"] != base_text else "original"
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
def export_endpoint(payload: ExportRequest | None = None, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    project = load_project(project_id)
    request = payload or ExportRequest()
    task = enqueue_task("export", project_id=project.get("id"), payload=request.dict(), label="Export video" if str(request.export_type).startswith("video") else f"Export {request.audio_format.upper()}")
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
    media_type = mimetypes.guess_type(str(resolved))[0] or "audio/wav"
    return FileResponse(str(resolved), media_type=media_type, filename=resolved.name)


@app.get("/api/image")
def image(path: str) -> FileResponse:
    return image_file_response(path)


@app.get("/api/video")
def video(path: str) -> FileResponse:
    return video_file_response(path)


class NoStoreStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        requested_path = (path or "").replace("\\", "/").lstrip("/")
        if requested_path in {"", "."} or requested_path.endswith("/"):
            requested_path = "index.html"
        if requested_path in {"app.js", "style.css", "index.html"}:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["ETag"] = f'"xtts-studio-{STUDIO_BUILD}-{requested_path}"'
            response.headers["X-XTTS-Studio-Build"] = STUDIO_BUILD
        return response


app.mount("/studio", NoStoreStaticFiles(directory=str(STATIC_DIR), html=True), name="studio")

