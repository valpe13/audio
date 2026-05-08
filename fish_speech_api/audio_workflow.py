from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from fish_backend import FishSpeechBackend, TTSRequest
except ImportError:  # pragma: no cover - package-style imports
    from .fish_backend import FishSpeechBackend, TTSRequest


SAMPLE_RATE = 24_000
SAMPLE_WIDTH = 2
CHANNELS = 1


@dataclass(slots=True)
class ChunkPlan:
    index: int
    text: str
    pause_after_ms: int
    gain_db: float
    speaking_rate_hint: float
    breath_after: bool = False
    room_tone_db: float = -58.0
    pitch_drift_percent: float = 0.0


@dataclass(slots=True)
class WorkflowResult:
    ok: bool
    backend: str
    output_wav: str
    output_mp3: str | None
    chunks: int
    duration_seconds: float
    manifest_path: str
    note: str | None = None


REALISM_PRESETS = {
    "sleep_safe": {
        "enabled": True,
        "micro_pauses": True,
        "micro_pause_min_ms": 120,
        "micro_pause_max_ms": 420,
        "loudness_variation_db": 0.35,
        "pitch_drift_percent": 0.35,
        "breath_amount": 0.04,
        "breath_in_pause_probability": 0.08,
        "breath_max_amplitude": 180,
        "room_tone": True,
        "room_tone_db": -62.0,
        "master_peak": 0.82,
    },
    "natural_lecture": {
        "enabled": True,
        "micro_pauses": True,
        "micro_pause_min_ms": 100,
        "micro_pause_max_ms": 520,
        "loudness_variation_db": 0.75,
        "pitch_drift_percent": 0.65,
        "breath_amount": 0.14,
        "breath_in_pause_probability": 0.18,
        "breath_max_amplitude": 260,
        "room_tone": True,
        "room_tone_db": -58.0,
        "master_peak": 0.86,
    },
    "experimental_realism": {
        "enabled": True,
        "micro_pauses": True,
        "micro_pause_min_ms": 90,
        "micro_pause_max_ms": 650,
        "loudness_variation_db": 1.1,
        "pitch_drift_percent": 1.0,
        "breath_amount": 0.28,
        "breath_in_pause_probability": 0.32,
        "breath_max_amplitude": 340,
        "room_tone": True,
        "room_tone_db": -55.0,
        "master_peak": 0.88,
    },
}


def clean_russian_text(text: str) -> str:
    replacements = {
        "\u00a0": " ",
        "…": "...",
        "—": " — ",
        "–": " — ",
        "\t": " ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    abbreviation_replacements = {
        r"\bт\.\s*е\.": "то есть",
        r"\bт\.\s*к\.": "так как",
        r"\bт\.\s*д\.": "так далее",
        r"\bт\.\s*п\.": "тому подобное",
        r"\bи\s*т\.\s*д\.": "и так далее",
        r"\bи\s*т\.\s*п\.": "и тому подобное",
        r"\bнапр\.": "например",
        r"\bсм\.": "смотри",
        r"\bстр\.": "страница",
        r"\bг\.": "город",
    }
    for pattern, replacement in abbreviation_replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    stress_replacements = {
        "Плечи": "Пле́чи",
        "выдохом": "вы́дохом",
        "выдох": "вы́дох",
        "вдох": "вдох",
        "ровнее": "ровне́е",
        "плечи": "пле́чи",
        "вечерний": "вече́рний",
        "комнату": "ко́мнату",
        "слушать": "слу́шать",
        "напряжение": "напряже́ние",
        "следующим": "сле́дующим",
    }
    for word, replacement in stress_replacements.items():
        text = re.sub(rf"(?<![А-Яа-яЁё]){word}(?![А-Яа-яЁё])", replacement, text, flags=re.IGNORECASE)

    text = re.sub(r"(?<=\d)\s*%", " процентов", text)
    text = re.sub(r"№\s*", "номер ", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=[А-Яа-яA-Za-zЁё])", r"\1 ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, max_chars: int = 420, *, micro_pauses: bool = False) -> list[str]:
    cleaned = clean_russian_text(text)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", cleaned) if part.strip()]
    chunks: list[str] = []

    for paragraph in paragraphs:
        sentences = [part.strip() for part in re.findall(r"[^.!?]+(?:[.!?]+|$)", paragraph) if part.strip()]
        current = ""
        for sentence in sentences:
            if len(sentence) > max_chars:
                if current:
                    chunks.extend(_split_micro_pause_phrases(current.strip(), max_chars) if micro_pauses else [current.strip()])
                    current = ""
                chunks.extend(_split_long_sentence(sentence, max_chars))
                continue

            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current.strip())
                current = sentence
            else:
                current = candidate

        if current:
            chunks.extend(_split_micro_pause_phrases(current.strip(), max_chars) if micro_pauses else [current.strip()])

    return chunks


