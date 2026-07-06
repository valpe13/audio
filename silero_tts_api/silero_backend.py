from __future__ import annotations

import json
import math
import re
import tempfile
import time
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

try:
    from xtts_api.pronunciation_preprocess import load_pronunciation_dictionary, preprocess_tts_text
except ImportError:  # pragma: no cover - standalone/package fallback
    load_pronunciation_dictionary = None
    preprocess_tts_text = None


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs"
DEFAULT_MODEL_ID = "v4_ru"
DEFAULT_LANGUAGE = "ru"
DEFAULT_SPEAKER = "baya"
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_DEVICE = "cpu"
KNOWN_RU_SPEAKERS = ["aidar", "baya", "kseniya", "xenia", "eugene", "random"]
DEFAULT_PRONUNCIATION_DICTIONARY = BASE_DIR.parent / "xtts_api" / "pronunciation_dictionary.json"


REALISM_PRESETS: dict[str, dict[str, Any]] = {
    "sleep_soft": {
        "pause_scale": 0.9,
        "breath_amount": 0.0,
        "room_tone": True,
        "room_tone_level": 0.62,
        "loudness_variation": 0.11,
        "comma_pause_ms": 170,
        "period_pause_ms": 455,
        "paragraph_pause_ms": 690,
        "micro_pause_ms": 82,
        "micro_pause_probability": 0.22,
        "target_peak": 0.76,
        "soften": True,
        "tone_softening": 0.34,
        "sleep_softness": 0.55,
        "chunk_fade_ms": 18,
    },
    "sleep_safe": {
        "pause_scale": 0.82,
        "breath_amount": 0.0,
        "room_tone": True,
        "room_tone_level": 1.0,
        "loudness_variation": 0.18,
        "comma_pause_ms": 155,
        "period_pause_ms": 430,
        "paragraph_pause_ms": 620,
        "micro_pause_ms": 70,
        "micro_pause_probability": 0.18,
        "target_peak": 0.86,
        "soften": False,
        "tone_softening": 0.0,
        "sleep_softness": 0.0,
        "chunk_fade_ms": 10,
    },
    "natural_lecture": {
        "pause_scale": 1.0,
        "breath_amount": 0.035,
        "room_tone": True,
        "room_tone_level": 1.0,
        "loudness_variation": 0.35,
        "comma_pause_ms": 190,
        "period_pause_ms": 520,
        "paragraph_pause_ms": 760,
        "micro_pause_ms": 85,
        "micro_pause_probability": 0.28,
        "target_peak": 0.88,
        "soften": False,
        "tone_softening": 0.0,
        "sleep_softness": 0.0,
        "chunk_fade_ms": 10,
    },
    "experimental_realism": {
        "pause_scale": 1.15,
        "breath_amount": 0.075,
        "room_tone": True,
        "room_tone_level": 1.0,
        "loudness_variation": 0.55,
        "comma_pause_ms": 220,
        "period_pause_ms": 650,
        "paragraph_pause_ms": 950,
        "micro_pause_ms": 105,
        "micro_pause_probability": 0.38,
        "target_peak": 0.9,
        "soften": False,
        "tone_softening": 0.0,
        "sleep_softness": 0.0,
        "chunk_fade_ms": 10,
    },
}


@dataclass
class AudioStats:
    path: str
    sample_rate: int
    channels: int
    frames: int
    duration_seconds: float
    rms: float
    peak: float
    file_size_bytes: int


@dataclass
class SileroResult:
    ok: bool
    backend: str
    audio_path: str
    manifest_path: str
    speaker: str
    sample_rate: int
    device: str
    model_id: str
    elapsed_seconds: float
    duration_seconds: float
    speed_x: float
    stats: AudioStats
    speakers: list[str]
    realism: dict[str, Any] | None = None


