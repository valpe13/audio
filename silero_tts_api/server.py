from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from silero_backend import DEFAULT_OUTPUT_DIR, DEFAULT_SAMPLE_RATE, DEFAULT_SPEAKER, REALISM_PRESETS, SileroTTSBackend


app = FastAPI(title="Local Silero RU TTS API", version="0.1.0")
backend = SileroTTSBackend(model_id="v4_ru", language="ru", device="cpu")


class SileroSynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    speaker: str = Field(DEFAULT_SPEAKER)
    sample_rate: int = Field(DEFAULT_SAMPLE_RATE)
    output_path: str | None = Field(None, description="Optional local output WAV path")
    return_file: bool = Field(False)
    realism_enabled: bool = Field(False)
    preset: str = Field("sleep_safe")
    pause_scale: float | None = Field(None)
    breath_amount: float | None = Field(None)
    room_tone: bool | None = Field(None)
    loudness_variation: float | None = Field(None)
    seed: int = Field(42)
    speed: float | None = Field(None)
    soften: bool | None = Field(None)
    target_peak: float | None = Field(None)
    tone_softening: float | None = Field(None)
    sleep_softness: float | None = Field(None)


@app.get("/health")
def health():
    return {
        "ok": True,
        "backend": "silero_tts_torch_hub",
        "model_id": backend.model_id,
        "language": backend.language,
        "device": backend.device,
        "speakers": backend.speakers,
        "realism_presets": list(REALISM_PRESETS.keys()),
    }


@app.get("/v1/speakers")
def speakers():
    return {"ok": True, "speakers": backend.speakers}


@app.post("/v1/tts")
def synthesize(payload: SileroSynthesizeRequest):
    started = time.perf_counter()
    output_path = Path(payload.output_path) if payload.output_path else DEFAULT_OUTPUT_DIR / f"silero_ru_{uuid4().hex}.wav"
    try:
        result = backend.synthesize(
            text=payload.text,
            output_path=output_path,
            speaker=payload.speaker,
            sample_rate=payload.sample_rate,
            realism_enabled=payload.realism_enabled,
            preset=payload.preset,
            pause_scale=payload.pause_scale,
            breath_amount=payload.breath_amount,
            room_tone=payload.room_tone,
            loudness_variation=payload.loudness_variation,
            seed=payload.seed,
            speed=payload.speed,
            soften=payload.soften,
            target_peak=payload.target_peak,
            tone_softening=payload.tone_softening,
            sleep_softness=payload.sleep_softness,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Silero TTS failed: {exc}") from exc

    if payload.return_file:
        return FileResponse(result.audio_path, media_type="audio/wav", filename=Path(result.audio_path).name)

    data = asdict(result)
    data["request_elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return data


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=7866)