def _split_micro_pause_phrases(text: str, max_chars: int) -> list[str]:
    if len(text) <= max(130, int(max_chars * 0.58)):
        return [text]
    pieces = [piece.strip() for piece in re.split(r"(?<=[,;:—])\s+", text) if piece.strip()]
    if len(pieces) < 2:
        return [text]
    result: list[str] = []
    current = ""
    target = max(95, int(max_chars * 0.48))
    for piece in pieces:
        candidate = f"{current} {piece}".strip()
        if current and len(candidate) > target:
            result.append(current.strip())
            current = piece
        else:
            current = candidate
    if current:
        result.append(current.strip())
    return result or [text]


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    pieces = [piece.strip() for piece in re.split(r"([,;:])", sentence) if piece.strip()]
    merged: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{piece}" if piece in ",;:" else f"{current} {piece}".strip()
        if current and len(candidate) > max_chars:
            merged.append(current.strip())
            current = piece
        else:
            current = candidate
    if current:
        merged.append(current.strip())
    return merged


def plan_prosody(chunks: list[str], seed: int = 42, realism: dict | None = None) -> list[ChunkPlan]:
    rng = random.Random(seed)
    realism = realism or resolve_realism_config({})
    loudness_variation_db = max(0.0, float(realism.get("loudness_variation_db", 0.0)))
    pitch_drift_max = min(1.0, max(0.0, float(realism.get("pitch_drift_percent", 0.0))))
    breath_probability = min(1.0, max(0.0, float(realism.get("breath_in_pause_probability", 0.0)) * float(realism.get("breath_amount", 0.0)) / 0.14))
    pause_min = int(realism.get("micro_pause_min_ms", 120))
    pause_max = int(realism.get("micro_pause_max_ms", 520))
    room_tone_db = float(realism.get("room_tone_db", -58.0))
    plan: list[ChunkPlan] = []
    for index, chunk in enumerate(chunks):
        terminal = chunk[-1:] if chunk else "."
        base_pause = 520
        if terminal == ",":
            base_pause = 260
        elif terminal in "!?":
            base_pause = 720
        elif terminal == ".":
            base_pause = 620
        if terminal in ",;:—":
            base_pause = 260
        if len(chunk) > 280:
            base_pause += 160
        text_ends_soft = terminal in ",;:—"
        random_pause = rng.randint(-90 if text_ends_soft else -140, 150 if text_ends_soft else 180)
        pause_after_ms = max(pause_min, min(pause_max if text_ends_soft else 1100, int(base_pause + random_pause)))
        plan.append(
            ChunkPlan(
                index=index,
                text=chunk,
                pause_after_ms=pause_after_ms,
                gain_db=round(rng.uniform(-loudness_variation_db, loudness_variation_db * 0.55), 3),
                speaking_rate_hint=round(rng.uniform(0.94, 1.04), 3),
                breath_after=bool(realism.get("breath_injection", True)) and rng.random() < breath_probability and terminal in ".,;:!?—",
                room_tone_db=room_tone_db,
                pitch_drift_percent=round(rng.uniform(-pitch_drift_max, pitch_drift_max), 4),
            )
        )
    return plan


def resolve_realism_config(config: dict, overrides: dict | None = None) -> dict:
    root = dict(config.get("realism", {})) if isinstance(config.get("realism", {}), dict) else {}
    preset_name = str((overrides or {}).get("preset") or root.get("preset") or "sleep_safe")
    resolved = dict(REALISM_PRESETS.get(preset_name, REALISM_PRESETS["sleep_safe"]))
    resolved["preset"] = preset_name
    for key, value in root.items():
        if key != "presets":
            resolved[key] = value
    presets = root.get("presets")
    if isinstance(presets, dict) and isinstance(presets.get(preset_name), dict):
        resolved.update(presets[preset_name])
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                resolved[key] = value
    resolved["pitch_drift_percent"] = min(1.0, max(0.0, float(resolved.get("pitch_drift_percent", 0.0))))
    resolved["loudness_variation_db"] = min(1.5, max(0.0, float(resolved.get("loudness_variation_db", 0.0))))
    resolved["breath_amount"] = min(1.0, max(0.0, float(resolved.get("breath_amount", 0.0))))
    return resolved


