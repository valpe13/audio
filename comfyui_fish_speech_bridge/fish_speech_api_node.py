from __future__ import annotations

import json
from pathlib import Path

import requests


class FishSpeechAPITTS:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": "Пример синтеза речи."}),
                "api_url": ("STRING", {"default": "http://127.0.0.1:7865/v1/tts"}),
                "language": ("STRING", {"default": "ru"}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.05}),
                "top_p": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.05}),
                "long_form": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "speaker": ("STRING", {"default": ""}),
                "reference_audio": ("STRING", {"default": ""}),
                "reference_text": ("STRING", {"multiline": True, "default": ""}),
                "preset": (["sleep_safe", "natural_lecture", "experimental_realism"], {"default": "sleep_safe"}),
                "breath_amount": ("FLOAT", {"default": 0.04, "min": 0.0, "max": 1.0, "step": 0.01}),
                "room_tone": ("BOOLEAN", {"default": True}),
                "pitch_drift": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.05}),
                "loudness_variation": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.5, "step": 0.05}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 2147483647}),
                "max_chars": ("INT", {"default": 420, "min": 120, "max": 1200}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("audio_path", "metadata_json")
    FUNCTION = "synthesize"
    CATEGORY = "audio/fish-speech"

    def synthesize(
        self,
        text,
        api_url,
        language,
        temperature,
        top_p,
        long_form,
        speaker="",
        reference_audio="",
        reference_text="",
        preset="sleep_safe",
        breath_amount=0.04,
        room_tone=True,
        pitch_drift=0.35,
        loudness_variation=0.35,
        seed=42,
        max_chars=420,
    ):
        endpoint = api_url
        if long_form and endpoint.endswith("/v1/tts"):
            endpoint = endpoint[: -len("/v1/tts")] + "/v1/long-form"
        payload = {
            "text": text,
            "language": language,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "seed": int(seed),
        }

        if long_form:
            payload["max_chars"] = int(max_chars)
            payload["export_mp3"] = True
            payload["preset"] = str(preset)
            payload["breath_amount"] = float(breath_amount)
            payload["room_tone"] = bool(room_tone)
            payload["pitch_drift"] = float(pitch_drift)
            payload["loudness_variation"] = float(loudness_variation)

        if speaker.strip():
            payload["speaker"] = speaker.strip()
        if reference_audio.strip():
            payload["reference_audio"] = str(Path(reference_audio.strip()))
        if reference_text.strip():
            payload["reference_text"] = reference_text.strip()

        response = requests.post(endpoint, json=payload, timeout=1800)
        response.raise_for_status()
        data = response.json()
        return (data.get("audio_path", data.get("output_wav", "")), json.dumps(data, ensure_ascii=False, indent=2))


NODE_CLASS_MAPPINGS = {
    "FishSpeechAPITTS": FishSpeechAPITTS,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FishSpeechAPITTS": "Fish Speech API TTS",
}

