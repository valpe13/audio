from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TTSRequest:
    text: str
    language: str = "ru"
    speaker: str | None = None
    seed: int | None = None
    temperature: float = 0.7
    top_p: float = 0.7
    reference_audio: str | None = None
    reference_text: str | None = None


class FishSpeechBackend:
    """Adapter boundary for real Fish Speech inference.

    The current implementation is intentionally a safe placeholder: it creates
    a short WAV marker file so the HTTP API and ComfyUI bridge can be tested
    without downloading models or installing heavy CUDA dependencies.

    Replace `synthesize()` internals after installing Fish Speech locally.
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self.backend_name = str(config.get("backend", "placeholder"))

    def synthesize(self, request: TTSRequest, output_path: Path) -> Path:
        if self.backend_name == "fish_speech_cli":
            return self._synthesize_with_fish_speech_cli(request, output_path)

        if self.backend_name != "placeholder":
            raise NotImplementedError(f"Unsupported TTS backend: {self.backend_name}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_placeholder_wav(output_path, request.text)
        return output_path

    def _synthesize_with_fish_speech_cli(self, request: TTSRequest, output_path: Path) -> Path:
        fish_config = dict(self.config.get("fish_speech", {}))
        repo_dir = self._resolve_path(fish_config.get("repo_dir"))
        checkpoint_dir = self._resolve_path(fish_config.get("checkpoint_dir"))
        venv_python = self._resolve_path(fish_config.get("venv_python"))
        device = str(fish_config.get("device", "cuda"))
        use_half = bool(fish_config.get("half", True))
        compile_model = bool(fish_config.get("compile", False))
        max_new_tokens = int(fish_config.get("max_new_tokens", 0))
        chunk_length = int(fish_config.get("chunk_length", 300))
        top_p = float(fish_config.get("top_p", request.top_p))
        temperature = float(fish_config.get("temperature", request.temperature))
        timeout_seconds = int(fish_config.get("timeout_seconds", 900))
        fallback_to_placeholder = bool(fish_config.get("fallback_to_placeholder", False))

        if repo_dir is None or not repo_dir.exists():
            raise FileNotFoundError(f"Fish Speech repo_dir does not exist: {repo_dir}")
        if checkpoint_dir is None or not checkpoint_dir.exists():
            raise FileNotFoundError(f"Fish Speech checkpoint_dir does not exist: {checkpoint_dir}")

        python_executable = str(venv_python) if venv_python and venv_python.exists() else shutil.which("python")
        if not python_executable:
            raise FileNotFoundError("Python executable for Fish Speech was not found")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        text2semantic_script = repo_dir / "fish_speech" / "models" / "text2semantic" / "inference.py"
        dac_script = repo_dir / "fish_speech" / "models" / "dac" / "inference.py"
        codec_checkpoint = self._resolve_path(
            fish_config.get("codec_checkpoint") or str(checkpoint_dir / "codec.pth")
        )
        decoder_config_name = str(fish_config.get("decoder_config_name", "modded_dac_vq"))
        output_dir = output_path.parent / f"{output_path.stem}_codes"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        text = request.text
        add_speaker_tag = bool(fish_config.get("add_speaker_tag", False))
        if add_speaker_tag and "<|speaker:" not in text:
            text = f"<|speaker:0|>{text}"

        semantic_command = [
            python_executable,
            str(text2semantic_script),
            "--text",
            text,
            "--checkpoint-path",
            str(checkpoint_dir),
            "--device",
            device,
            "--output-dir",
            str(output_dir),
            "--chunk-length",
            str(chunk_length),
            "--temperature",
            str(temperature),
            "--top-p",
            str(top_p),
        ]
        if request.seed is not None:
            semantic_command.extend(["--seed", str(request.seed)])
        if max_new_tokens > 0:
            semantic_command.extend(["--max-new-tokens", str(max_new_tokens)])
        iterative_prompt = bool(fish_config.get("iterative_prompt", True))
        semantic_command.append("--iterative-prompt" if iterative_prompt else "--no-iterative-prompt")
        semantic_command.append("--half" if use_half else "--no-half")
        semantic_command.append("--compile" if compile_model else "--no-compile")

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["TOKENIZERS_PARALLELISM"] = "false"

        config_reference_audio = str(fish_config.get("reference_audio", "") or "").strip()
        config_reference_text = str(fish_config.get("reference_text", "") or "").strip()
        reference_audio = str(request.reference_audio or config_reference_audio or "").strip()
        reference_text = str(request.reference_text or config_reference_text or "").strip()
        if reference_audio and reference_text:
            reference_path = self._resolve_path(reference_audio)
            if reference_path is None or not reference_path.exists():
                raise FileNotFoundError(f"Reference audio does not exist: {reference_audio}")
            if bool(fish_config.get("use_prompt_audio", False)):
                semantic_command.extend(["--prompt-audio", str(reference_path), "--prompt-text", reference_text])
            else:
                prompt_tokens = output_path.parent / f"{output_path.stem}_prompt_tokens.npy"
                prompt_command = [
                    python_executable,
                    str(dac_script),
                    "-i",
                    str(reference_path),
                    "-o",
                    str(prompt_tokens.with_suffix(".wav")),
                    "--checkpoint-path",
                    str(codec_checkpoint),
                    "--config-name",
                    decoder_config_name,
                    "-d",
                    device,
                ]
                prompt_result = subprocess.run(
                    prompt_command,
                    cwd=str(repo_dir),
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                if prompt_result.returncode != 0 or not prompt_tokens.exists():
                    raise RuntimeError(
                        "Fish Speech prompt-token extraction failed "
                        f"with exit code {prompt_result.returncode}.\nSTDOUT:\n{prompt_result.stdout}\nSTDERR:\n{prompt_result.stderr}"
                    )
                semantic_command.extend(["--prompt-tokens", str(prompt_tokens), "--prompt-text", reference_text])

        try:
            result = subprocess.run(
                semantic_command,
                cwd=str(repo_dir),
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except Exception as exc:
            if fallback_to_placeholder:
                self._write_backend_error(output_path, f"Fish Speech CLI raised {type(exc).__name__}: {exc}")
                self._write_placeholder_wav(output_path, request.text)
                return output_path
            raise

        codes_path = output_dir / "codes_0.npy"
        if result.returncode != 0 or not codes_path.exists():
            message = (
                "Fish Speech text2semantic CLI failed "
                f"with exit code {result.returncode}.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
            if fallback_to_placeholder:
                self._write_backend_error(output_path, message)
                self._write_placeholder_wav(output_path, request.text)
                return output_path
            raise RuntimeError(message)

        dac_command = [
            python_executable,
            str(dac_script),
            "-i",
            str(codes_path),
            "-o",
            str(output_path),
            "--checkpoint-path",
            str(codec_checkpoint),
            "--config-name",
            decoder_config_name,
            "-d",
            device,
        ]
        dac_result = subprocess.run(
            dac_command,
            cwd=str(repo_dir),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if dac_result.returncode != 0 or not output_path.exists():
            message = (
                "Fish Speech DAC CLI failed "
                f"with exit code {dac_result.returncode}.\nSTDOUT:\n{dac_result.stdout}\nSTDERR:\n{dac_result.stderr}"
            )
            if fallback_to_placeholder:
                self._write_backend_error(output_path, message)
                self._write_placeholder_wav(output_path, request.text)
                return output_path
            raise RuntimeError(message)

        return output_path

    @staticmethod
    def _resolve_path(value: object) -> Path | None:
        if not value:
            return None
        path = Path(str(value))
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parent.parent / path

    @staticmethod
    def _write_placeholder_wav(output_path: Path, text: str) -> None:
        sample_rate = 24_000
        duration_seconds = min(12.0, max(1.2, len(text) / 28.0))
        total_samples = int(sample_rate * duration_seconds)
        amplitude = 0.13
        rng = random.Random(sum(ord(char) for char in text))
        base_frequency_hz = 155.0 + rng.random() * 40.0

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)

            frames = bytearray()
            for index in range(total_samples):
                seconds = index / sample_rate
                syllable_gate = 0.58 + 0.42 * max(0.0, math.sin(2.0 * math.pi * 4.2 * seconds))
                phrase_envelope = 0.72 + 0.28 * math.sin(2.0 * math.pi * 0.33 * seconds + 0.4)
                fade_in = min(1.0, index / max(int(sample_rate * 0.04), 1))
                fade_out = min(1.0, (total_samples - index) / max(int(sample_rate * 0.08), 1))
                envelope = syllable_gate * phrase_envelope * fade_in * fade_out
                frequency_hz = base_frequency_hz + 28.0 * math.sin(2.0 * math.pi * 1.1 * seconds)
                carrier = (
                    math.sin(2.0 * math.pi * frequency_hz * seconds)
                    + 0.35 * math.sin(2.0 * math.pi * frequency_hz * 2.01 * seconds)
                    + 0.16 * math.sin(2.0 * math.pi * frequency_hz * 3.03 * seconds)
                )
                sample = int(
                    32767
                    * amplitude
                    * envelope
                    * carrier
                    / 1.51
                )
                frames.extend(sample.to_bytes(2, byteorder="little", signed=True))

            wav_file.writeframes(bytes(frames))

    @staticmethod
    def _write_backend_error(output_path: Path, message: str) -> None:
        error_path = output_path.with_suffix(".fish_speech_error.txt")
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text(message, encoding="utf-8")