def generate_long_form_audio(
    text: str,
    config: dict,
    output_wav: Path,
    *,
    language: str = "ru",
    speaker: str | None = None,
    seed: int = 42,
    max_chars: int = 420,
    export_mp3: bool = True,
    preset: str | None = None,
    realism_overrides: dict | None = None,
    reference_audio: str | None = None,
    reference_text: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    fixed_chunk_seed: bool | None = None,
    voice_prompt: str | None = None,
) -> WorkflowResult:
    output_wav = output_wav.resolve()
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    backend = FishSpeechBackend(config)
    realism = resolve_realism_config(config, {"preset": preset, **(realism_overrides or {})})
    fish_config = config.get("fish_speech", {}) if isinstance(config.get("fish_speech", {}), dict) else {}
    fixed_chunk_seed = bool(fish_config.get("fixed_chunk_seed", False)) if fixed_chunk_seed is None else fixed_chunk_seed
    temperature = float(fish_config.get("temperature", 0.7)) if temperature is None else temperature
    top_p = float(fish_config.get("top_p", 0.7)) if top_p is None else top_p
    voice_prompt = str(voice_prompt or fish_config.get("voice_prompt", "") or "").strip()
    prompt_prefix_as_text = bool(fish_config.get("prompt_prefix_as_text", False))
    if voice_prompt and prompt_prefix_as_text and not (reference_audio and reference_text):
        text = f"{voice_prompt}\n\n{text}"
    chunks = chunk_text(text, max_chars=max_chars, micro_pauses=bool(realism.get("micro_pauses", False)))
    plan = plan_prosody(chunks, seed=seed, realism=realism)

    with tempfile.TemporaryDirectory(prefix="fish_longform_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        segment_paths: list[Path] = []
        for item in plan:
            segment_path = temp_dir / f"segment_{item.index:03d}.wav"
            backend.synthesize(
                TTSRequest(
                    text=item.text,
                    language=language,
                    speaker=speaker,
                    seed=seed if fixed_chunk_seed else seed + item.index,
                    temperature=temperature,
                    top_p=top_p,
                    reference_audio=reference_audio,
                    reference_text=reference_text,
                ),
                segment_path,
            )
            processed_path = temp_dir / f"segment_{item.index:03d}_processed.wav"
            samples, sample_rate = read_wav_mono(segment_path)
            samples = apply_gain_db(samples, item.gain_db)
            samples = apply_pitch_drift(samples, item.pitch_drift_percent, seed + item.index) if item.pitch_drift_percent else samples
            write_wav_mono(processed_path, samples, sample_rate)
            segment_paths.append(processed_path)

        concatenated = concat_segments_with_room_tone(segment_paths, plan, seed=seed, realism=realism)
        mastered = master_audio(concatenated, target_peak=float(realism.get("master_peak", 0.86)))
        write_wav_mono(output_wav, mastered, SAMPLE_RATE)

    output_mp3: Path | None = None
    if export_mp3:
        output_mp3 = export_mp3_with_ffmpeg(output_wav)

    duration = get_wav_duration(output_wav)
    manifest_path = output_wav.with_suffix(".manifest.json")
    manifest = {
        "ok": True,
        "backend": backend.backend_name,
        "output_wav": str(output_wav),
        "output_mp3": str(output_mp3) if output_mp3 else None,
        "chunks": [asdict(item) for item in plan],
        "realism": realism,
        "reference_audio_enabled": bool(reference_audio and reference_text),
        "voice_prompt": voice_prompt,
        "voice_prompt_mode": "reference_conditioning" if reference_audio and reference_text and voice_prompt else "text_prefix" if voice_prompt and prompt_prefix_as_text else "metadata_only",
        "fixed_chunk_seed": fixed_chunk_seed,
        "temperature": temperature,
        "top_p": top_p,
        "duration_seconds": duration,
        "sample_rate": SAMPLE_RATE,
        "note": "Placeholder backend tone/prosody test; connect real Fish Speech for speech." if backend.backend_name == "placeholder" else None,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return WorkflowResult(
        ok=True,
        backend=backend.backend_name,
        output_wav=str(output_wav),
        output_mp3=str(output_mp3) if output_mp3 else None,
        chunks=len(plan),
        duration_seconds=duration,
        manifest_path=str(manifest_path),
        note=manifest["note"],
    )


def read_wav_mono(path: Path) -> tuple[list[int], int]:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != SAMPLE_WIDTH:
        raise ValueError(f"Only 16-bit WAV is supported, got {sample_width * 8}-bit: {path}")

    samples = [int.from_bytes(frames[i : i + 2], "little", signed=True) for i in range(0, len(frames), 2)]
    if channels == 1:
        return samples, sample_rate
    if channels == 2:
        mono = [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples), 2)]
        return mono, sample_rate
    raise ValueError(f"Only mono/stereo WAV is supported, got {channels} channels: {path}")