class SileroTTSBackend:
    def __init__(self, model_id: str = DEFAULT_MODEL_ID, language: str = DEFAULT_LANGUAGE, device: str = DEFAULT_DEVICE):
        self.model_id = model_id
        self.language = language
        self.device = self._normalize_device(device)
        self._model: Any | None = None
        self._speakers: list[str] = KNOWN_RU_SPEAKERS.copy()

    @staticmethod
    def _normalize_device(device: str) -> str:
        requested = (device or DEFAULT_DEVICE).strip().lower()
        if requested in {"auto", ""}:
            return "cuda" if torch.cuda.is_available() else "cpu"
        if requested == "cuda" and torch.cuda.is_available():
            return "cuda"
        return "cpu"

    @property
    def speakers(self) -> list[str]:
        self._load_model()
        return self._speakers.copy()

    def _load_model(self):
        if self._model is not None:
            return self._model

        torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
        model, _example_text = torch.hub.load(
            repo_or_dir="snakers4/silero-models",
            model="silero_tts",
            language=self.language,
            speaker=self.model_id,
            trust_repo=True,
        )
        model.to(torch.device(self.device))
        self._model = model
        discovered = getattr(model, "speakers", None)
        if isinstance(discovered, (list, tuple)) and discovered:
            self._speakers = [str(item) for item in discovered]
        return model

    def synthesize(
        self,
        text: str,
        output_path: str | Path,
        speaker: str = DEFAULT_SPEAKER,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        realism_enabled: bool = False,
        preset: str = "sleep_safe",
        pause_scale: float | None = None,
        breath_amount: float | None = None,
        room_tone: bool | None = None,
        loudness_variation: float | None = None,
        seed: int = 42,
        speed: float | None = None,
        soften: bool | None = None,
        target_peak: float | None = None,
        tone_softening: float | None = None,
        sleep_softness: float | None = None,
    ) -> SileroResult:
        if not text or not text.strip():
            raise ValueError("Text is empty")

        if load_pronunciation_dictionary and preprocess_tts_text:
            text = preprocess_tts_text(
                text,
                load_pronunciation_dictionary(DEFAULT_PRONUNCIATION_DICTIONARY),
                stress_mark_style="plus",
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        model = self._load_model()
        selected_speaker = speaker.strip() or DEFAULT_SPEAKER
        if selected_speaker not in self._speakers:
            raise ValueError(f"Unknown speaker '{selected_speaker}'. Available speakers: {', '.join(self._speakers)}")

        started = time.perf_counter()
        if realism_enabled:
            realism_info = self._synthesize_realistic(
                model=model,
                text=text.strip(),
                output_path=output_path,
                speaker=selected_speaker,
                sample_rate=int(sample_rate),
                preset=preset,
                pause_scale=pause_scale,
                breath_amount=breath_amount,
                room_tone=room_tone,
                loudness_variation=loudness_variation,
                seed=int(seed),
                speed=speed,
                soften=soften,
                target_peak=target_peak,
                tone_softening=tone_softening,
                sleep_softness=sleep_softness,
            )
        else:
            self._save_model_wav(
                model=model,
                text=text.strip(),
                speaker=selected_speaker,
                sample_rate=int(sample_rate),
                output_path=output_path,
                speed=speed,
            )
            realism_info = None
        elapsed = time.perf_counter() - started
        stats = inspect_wav(output_path)
        manifest_path = output_path.with_suffix(".manifest.json")
        result = SileroResult(
            ok=True,
            backend="silero_tts_torch_hub",
            audio_path=str(output_path),
            manifest_path=str(manifest_path),
            speaker=selected_speaker,
            sample_rate=stats.sample_rate,
            device=self.device,
            model_id=self.model_id,
            elapsed_seconds=round(elapsed, 3),
            duration_seconds=round(stats.duration_seconds, 3),
            speed_x=round(stats.duration_seconds / elapsed, 3) if elapsed > 0 else math.inf,
            stats=stats,
            speakers=self._speakers.copy(),
            realism=realism_info,
        )
        manifest_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def _save_model_wav(
        self,
        model: Any,
        text: str,
        speaker: str,
        sample_rate: int,
        output_path: str | Path,
        speed: float | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "text": text,
            "speaker": speaker,
            "sample_rate": int(sample_rate),
            "audio_path": str(output_path),
        }
        if speed is not None:
            try:
                import inspect

                if "speed" in inspect.signature(model.save_wav).parameters:
                    kwargs["speed"] = float(speed)
            except Exception:
                pass
        model.save_wav(**kwargs)

    def _synthesize_realistic(
        self,
        model: Any,
        text: str,
        output_path: Path,
        speaker: str,
        sample_rate: int,
        preset: str,
        pause_scale: float | None,
        breath_amount: float | None,
        room_tone: bool | None,
        loudness_variation: float | None,
        seed: int,
        speed: float | None,
        soften: bool | None,
        target_peak: float | None,
        tone_softening: float | None,
        sleep_softness: float | None,
    ) -> dict[str, Any]:
        cfg = build_realism_config(
            preset=preset,
            pause_scale=pause_scale,
            breath_amount=breath_amount,
            room_tone=room_tone,
            loudness_variation=loudness_variation,
            soften=soften,
            target_peak=target_peak,
            tone_softening=tone_softening,
            sleep_softness=sleep_softness,
        )
        rng = np.random.default_rng(seed)
        chunks = split_text_for_realism(text)
        if not chunks:
            raise ValueError("No speakable text chunks after realism splitting")

        audio_parts: list[np.ndarray] = []
        pause_events: list[dict[str, Any]] = []
        breath_count = 0
        chunk_peaks: list[float] = []
        total_pause_frames = 0

        with tempfile.TemporaryDirectory(prefix="silero_realism_") as tmp_dir:
            for index, chunk in enumerate(chunks):
                chunk_path = Path(tmp_dir) / f"chunk_{index:03d}.wav"
                self._save_model_wav(model, chunk["text"], speaker, sample_rate, chunk_path, speed=speed)
                chunk_audio, chunk_sr = read_wav_float32(chunk_path)
                if chunk_sr != sample_rate:
                    raise ValueError(f"Unexpected chunk sample rate {chunk_sr}; expected {sample_rate}")
                chunk_audio = mono_float32(chunk_audio)
                chunk_audio = fade_edges(chunk_audio, sample_rate, fade_ms=int(cfg["chunk_fade_ms"]))
                if bool(cfg["soften"]):
                    chunk_audio = soften_audio(
                        chunk_audio,
                        sample_rate=sample_rate,
                        tone_softening=float(cfg["tone_softening"]),
                        sleep_softness=float(cfg["sleep_softness"]),
                    )

                gain_db = float(rng.normal(0.0, cfg["loudness_variation"] * 0.45)) if cfg["loudness_variation"] > 0 else 0.0
                gain_db = float(np.clip(gain_db, -cfg["loudness_variation"], cfg["loudness_variation"]))
                chunk_audio = chunk_audio * float(10 ** (gain_db / 20.0))
                chunk_peaks.append(round(float(np.max(np.abs(chunk_audio))) if chunk_audio.size else 0.0, 6))
                audio_parts.append(chunk_audio.astype(np.float32, copy=False))

                if index < len(chunks) - 1:
                    pause_ms = planned_pause_ms(chunk["pause_kind"], cfg, rng)
                    if pause_ms > 0:
                        if cfg["breath_amount"] > 0 and chunk["pause_kind"] in {"period", "paragraph"} and rng.random() < min(0.85, cfg["breath_amount"] * 5.0):
                            breath = make_breath(sample_rate, int(rng.integers(120, 260)), cfg["breath_amount"], rng)
                            audio_parts.append(breath)
                            breath_count += 1
                        pause = make_pause(sample_rate, pause_ms, bool(cfg["room_tone"]), rng, level=float(cfg["room_tone_level"]))
                        audio_parts.append(pause)
                        pause_frames = int(pause.shape[0])
                        total_pause_frames += pause_frames
                        pause_events.append({"after_chunk": index, "kind": chunk["pause_kind"], "duration_ms": round(1000.0 * pause_frames / sample_rate, 1)})

        if not audio_parts:
            raise ValueError("No audio generated")
        audio = np.concatenate(audio_parts).astype(np.float32, copy=False)
        audio = master_audio(audio, sample_rate=sample_rate, target_peak=float(cfg["target_peak"]), sleep_softness=float(cfg["sleep_softness"]))
        write_wav_float32(output_path, audio, sample_rate)
        return {
            "enabled": True,
            "preset": cfg["preset"],
            "seed": seed,
            "speed": speed,
            "chunks": len(chunks),
            "pauses": len(pause_events),
            "breaths": breath_count,
            "pause_seconds": round(total_pause_frames / sample_rate, 3),
            "room_tone": bool(cfg["room_tone"]),
            "room_tone_level": cfg["room_tone_level"],
            "pause_scale": cfg["pause_scale"],
            "breath_amount": cfg["breath_amount"],
            "loudness_variation_db": cfg["loudness_variation"],
            "target_peak": cfg["target_peak"],
            "soften": bool(cfg["soften"]),
            "tone_softening": cfg["tone_softening"],
            "sleep_softness": cfg["sleep_softness"],
            "chunk_fade_ms": cfg["chunk_fade_ms"],
            "chunk_peak_pre_master": chunk_peaks,
            "pause_events": pause_events,
            "split_preview": [chunk["text"] for chunk in chunks[:8]],
        }


def build_realism_config(
    preset: str,
    pause_scale: float | None,
    breath_amount: float | None,
    room_tone: bool | None,
    loudness_variation: float | None,
    soften: bool | None = None,
    target_peak: float | None = None,
    tone_softening: float | None = None,
    sleep_softness: float | None = None,
) -> dict[str, Any]:
    preset_name = preset if preset in REALISM_PRESETS else "sleep_safe"
    cfg = {"preset": preset_name, **REALISM_PRESETS[preset_name]}
    if pause_scale is not None:
        cfg["pause_scale"] = float(np.clip(pause_scale, 0.2, 2.2))
    if breath_amount is not None:
        cfg["breath_amount"] = float(np.clip(breath_amount, 0.0, 0.3))
    if room_tone is not None:
        cfg["room_tone"] = bool(room_tone)
    if loudness_variation is not None:
        cfg["loudness_variation"] = float(np.clip(loudness_variation, 0.0, 1.5))
    if soften is not None:
        cfg["soften"] = bool(soften)
    if target_peak is not None:
        cfg["target_peak"] = float(np.clip(target_peak, 0.45, 0.95))
    if tone_softening is not None:
        cfg["tone_softening"] = float(np.clip(tone_softening, 0.0, 0.75))
    if sleep_softness is not None:
        cfg["sleep_softness"] = float(np.clip(sleep_softness, 0.0, 1.0))
    if cfg["sleep_softness"] > 0 and not cfg["soften"]:
        cfg["soften"] = True
    return cfg


def split_text_for_realism(text: str) -> list[dict[str, str]]:
    cleaned = re.sub(r"[ \t]+", " ", text.strip())
    if not cleaned:
        return []
    tokens = re.split(r"(\n\s*\n+|[.!?…]+|[,;:—–-])", cleaned)
    chunks: list[dict[str, str]] = []
    buf = ""
    pending_pause = "micro"
    for token in tokens:
        if not token:
            continue
        if re.match(r"\n\s*\n+", token):
            if buf.strip():
                chunks.append({"text": buf.strip(), "pause_kind": "paragraph"})
                buf = ""
            pending_pause = "paragraph"
        elif re.match(r"[.!?…]+", token):
            buf += token
            if buf.strip():
                chunks.append({"text": buf.strip(), "pause_kind": "period"})
                buf = ""
            pending_pause = "period"
        elif re.match(r"[,;:—–-]", token):
            buf += token
            words = re.findall(r"\w+", buf, flags=re.UNICODE)
            if len(words) >= 5:
                chunks.append({"text": buf.strip(), "pause_kind": "comma"})
                buf = ""
            pending_pause = "comma"
        else:
            part = token.strip()
            if not part:
                continue
            candidate = (buf + " " + part).strip() if buf else part
            if len(candidate) > 150:
                split_at = max(candidate.rfind(" и ", 0, 150), candidate.rfind(" что ", 0, 150), candidate.rfind(" как ", 0, 150))
                if split_at > 55:
                    chunks.append({"text": candidate[:split_at].strip(), "pause_kind": "micro"})
                    buf = candidate[split_at:].strip()
                else:
                    chunks.append({"text": candidate.strip(), "pause_kind": pending_pause})
                    buf = ""
            else:
                buf = candidate
    if buf.strip():
        chunks.append({"text": buf.strip(), "pause_kind": pending_pause})
    if chunks:
        chunks[-1]["pause_kind"] = "none"
    return chunks


def planned_pause_ms(kind: str, cfg: dict[str, Any], rng: np.random.Generator) -> int:
    base = {
        "comma": cfg["comma_pause_ms"],
        "period": cfg["period_pause_ms"],
        "paragraph": cfg["paragraph_pause_ms"],
        "micro": cfg["micro_pause_ms"] if rng.random() < cfg["micro_pause_probability"] else 0,
    }.get(kind, 0)
    jitter = float(rng.normal(1.0, 0.12))
    return max(0, int(base * cfg["pause_scale"] * np.clip(jitter, 0.72, 1.34)))


def make_pause(sample_rate: int, duration_ms: int, room_tone: bool, rng: np.random.Generator, level: float = 1.0) -> np.ndarray:
    frames = max(0, int(sample_rate * duration_ms / 1000.0))
    if frames <= 0:
        return np.zeros(0, dtype=np.float32)
    if not room_tone:
        return np.zeros(frames, dtype=np.float32)
    noise = rng.normal(0.0, 1.0, frames).astype(np.float32)
    noise = smooth_noise(noise, window=max(8, int(sample_rate * 0.004)))
    noise *= float(rng.uniform(0.00055, 0.00115)) * float(np.clip(level, 0.0, 1.5))
    return fade_edges(noise, sample_rate, fade_ms=min(35, duration_ms // 3))


def make_breath(sample_rate: int, duration_ms: int, amount: float, rng: np.random.Generator) -> np.ndarray:
    frames = max(1, int(sample_rate * duration_ms / 1000.0))
    breath = rng.normal(0.0, 1.0, frames).astype(np.float32)
    breath = smooth_noise(breath, window=max(12, int(sample_rate * 0.009)))
    breath *= float(np.clip(amount, 0.0, 0.3)) * 0.018
    return fade_edges(breath, sample_rate, fade_ms=min(70, duration_ms // 2))


def smooth_noise(noise: np.ndarray, window: int) -> np.ndarray:
    if noise.size == 0 or window <= 1:
        return noise
    kernel = np.ones(window, dtype=np.float32) / float(window)
    return np.convolve(noise, kernel, mode="same").astype(np.float32)


def fade_edges(audio: np.ndarray, sample_rate: int, fade_ms: int = 10) -> np.ndarray:
    if audio.size == 0:
        return audio.astype(np.float32)
    fade = min(audio.size // 2, int(sample_rate * fade_ms / 1000.0))
    out = audio.astype(np.float32, copy=True)
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        out[:fade] *= ramp
        out[-fade:] *= ramp[::-1]
    return out


def one_pole_lowpass(audio: np.ndarray, sample_rate: int, cutoff_hz: float) -> np.ndarray:
    if audio.size == 0:
        return audio.astype(np.float32)
    cutoff = float(np.clip(cutoff_hz, 1200.0, sample_rate * 0.45))
    alpha = float(1.0 - math.exp(-2.0 * math.pi * cutoff / sample_rate))
    out = np.empty_like(audio, dtype=np.float32)
    last = float(audio[0])
    out[0] = last
    for index in range(1, audio.size):
        last += alpha * (float(audio[index]) - last)
        out[index] = last
    return out


def soften_audio(audio: np.ndarray, sample_rate: int, tone_softening: float, sleep_softness: float) -> np.ndarray:
    if audio.size == 0:
        return audio.astype(np.float32)
    amount = float(np.clip(tone_softening, 0.0, 0.75))
    softness = float(np.clip(sleep_softness, 0.0, 1.0))
    if amount <= 0.0 and softness <= 0.0:
        return audio.astype(np.float32, copy=False)

    cutoff = 9000.0 - 2400.0 * amount - 900.0 * softness
    low = one_pole_lowpass(audio.astype(np.float32, copy=False), sample_rate, cutoff_hz=cutoff)
    softened = audio * (1.0 - amount) + low * amount

    high = softened - one_pole_lowpass(softened, sample_rate, cutoff_hz=5200.0)
    high_gate = np.clip((np.abs(high) - 0.018) / 0.10, 0.0, 1.0)
    softened = softened - high * high_gate * (0.10 + 0.18 * softness)
    return np.clip(softened, -1.0, 1.0).astype(np.float32)


def master_audio(audio: np.ndarray, sample_rate: int, target_peak: float, sleep_softness: float = 0.0) -> np.ndarray:
    out = np.nan_to_num(audio.astype(np.float32, copy=True))
    softness = float(np.clip(sleep_softness, 0.0, 1.0))
    if softness > 0:
        drive = 1.0 + 0.18 * softness
        out = np.tanh(out * drive) / math.tanh(drive)
        rms = float(np.sqrt(np.mean(np.square(out)))) if out.size else 0.0
        if rms > 0.115:
            out *= 0.115 / rms
    out = fade_edges(out, sample_rate, fade_ms=8 + int(8 * softness))
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 0:
        out *= min(1.0, float(target_peak) / peak)
    return np.clip(out, -0.98, 0.98).astype(np.float32)


def mono_float32(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 2:
        return audio.mean(axis=1).astype(np.float32)
    return audio.astype(np.float32, copy=False)


def read_wav_float32(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        frames = wav_file.getnframes()
        sample_width = wav_file.getsampwidth()
        raw = wav_file.readframes(frames)
    if sample_width == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if channels > 1:
        samples = samples.reshape(-1, channels)
    return samples.astype(np.float32, copy=False), sample_rate


def write_wav_float32(path: str | Path, audio: np.ndarray, sample_rate: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(pcm.tobytes())


def inspect_wav(path: str | Path) -> AudioStats:
    path = Path(path)
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        frames = wav_file.getnframes()
        sample_width = wav_file.getsampwidth()
        raw = wav_file.readframes(frames)

    if sample_width == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        samples = (samples - 128.0) / 128.0

    rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    return AudioStats(
        path=str(path),
        sample_rate=sample_rate,
        channels=channels,
        frames=frames,
        duration_seconds=frames / sample_rate if sample_rate else 0.0,
        rms=round(rms, 6),
        peak=round(peak, 6),
        file_size_bytes=path.stat().st_size,
    )


def load_text(text: str | None, text_file: str | None) -> str:
    if text_file:
        return Path(text_file).read_text(encoding="utf-8")
    return text or ""

