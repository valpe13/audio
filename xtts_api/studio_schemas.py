from typing import Any, Optional

from pydantic import BaseModel, Field


class SplitRequest(BaseModel):
    text: str
    max_chars: int = Field(default=190, ge=60, le=320)
    split_pause_after_min: float = Field(default=0.18, ge=0.0, le=30.0)
    split_pause_after_max: float = Field(default=0.35, ge=0.0, le=30.0)
    generate_group_prompts: bool | None = None


class ChunkUpdate(BaseModel):
    text: str | None = None
    tts_text: str | None = None
    pause_after: float | None = Field(default=None, ge=0.0, le=30.0)
    order: int | None = None
    image_prompt: str | None = None
    image_negative_prompt: str | None = None
    animation_positive_prompt: str | None = None
    animation_negative_prompt: str | None = None
    grok_video_prompt: str | None = None
    prompt_context_note: str | None = None
    prompt_source: str | None = None


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
    image_grok_resolution: str | None = None
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
    image_no_text: bool | None = None
    project_visual_context: str | None = None
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
    ai_generate_group_prompts_on_split: bool | None = None


class TextValue(BaseModel):
    text: str


class QueueRequest(BaseModel):
    chunk_ids: list[str]


class VersionSelect(BaseModel):
    version_id: str


class MusicEnvelopePoint(BaseModel):
    time: float = Field(default=0.0, ge=0.0)
    volume: float = Field(default=0.18, ge=0.0, le=2.0)


class MainTimelineSpeedEnvelopePoint(BaseModel):
    time: float = Field(default=0.0, ge=0.0)
    speed: float = Field(default=1.0, ge=0.25, le=2.0)


VideoSpeedEnvelopePoint = MainTimelineSpeedEnvelopePoint


class VoiceArrangementUpdate(BaseModel):
    volume_envelope: list[MusicEnvelopePoint] = Field(default_factory=list)


class MusicArrangementUpdate(BaseModel):
    mode: Optional[str] = None
    volume_envelope: Optional[list[MusicEnvelopePoint]] = None
    sources: Optional[list[dict[str, Any]]] = None
    lanes: Optional[list[dict[str, Any]]] = None
    tracks: Optional[list[dict[str, Any]]] = None


class VideoArrangementUpdate(BaseModel):
    speed_envelope: Optional[list[MainTimelineSpeedEnvelopePoint]] = None
    main_timeline_speed_envelope: Optional[list[MainTimelineSpeedEnvelopePoint]] = None


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
    scheduled: bool | None = None
    kind: str | None = None
    source: str | None = None
    source_id: str | None = None
    timeline_source: str | None = None
    auto_sequence_id: str | None = None
    chunk_id: str | None = None
    prompt_scope: str | None = None
    prompt_source: str | None = None
    provider: str | None = None
    model: str | None = None
    positive_prompt: str | None = None
    negative_prompt: str | None = None
    fit: str = Field(default="cover")
    volume: float | None = Field(default=None, ge=0.0, le=2.0)


class GroupUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    chunk_ids: list[str] | None = None
    visual_prompt: str | None = None
    visual_context: str | None = None
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
    subtitle_defaults: dict[str, Any] | None = None
    subtitle_blocks: list[dict[str, Any]] | None = None


class GroupCreate(BaseModel):
    title: str = ""
    summary: str = ""
    chunk_ids: list[str] = Field(default_factory=list)
    insert_after_group_id: str | None = None


class GroupSplitRequest(BaseModel):
    chunks_per_group: int = Field(default=4, ge=1, le=100)


class GroupMoveRequest(BaseModel):
    direction: str | None = None
    order: int | None = None


class GroupImageRequest(BaseModel):
    force: bool = False


class ChunkImageRequest(BaseModel):
    force: bool = False
    replace: bool = False
    missing_only: bool = True


class GroupImagesRequest(BaseModel):
    missing_only: bool = True
    force: bool = False


class ChunkImagesRequest(BaseModel):
    missing_only: bool = True
    force: bool = False
    replace: bool = False
    images_per_chunk: int = Field(default=2, ge=1, le=4)


class ChunkVideoRequest(BaseModel):
    force: bool = False
    replace: bool = False
    missing_only: bool = False


class ChunkVideosRequest(BaseModel):
    missing_only: bool = True
    force: bool = False
    replace: bool = False


class GroupVideosRequest(BaseModel):
    missing_only: bool = True
    force: bool = False


class GroupVideoRequest(BaseModel):
    force: bool = False
    source_media_id: str | None = None


class ChunkPromptItem(BaseModel):
    id: str
    image_prompt: str | None = None
    image_negative_prompt: str | None = None
    animation_positive_prompt: str | None = None
    animation_negative_prompt: str | None = None
    grok_video_prompt: str | None = None
    prompt_context_note: str | None = None
    prompt_source: str | None = None


class ChunkPromptsUpdate(BaseModel):
    chunks: list[ChunkPromptItem] = Field(default_factory=list)


class BulkPromptGenerationRequest(BaseModel):
    missing_only: bool = True


class BulkSubtitlesRequest(BaseModel):
    missing_only: bool = True
    mode: str = "chunks"
    subtitle_defaults: dict[str, Any] | None = None


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
    export_scope: str = Field(default="full")
    group_ids: list[str] = Field(default_factory=list)
    separate_groups: bool = False


class ProjectCreate(BaseModel):
    name: str = Field(default="New project", min_length=1, max_length=120)
    initial_text: str = ""


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class TextImportRequest(BaseModel):
    text: str
    mode: str = Field(default="replace")
