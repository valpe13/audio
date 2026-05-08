from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from audio_workflow import WorkflowResult, generate_long_form_audio
from fish_backend import FishSpeechBackend, TTSRequest


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
EXAMPLE_CONFIG_PATH = BASE_DIR / "config.example.json"


def load_config() -> dict[str, Any]:
    source = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    with source.open("r", encoding="utf-8") as file:
        config = json.load(file)

    output_dir = Path(str(config.get("output_dir", "outputs")))
    if not output_dir.is_absolute():
        output_dir = BASE_DIR / output_dir
    config["output_dir"] = str(output_dir)
    return config


config = load_config()
backend = FishSpeechBackend(config)
app = FastAPI(title="Local Fish Speech API", version="0.1.0")


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize")
    language: str = Field("ru", description="Language code, defaults to Russian")
    speaker: str | None = Field(None, description="Optional voice/speaker id")
    seed: int | None = Field(None, description="Optional generation seed")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    top_p: float = Field(0.7, ge=0.0, le=1.0)
    reference_audio: str | None = Field(None, description="Optional local reference audio path")
    reference_text: str | None = Field(None, description="Optional transcript for reference audio")
    return_file: bool = Field(False, description="Return WAV bytes directly instead of JSON")


class SynthesizeResponse(BaseModel):
    ok: bool
    backend: str
    audio_path: str
    filename: str
    elapsed_seconds: float
    note: str | None = None


class LongFormRequest(SynthesizeRequest):
    max_chars: int = Field(420, ge=120, le=1200, description="Maximum cleaned text characters per synthesis chunk")
    export_mp3: bool = Field(True, description="Also export MP3 when ffmpeg is available")
    preset: str | None = Field(None, description="Realism preset: sleep_safe, natural_lecture, or experimental_realism")
    breath_amount: float | None = Field(None, ge=0.0, le=1.0)
    room_tone: bool | None = Field(None)
    pitch_drift: float | None = Field(None, ge=0.0, le=1.0)
    loudness_variation: float | None = Field(None, ge=0.0, le=1.5)


class LongFormResponse(BaseModel):
    ok: bool
    backend: str
    output_wav: str
    output_mp3: str | None
    chunks: int
    duration_seconds: float
    manifest_path: str
    note: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "backend": backend.backend_name,
        "output_dir": config["output_dir"],
    }


@app.post("/v1/tts", response_model=SynthesizeResponse)
def synthesize(payload: SynthesizeRequest):
    started = time.perf_counter()
    filename = f"fish_speech_{uuid4().hex}.wav"
    output_path = Path(config["output_dir"]) / filename

    try:
        backend.synthesize(
            TTSRequest(
                text=payload.text,
                language=payload.language,
                speaker=payload.speaker,
                seed=payload.seed,
                temperature=payload.temperature,
                top_p=payload.top_p,
                reference_audio=payload.reference_audio,
                reference_text=payload.reference_text,
            ),
            output_path,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TTS failed: {exc}") from exc

    if payload.return_file:
        return FileResponse(output_path, media_type="audio/wav", filename=filename)

    return SynthesizeResponse(
        ok=True,
        backend=backend.backend_name,
        audio_path=str(output_path),
        filename=filename,
        elapsed_seconds=round(time.perf_counter() - started, 3),
        note="Placeholder WAV generated. Wire fish_backend.py to real Fish Speech for inference."
        if backend.backend_name == "placeholder"
        else None,
    )


@app.post("/v1/long-form", response_model=LongFormResponse)
def synthesize_long_form(payload: LongFormRequest):
    filename = f"fish_speech_longform_{uuid4().hex}.wav"
    output_path = Path(config["output_dir"]) / filename

    try:
        result: WorkflowResult = generate_long_form_audio(
            payload.text,
            config,
            output_path,
            language=payload.language,
            speaker=payload.speaker,
            seed=payload.seed or 42,
            max_chars=payload.max_chars,
            export_mp3=payload.export_mp3,
            preset=payload.preset,
            realism_overrides={
                "breath_amount": payload.breath_amount,
                "room_tone": payload.room_tone,
                "pitch_drift_percent": payload.pitch_drift,
                "loudness_variation_db": payload.loudness_variation,
            },
            reference_audio=payload.reference_audio,
            reference_text=payload.reference_text,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Long-form TTS failed: {exc}") from exc

    return LongFormResponse(**asdict(result))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host=str(config.get("host", "127.0.0.1")), port=int(config.get("port", 7865)))

