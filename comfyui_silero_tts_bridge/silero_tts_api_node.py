from __future__ import annotations

import json
from pathlib import Path

import requests


class SileroRUTTSAPI:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": "Добрый вечер. Это тест Silero TTS на русском языке."}),
                "api_url": ("STRING", {"default": "http://127.0.0.1:7866/v1/tts"}),
                "speaker": (["baya", "kseniya", "xenia", "aidar", "eugene", "random"], {"default": "baya"}),
                "sample_rate": (["48000", "24000", "8000"], {"default": "48000"}),
                "output_path": ("STRING", {"default": "silero_tts_api/outputs/comfyui_silero_ru.wav"}),
                "realism_enabled": ("BOOLEAN", {"default": False}),
                "preset": (["sleep_soft", "sleep_safe", "natural_lecture", "experimental_realism"], {"default": "sleep_soft"}),
                "pause_scale": ("FLOAT", {"default": 0.9, "min": 0.2, "max": 2.2, "step": 0.01}),
                "breath_amount": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 0.3, "step": 0.01}),
                "room_tone": ("BOOLEAN", {"default": True}),
                "loudness_variation": ("FLOAT", {"default": 0.11, "min": 0.0, "max": 1.5, "step": 0.01}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 2147483647}),
                "speed": ("FLOAT", {"default": 0.9, "min": 0.5, "max": 2.0, "step": 0.01}),
                "soften": ("BOOLEAN", {"default": True}),
                "target_peak": ("FLOAT", {"default": 0.76, "min": 0.45, "max": 0.95, "step": 0.01}),
                "tone_softening": ("FLOAT", {"default": 0.34, "min": 0.0, "max": 0.75, "step": 0.01}),
                "sleep_softness": ("FLOAT", {"default": 0.55, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("audio_path", "metadata_json")
    FUNCTION = "synthesize"
    CATEGORY = "audio/silero-tts"

    def synthesize(self, text, api_url, speaker, sample_rate, output_path, realism_enabled, preset, pause_scale, breath_amount, room_tone, loudness_variation, seed, speed, soften, target_peak, tone_softening, sleep_softness):
        payload = {
            "text": text,
            "speaker": speaker,
            "sample_rate": int(sample_rate),
            "output_path": str(Path(output_path)) if output_path.strip() else None,
            "realism_enabled": bool(realism_enabled),
            "preset": preset,
            "pause_scale": float(pause_scale),
            "breath_amount": float(breath_amount),
            "room_tone": bool(room_tone),
            "loudness_variation": float(loudness_variation),
            "seed": int(seed),
            "soften": bool(soften),
            "target_peak": float(target_peak),
            "tone_softening": float(tone_softening),
            "sleep_softness": float(sleep_softness),
        }
        if abs(float(speed) - 1.0) > 0.001:
            payload["speed"] = float(speed)
        response = requests.post(api_url, json=payload, timeout=1800)
        response.raise_for_status()
        data = response.json()
        return (data.get("audio_path", ""), json.dumps(data, ensure_ascii=False, indent=2))


NODE_CLASS_MAPPINGS = {
    "SileroRUTTSAPI": SileroRUTTSAPI,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SileroRUTTSAPI": "Silero RU TTS API",
}