def write_wav_mono(path: Path, samples: list[int], sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for sample in samples:
            frames.extend(_clip_int16(sample).to_bytes(2, "little", signed=True))
        wav_file.writeframes(bytes(frames))


def concat_segments_with_room_tone(paths: list[Path], plan: list[ChunkPlan], seed: int, realism: dict | None = None) -> list[int]:
    output: list[int] = []
    realism = realism or resolve_realism_config({})
    for index, path in enumerate(paths):
        samples, sample_rate = read_wav_mono(path)
        if sample_rate != SAMPLE_RATE:
            samples = resample_linear(samples, sample_rate, SAMPLE_RATE)
        output.extend(samples)
        pause = generate_room_tone(plan[index].pause_after_ms, seed + index, db=float(plan[index].room_tone_db)) if realism.get("room_tone", True) else [0] * int(SAMPLE_RATE * plan[index].pause_after_ms / 1000)
        if plan[index].breath_after:
            pause = mix_at_start(pause, load_or_generate_breath(realism, seed + index), offset_ms=35)
        output.extend(pause)
    return output


def resample_linear(samples: list[int], source_rate: int, target_rate: int) -> list[int]:
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError(f"Invalid sample rate conversion: {source_rate} -> {target_rate}")
    if source_rate == target_rate or not samples:
        return samples

    output_length = max(1, int(round(len(samples) * target_rate / source_rate)))
    if output_length == 1:
        return [samples[0]]

    ratio = source_rate / target_rate
    resampled: list[int] = []
    last_index = len(samples) - 1
    for output_index in range(output_length):
        source_position = output_index * ratio
        left = min(int(source_position), last_index)
        right = min(left + 1, last_index)
        fraction = source_position - left
        value = int(samples[left] * (1.0 - fraction) + samples[right] * fraction)
        resampled.append(_clip_int16(value))
    return resampled


def generate_room_tone(duration_ms: int, seed: int, amplitude: int | None = None, db: float = -58.0) -> list[int]:
    rng = random.Random(seed)
    if amplitude is None:
        amplitude = max(0, int(32767 * (10 ** (db / 20.0))))
    total = int(SAMPLE_RATE * duration_ms / 1000)
    samples: list[int] = []
    drift = rng.randint(-10, 10)
    for index in range(total):
        low = math.sin(2.0 * math.pi * 55.0 * index / SAMPLE_RATE) * 0.22
        noise = rng.uniform(-1.0, 1.0) * 0.78
        samples.append(int((noise + low) * amplitude + drift))
    return samples


def load_or_generate_breath(realism: dict, seed: int) -> list[int]:
    sample_path = str(realism.get("breath_sample", "") or "").strip()
    breath_amount = float(realism.get("breath_amount", 0.0))
    if sample_path:
        path = Path(sample_path)
        if path.exists():
            samples, sample_rate = read_wav_mono(path)
            if sample_rate != SAMPLE_RATE:
                samples = resample_linear(samples, sample_rate, SAMPLE_RATE)
            return apply_gain_db(samples[: int(SAMPLE_RATE * 0.65)], -24.0 + 12.0 * breath_amount)
    rng = random.Random(seed)
    duration_ms = rng.randint(180, 420)
    total = int(SAMPLE_RATE * duration_ms / 1000)
    max_amp = int(float(realism.get("breath_max_amplitude", 220)) * breath_amount)
    samples: list[int] = []
    last = 0.0
    for index in range(total):
        pos = index / max(total - 1, 1)
        envelope = math.sin(math.pi * pos) ** 1.7
        hiss = rng.uniform(-1.0, 1.0)
        last = 0.72 * last + 0.28 * hiss
        low_cut = hiss - last
        samples.append(int(low_cut * envelope * max_amp))
    return samples


def mix_at_start(base: list[int], overlay: list[int], offset_ms: int = 0) -> list[int]:
    if not overlay:
        return base
    output = list(base)
    offset = min(len(output), int(SAMPLE_RATE * offset_ms / 1000))
    required = offset + len(overlay)
    if required > len(output):
        output.extend([0] * (required - len(output)))
    for index, sample in enumerate(overlay):
        output[offset + index] = _clip_int16(output[offset + index] + sample)
    return output


def apply_pitch_drift(samples: list[int], drift_percent: float, seed: int) -> list[int]:
    if not samples or abs(drift_percent) < 0.01:
        return samples
    drift = max(-1.0, min(1.0, drift_percent)) / 100.0
    rng = random.Random(seed)
    phase = rng.random() * math.tau
    cycle_seconds = rng.uniform(5.0, 11.0)
    warped: list[int] = []
    source_pos = 0.0
    last_index = len(samples) - 1
    while len(warped) < len(samples) and source_pos < last_index:
        left = int(source_pos)
        right = min(left + 1, last_index)
        frac = source_pos - left
        warped.append(_clip_int16(int(samples[left] * (1.0 - frac) + samples[right] * frac)))
        t = len(warped) / SAMPLE_RATE
        rate = 1.0 + drift * math.sin(math.tau * t / cycle_seconds + phase)
        source_pos += max(0.985, min(1.015, rate))
    if len(warped) != len(samples):
        warped = resample_linear(warped, max(1, int(SAMPLE_RATE * len(warped) / max(len(samples), 1))), SAMPLE_RATE)
    return (warped + [0] * len(samples))[: len(samples)]


def master_audio(samples: list[int], target_peak: float = 0.88, fade_ms: int = 35) -> list[int]:
    if not samples:
        return samples
    peak = max(abs(sample) for sample in samples) or 1
    gain = (32767 * target_peak) / peak
    mastered = [_clip_int16(int(sample * gain)) for sample in samples]
    fade_samples = min(len(mastered) // 2, int(SAMPLE_RATE * fade_ms / 1000))
    for index in range(fade_samples):
        factor = index / max(fade_samples, 1)
        mastered[index] = int(mastered[index] * factor)
        mastered[-index - 1] = int(mastered[-index - 1] * factor)
    return mastered


def apply_gain_db(samples: list[int], gain_db: float) -> list[int]:
    multiplier = 10 ** (gain_db / 20.0)
    return [_clip_int16(int(sample * multiplier)) for sample in samples]


def export_mp3_with_ffmpeg(wav_path: Path) -> Path | None:
    if shutil.which("ffmpeg") is None:
        return None
    mp3_path = wav_path.with_suffix(".mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "3", str(mp3_path)],
        check=True,
    )
    return mp3_path


def get_wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        return round(wav_file.getnframes() / float(wav_file.getframerate()), 3)


def _clip_int16(sample: int) -> int:
    return max(-32768, min(32767, sample))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate long-form Russian test audio through the local Fish Speech workflow")
    parser.add_argument("--text-file", type=Path, default=Path(__file__).with_name("sample_russian_sleep_lecture.txt"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("outputs") / "russian_sleep_lecture_placeholder_test.wav")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-chars", type=int, default=420)
    parser.add_argument("--preset", choices=sorted(REALISM_PRESETS), default=None)
    parser.add_argument("--breath-amount", type=float, default=None)
    parser.add_argument("--room-tone", choices=["on", "off"], default=None)
    parser.add_argument("--pitch-drift", type=float, default=None)
    parser.add_argument("--loudness-variation", type=float, default=None)
    parser.add_argument("--reference-audio", type=str, default=None)
    parser.add_argument("--reference-text", type=str, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--fixed-chunk-seed", action="store_true")
    parser.add_argument("--voice-prompt", type=str, default=None)
    parser.add_argument("--no-mp3", action="store_true")
    args = parser.parse_args()

    config_path = args.config if args.config.exists() else Path(__file__).with_name("config.example.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if "output_dir" in config:
        output_dir = Path(str(config["output_dir"]))
        if not output_dir.is_absolute():
            config["output_dir"] = str(Path(__file__).resolve().parent / output_dir)

    text = args.text_file.read_text(encoding="utf-8")
    realism_overrides = {
        "breath_amount": args.breath_amount,
        "room_tone": None if args.room_tone is None else args.room_tone == "on",
        "pitch_drift_percent": args.pitch_drift,
        "loudness_variation_db": args.loudness_variation,
    }
    fish_config = config.get("fish_speech", {}) if isinstance(config.get("fish_speech", {}), dict) else {}
    reference_audio = args.reference_audio or fish_config.get("reference_audio") or None
    reference_text = args.reference_text or fish_config.get("reference_text") or None
    result = generate_long_form_audio(
        text,
        config,
        args.output,
        seed=args.seed,
        max_chars=args.max_chars,
        export_mp3=not args.no_mp3,
        preset=args.preset,
        realism_overrides=realism_overrides,
        reference_audio=reference_audio,
        reference_text=reference_text,
        temperature=args.temperature,
        top_p=args.top_p,
        fixed_chunk_seed=args.fixed_chunk_seed or None,
        voice_prompt=args.voice_prompt,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
