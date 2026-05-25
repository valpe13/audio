from pathlib import Path
from typing import Any

REALVISXL_CHECKPOINT = "RealVisXL_V5.0_fp16.safetensors"
SVD_XT_CHECKPOINT = "svd_xt.safetensors"
GROK_IMAGINE_VIDEO_MODEL = "grok-imagine-video"
GROK_IMAGE_MODEL = "grok-imagine-image-quality"
LEGACY_GROK_IMAGE_MODELS = {"grok-2-image", "grok-2-image-1212", "grok-imagine-image-pro"}
GROK_IMAGE_RESOLUTIONS = {"1k", "2k"}
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
    "text, letters, captions, subtitles, signs, labels, watermark, logo, readable writing, UI, low quality, blurry, distorted anatomy, extra fingers, deformed hands, "
    "bad anatomy, missing fingers, bad eyes, duplicate people, cropped face, noisy, jpeg artifacts, "
    "overexposed, underexposed, oversaturated, cartoon, anime, cgi, plastic skin"
)
DEFAULT_VIDEO_GROUP_NEGATIVE = (
    "text, letters, captions, subtitles, UI, signs, labels, readable writing, watermark, logo, signature, low quality, blurry, out of focus, "
    "noisy, jpeg artifacts, overexposed, underexposed, oversaturated, cartoon, anime, cgi, "
    "plastic skin, distorted anatomy, bad anatomy, deformed hands, extra fingers, missing fingers, "
    "bad eyes, duplicate people, cropped face"
)
ANCIENT_PREHISTORY_NEGATIVE = (
    "modern clothing, business suit, office suit, shirt and tie, jacket, blazer, dress pants, modern shoes, "
    "sneakers, watch, glasses, phone, earbuds, backpack, plastic, flashlight, metal camping gear, city, office, "
    "modern buildings, cars, road, power lines, modern campfire scene, tourists, safari, cosplay, fantasy armor"
)
GROK_REFERENCE_LIMITATION_NOTE = (
    "Direct image reference conditioning is not implemented for xAI /v1/images/generations in XTTS Studio; "
    "consistency is prompt/context-based using project/group shared visual context."
)


def image_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    if mime not in {"image/png", "image/jpeg", "image/webp"}:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


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

def build_default_settings(root: Path, default_ref: Path, default_pronunciation_dictionary: Path) -> dict[str, Any]:
    return {
    "reference_path": str(default_ref.relative_to(root)),
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
    "image_provider": "grok",
    "image_model": "grok",
    "image_grok_model": GROK_IMAGE_MODEL,
    "image_grok_resolution": "1k",
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
    "image_no_text": True,
    "project_visual_context": "",
    "image_seed": 0,
    "image_steps": 22,
    "image_cfg": 6.0,
    "image_sampler": "dpmpp_2m_sde",
    "image_scheduler": "karras",
    "video_i2v_enabled": True,
    "video_i2v_quality_preset": "balanced",
    "video_i2v_motion_style": "ambient_nature",
    "video_i2v_workflow_mode": "generated_grok_imagine_video",
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
    "tts_pronunciation_dictionary_path": str(default_pronunciation_dictionary.relative_to(root)),
    "tts_stress_mark_style": "acute",
    "tts_backend": "xtts",
    "silero_api_url": "http://127.0.0.1:7866",
    "silero_speaker": "baya",
    "silero_sample_rate": 48000,
    "silero_realism_enabled": True,
    "silero_realism_preset": "sleep_safe",
    "ai_add_russian_stress_marks": False,
    "ai_stress_model": "",
    "ai_stress_batch_chunks": 2,
    "ai_stress_max_request_chars": 2500,
    "ai_stress_retries": 2,
    "ai_generate_group_prompts_on_split": True,
}


