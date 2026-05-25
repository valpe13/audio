import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    from project_compat import extract_legacy_chunks
    from pronunciation_preprocess import load_pronunciation_dictionary, preprocess_tts_text
    from studio_static_files import NoStoreStaticFiles
    from studio_audio_helpers import append_crossfaded, clamp_pause, clip_effective_duration, envelope_values, room_tone, sanitize_bitrate
    from studio_schemas import (
        ExportRequest,
        GroupUpdate,
        VideoGroupsAiRequest,
    )
    from studio_text import (
        chunk_tts_source_text,
        clean_text,
        compact_stress_validation_text,
        ensure_chunk_stress_fields,
        normalize_tts_backend as normalize_tts_backend_with_default,
        repair_mojibake_text,
        repair_project_mojibake_fields,
        sanitize_split_chunk_for_response,
        split_text_into_chunks,
    )
    from studio_json_helpers import extract_json_object, resolve_xai_text_model as resolve_xai_text_model_base
    from studio_generation_settings import image_settings as image_settings_base, video_i2v_settings as video_i2v_settings_base
    from studio_prompt_helpers import (
        DEFAULT_ANIMATION_NEGATIVE_PROMPT,
        DEFAULT_ANIMATION_POSITIVE_PROMPT,
        NO_PEOPLE_IMAGE_NEGATIVE,
        NO_PEOPLE_VISUAL_INSTRUCTION,
        NO_TEXT_IMAGE_INSTRUCTION,
        NO_TEXT_IMAGE_NEGATIVE,
        append_unique_csv_terms,
        apply_no_text_to_prompts,
        build_animation_positive_prompt,
        build_video_group_visual_context,
        build_grok_imagine_video_request_payload,
        build_grok_image_request_metadata,
        build_grok_image_request_payload,
        grok_image_dimensions_from_settings,
        grok_image_model_from_settings,
        format_grok_imagine_video_status_error,
        format_grok_imagine_video_timeout_error,
        format_unsupported_grok_imagine_video_resolution_error,
        format_xai_image_missing_url_error,
        grok_image_negative_prompt_from_bundle,
        grok_image_positive_prompt_from_bundle,
        grok_image_aspect_ratio_from_settings,
        format_grok_image_generation_prompt,
        format_grok_image_request_prompt,
        format_animatediff_prompt,
        format_grok_imagine_video_prompt,
        grok_imagine_video_diagnostics_aspect_ratio_behavior,
        grok_imagine_video_diagnostics_defaults,
        grok_imagine_video_diagnostics_docs,
        grok_imagine_video_diagnostics_quality_options,
        grok_imagine_video_diagnostics_warnings,
        grok_imagine_video_resolution_options,
        grok_imagine_video_api_key_blockers,
        normalize_grok_video_download_suffix,
        normalize_grok_imagine_video_duration,
        normalize_grok_imagine_video_resolution,
        group_visual_context,
        image_orientation_phrase,
        looks_like_ancient_prehistory_scene,
        no_text_images_enabled,
        normalize_animation_negative_prompt,
        normalize_animation_positive_prompt,
        normalize_grok_video_prompt,
        project_visual_context,
        truncate_text,
        visual_context_prefix,
    )
    from studio_media_meta import (
        format_ffmpeg_concat_file,
        group_chunk_id_strings,
        group_chunk_media_items,
        make_media_stats_helpers,
        normalize_group_media_duration,
        normalize_group_image_meta,
        normalize_group_media_layout,
        normalize_group_media_item,
        normalize_group_media_items,
        normalize_group_video_meta,
    )
    from studio_project_route_checks import make_project_route_checks
    from studio_routes_basic import register_basic_routes, route_availability_summary as route_availability_summary_for_app
    from studio_routes_chunks_export import register_chunk_export_routes
    from studio_routes_diagnostics import register_diagnostics_routes
    from studio_routes_media import register_media_routes
    from studio_routes_project_active import register_project_active_routes
    from studio_routes_project_group_prompts import register_project_group_prompt_routes
    from studio_routes_project_media_generation import register_project_media_generation_routes
    from studio_routes_project_index import register_project_index_routes
    from studio_routes_project_read import register_project_read_routes
    from studio_routes_project_settings import register_project_settings_routes
    from studio_routes_project_write import register_project_write_routes
    from studio_routes_queue_read import register_queue_read_routes
    from studio_routes_queue_write import register_queue_write_routes
    from studio_chunk_factory import create_chunk_dict as create_chunk_dict_base, get_selected_version, make_chunk_pause_helpers, normalize_chunk_versions, reset_current_chunk_audio_selection, selected_chunk_audio_path as selected_chunk_audio_path_base, sync_chunk_to_selected_version
    from studio_ai_stress import add_ai_stress_to_chunks_safe as add_ai_stress_to_chunks_safe_base
    from studio_tts_generation import make_tts_generation_helpers
    from studio_media_task_enqueue import make_media_task_enqueue_helpers
    from studio_chunk_media_generation import make_chunk_media_generation_helpers
    from studio_queue_runtime import make_queue_runtime_helpers
    from studio_group_media import make_group_media_helpers
    from studio_chunk_prompts import CHUNK_PROMPT_LIMITS, make_chunk_prompt_helpers
    from studio_video_groups_ai import make_video_group_ai_helpers, make_video_group_prompt_helpers
    from studio_comfyui import make_comfyui_helpers
    from studio_comfyui import compile_animatediff_i2v_workflow as compile_animatediff_i2v_workflow_base, compile_animatediff_sdxl_i2v_workflow as compile_animatediff_sdxl_i2v_workflow_base, compile_svd_i2v_workflow as compile_svd_i2v_workflow_base
    from studio_comfyui_runtime import make_comfyui_runtime_helpers
    from studio_comfyui_workflows import make_comfyui_workflow_helpers
    from studio_grok_video import make_grok_video_helpers
    from studio_image_generation import make_image_generation_helpers
    from studio_export import make_export_helpers
    from studio_project_store import (
        active_project_id as active_project_id_base,
        apply_safe_secret_settings as apply_safe_secret_settings_base,
        create_project_storage as create_project_storage_base,
        default_project as default_project_base,
        ensure_dirs as ensure_dirs_base,
        ensure_project_dirs as ensure_project_dirs_base,
        load_project as load_project_base,
        load_project_secrets as load_project_secrets_base,
        load_projects_index as load_projects_index_base,
        make_project_store_bindings,
        normalize_project_arrangement as normalize_project_arrangement_base,
        project_chunks_dir as project_chunks_dir_base,
        project_dir as project_dir_base,
        project_exports_dir as project_exports_dir_base,
        project_images_dir as project_images_dir_base,
        project_outputs_dir as project_outputs_dir_base,
        project_path as project_path_base,
        project_secrets_path as project_secrets_path_base,
        project_uploads_dir as project_uploads_dir_base,
        project_videos_dir as project_videos_dir_base,
        resolve_xai_api_key as resolve_xai_api_key_base,
        safe_project_id as safe_project_id_base,
        save_project as save_project_base,
        save_project_secrets as save_project_secrets_base,
        save_projects_index as save_projects_index_base,
        set_active_project as set_active_project_base,
        set_status as set_status_base,
        slugify_project_name as slugify_project_name_base,
        xai_api_key_hint as xai_api_key_hint_base,
    )
    from studio_storage import chunk_order_ids, group_chunk_sequence_id, normalize_loaded_chunk_legacy_version, normalize_loaded_chunk_selected_version, normalize_loaded_project_basics, normalize_project_metadata, ordered_project_chunks, prepare_active_project_index_update, prepare_active_project_response, prepare_clear_completed_tasks_response, prepare_created_project_response, prepare_deleted_project_response, prepare_loaded_projects_index, prepare_optional_queued_task_response, prepare_optional_queued_tasks_response, prepare_patched_project_response, prepare_project_create_index_update, prepare_project_delete_index_update, prepare_project_queue_progress_response, prepare_project_save_index_update, prepare_projects_index, prepare_queue_progress_response, prepare_queued_task_response, prepare_queued_tasks_empty_skipped_response, prepare_queued_tasks_plain_response, prepare_queued_tasks_response, prepare_queued_tasks_skipped_response, project_metadata_from_project, renumber_project_chunks, validate_project_id
    from studio_subtitles import (
        build_ass_dialogue_lines,
        build_ass_style_lines,
        build_subtitle_export_diagnostics,
        clamp_subtitle_events_to_duration,
        format_ass_document,
        normalize_subtitle_blocks,
        normalize_subtitle_defaults,
        prepare_styled_ass_events,
        subtitle_event_model_for_block,
    )
    from studio_video_geometry import (
        GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS,
        active_visual_group_media_at,
        animatediff_combined_node_names,
        animatediff_missing_node_names,
        animatediff_motion_model_suffixes,
        animatediff_required_node_names,
        animatediff_sdxl_optional_node_names,
        animatediff_sdxl_target_dimensions_for_source,
        animatediff_target_dimensions_for_source,
        calculate_video_source_offset,
        clamp_video_speed,
        comfyui_node_inputs_for_object_info,
        comfyui_video_output_suffixes,
        export_visual_segment_timing,
        fallback_visual_media_item,
        format_export_visual_segment_filename,
        format_experimental_sdxl_path_warning,
        format_ffmpeg_executable_arg,
        format_ffmpeg_still_image_segment_filter,
        format_ffmpeg_video_segment_filter,
        format_ffmpeg_visual_filter,
        format_comfyui_object_info_unavailable_blocker,
        format_incompatible_sdxl_motion_model_blocker,
        format_missing_sd15_checkpoint_blocker,
        format_missing_sd15_motion_model_blocker,
        format_missing_sdxl_checkpoint_blocker,
        format_missing_sdxl_motion_model_blocker,
        format_missing_comfyui_nodes_blocker,
        format_optional_sdxl_helper_nodes_warning,
        grok_imagine_video_resolution,
        group_time_ranges,
        is_video_source_path,
        looks_like_sd15_checkpoint,
        looks_like_sdxl_checkpoint,
        looks_like_sdxl_motion_model,
        main_timeline_speed_is_constant,
        normalize_speed_envelope_points,
        normalized_main_timeline_speed_envelope,
        parse_video_source_duration,
        resolve_export_dimensions,
        rounded_video_dimension,
        scheduled_group_media_items,
        scheduled_visual_image_media_items,
        source_image_aspect_ratio,
        split_range_by_group_media_timeline,
        svd_source_dimensions,
        video_i2v_backend_label,
        video_i2v_preset_option,
        video_i2v_preset_string_options,
         video_i2v_style_capped_int_setting,
         video_i2v_style_capped_int_value,
        video_i2v_style_delta_int_value,
        video_i2v_style_float_value,
        video_i2v_style_int_value,
        video_i2v_svd_numeric_options,
        visual_segment_source_value,
        wrap_video_source_offset,
    )
    from xai_client import download_http_file, extract_xai_image_url, save_xai_image_url, xai_json_request
except ImportError:  # pragma: no cover - package-style imports
    from .project_compat import extract_legacy_chunks
    from .pronunciation_preprocess import load_pronunciation_dictionary, preprocess_tts_text
    from .studio_static_files import NoStoreStaticFiles
    from .studio_audio_helpers import append_crossfaded, clamp_pause, clip_effective_duration, envelope_values, room_tone, sanitize_bitrate
    from .studio_schemas import (
        ExportRequest,
        GroupUpdate,
        VideoGroupsAiRequest,
    )
    from .studio_text import (
        chunk_tts_source_text,
        clean_text,
        compact_stress_validation_text,
        ensure_chunk_stress_fields,
        normalize_tts_backend as normalize_tts_backend_with_default,
        repair_mojibake_text,
        repair_project_mojibake_fields,
        sanitize_split_chunk_for_response,
        split_text_into_chunks,
    )
    from .studio_json_helpers import extract_json_object, resolve_xai_text_model as resolve_xai_text_model_base
    from .studio_generation_settings import image_settings as image_settings_base, video_i2v_settings as video_i2v_settings_base
    from .studio_prompt_helpers import (
        DEFAULT_ANIMATION_NEGATIVE_PROMPT,
        DEFAULT_ANIMATION_POSITIVE_PROMPT,
        NO_PEOPLE_IMAGE_NEGATIVE,
        NO_PEOPLE_VISUAL_INSTRUCTION,
        NO_TEXT_IMAGE_INSTRUCTION,
        NO_TEXT_IMAGE_NEGATIVE,
        append_unique_csv_terms,
        apply_no_text_to_prompts,
        build_animation_positive_prompt,
        build_video_group_visual_context,
        build_grok_imagine_video_request_payload,
        build_grok_image_request_metadata,
        build_grok_image_request_payload,
        grok_image_dimensions_from_settings,
        grok_image_model_from_settings,
        format_grok_imagine_video_status_error,
        format_grok_imagine_video_timeout_error,
        format_unsupported_grok_imagine_video_resolution_error,
        format_xai_image_missing_url_error,
        grok_image_negative_prompt_from_bundle,
        grok_image_positive_prompt_from_bundle,
        grok_image_aspect_ratio_from_settings,
        format_grok_image_generation_prompt,
        format_grok_image_request_prompt,
        format_animatediff_prompt,
        format_grok_imagine_video_prompt,
        grok_imagine_video_diagnostics_aspect_ratio_behavior,
        grok_imagine_video_diagnostics_defaults,
        grok_imagine_video_diagnostics_docs,
        grok_imagine_video_diagnostics_quality_options,
        grok_imagine_video_diagnostics_warnings,
        grok_imagine_video_resolution_options,
        grok_imagine_video_api_key_blockers,
        normalize_grok_video_download_suffix,
        normalize_grok_imagine_video_duration,
        normalize_grok_imagine_video_resolution,
        group_visual_context,
        image_orientation_phrase,
        looks_like_ancient_prehistory_scene,
        no_text_images_enabled,
        normalize_animation_negative_prompt,
        normalize_animation_positive_prompt,
        normalize_grok_video_prompt,
        project_visual_context,
        truncate_text,
        visual_context_prefix,
    )
    from .studio_media_meta import (
        format_ffmpeg_concat_file,
        group_chunk_id_strings,
        group_chunk_media_items,
        make_media_stats_helpers,
        normalize_group_media_duration,
        normalize_group_image_meta,
        normalize_group_media_layout,
        normalize_group_media_item,
        normalize_group_media_items,
        normalize_group_video_meta,
    )
    from .studio_project_route_checks import make_project_route_checks
    from .studio_routes_basic import register_basic_routes, route_availability_summary as route_availability_summary_for_app
    from .studio_routes_chunks_export import register_chunk_export_routes
    from .studio_routes_diagnostics import register_diagnostics_routes
    from .studio_routes_media import register_media_routes
    from .studio_routes_project_active import register_project_active_routes
    from .studio_routes_project_group_prompts import register_project_group_prompt_routes
    from .studio_routes_project_media_generation import register_project_media_generation_routes
    from .studio_routes_project_index import register_project_index_routes
    from .studio_routes_project_read import register_project_read_routes
    from .studio_routes_project_settings import register_project_settings_routes
    from .studio_routes_project_write import register_project_write_routes
    from .studio_routes_queue_read import register_queue_read_routes
    from .studio_routes_queue_write import register_queue_write_routes
    from .studio_chunk_factory import create_chunk_dict as create_chunk_dict_base, get_selected_version, make_chunk_pause_helpers, normalize_chunk_versions, reset_current_chunk_audio_selection, selected_chunk_audio_path as selected_chunk_audio_path_base, sync_chunk_to_selected_version
    from .studio_ai_stress import add_ai_stress_to_chunks_safe as add_ai_stress_to_chunks_safe_base
    from .studio_tts_generation import make_tts_generation_helpers
    from .studio_media_task_enqueue import make_media_task_enqueue_helpers
    from .studio_chunk_media_generation import make_chunk_media_generation_helpers
    from .studio_queue_runtime import make_queue_runtime_helpers
    from .studio_group_media import make_group_media_helpers
    from .studio_chunk_prompts import CHUNK_PROMPT_LIMITS, make_chunk_prompt_helpers
    from .studio_video_groups_ai import make_video_group_ai_helpers, make_video_group_prompt_helpers
    from .studio_comfyui import make_comfyui_helpers
    from .studio_comfyui import compile_animatediff_i2v_workflow as compile_animatediff_i2v_workflow_base, compile_animatediff_sdxl_i2v_workflow as compile_animatediff_sdxl_i2v_workflow_base, compile_svd_i2v_workflow as compile_svd_i2v_workflow_base
    from .studio_comfyui_runtime import make_comfyui_runtime_helpers
    from .studio_comfyui_workflows import make_comfyui_workflow_helpers
    from .studio_grok_video import make_grok_video_helpers
    from .studio_image_generation import make_image_generation_helpers
    from .studio_export import make_export_helpers
    from .studio_project_store import (
        active_project_id as active_project_id_base,
        apply_safe_secret_settings as apply_safe_secret_settings_base,
        create_project_storage as create_project_storage_base,
        default_project as default_project_base,
        ensure_dirs as ensure_dirs_base,
        ensure_project_dirs as ensure_project_dirs_base,
        load_project as load_project_base,
        load_project_secrets as load_project_secrets_base,
        load_projects_index as load_projects_index_base,
        make_project_store_bindings,
        normalize_project_arrangement as normalize_project_arrangement_base,
        project_chunks_dir as project_chunks_dir_base,
        project_dir as project_dir_base,
        project_exports_dir as project_exports_dir_base,
        project_images_dir as project_images_dir_base,
        project_outputs_dir as project_outputs_dir_base,
        project_path as project_path_base,
        project_secrets_path as project_secrets_path_base,
        project_uploads_dir as project_uploads_dir_base,
        project_videos_dir as project_videos_dir_base,
        resolve_xai_api_key as resolve_xai_api_key_base,
        safe_project_id as safe_project_id_base,
        save_project as save_project_base,
        save_project_secrets as save_project_secrets_base,
        save_projects_index as save_projects_index_base,
        set_active_project as set_active_project_base,
        set_status as set_status_base,
        slugify_project_name as slugify_project_name_base,
        xai_api_key_hint as xai_api_key_hint_base,
    )
    from .studio_storage import chunk_order_ids, group_chunk_sequence_id, normalize_loaded_chunk_legacy_version, normalize_loaded_chunk_selected_version, normalize_loaded_project_basics, normalize_project_metadata, ordered_project_chunks, prepare_active_project_index_update, prepare_active_project_response, prepare_clear_completed_tasks_response, prepare_created_project_response, prepare_deleted_project_response, prepare_loaded_projects_index, prepare_optional_queued_task_response, prepare_optional_queued_tasks_response, prepare_patched_project_response, prepare_project_create_index_update, prepare_project_delete_index_update, prepare_project_queue_progress_response, prepare_project_save_index_update, prepare_projects_index, prepare_queue_progress_response, prepare_queued_task_response, prepare_queued_tasks_empty_skipped_response, prepare_queued_tasks_plain_response, prepare_queued_tasks_response, prepare_queued_tasks_skipped_response, project_metadata_from_project, renumber_project_chunks, validate_project_id
    from .studio_subtitles import (
        build_ass_dialogue_lines,
        build_ass_style_lines,
        build_subtitle_export_diagnostics,
        clamp_subtitle_events_to_duration,
        format_ass_document,
        normalize_subtitle_blocks,
        normalize_subtitle_defaults,
        prepare_styled_ass_events,
        subtitle_event_model_for_block,
    )
    from .studio_video_geometry import (
        GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS,
        active_visual_group_media_at,
        animatediff_combined_node_names,
        animatediff_missing_node_names,
        animatediff_motion_model_suffixes,
        animatediff_required_node_names,
        animatediff_sdxl_optional_node_names,
        animatediff_sdxl_target_dimensions_for_source,
        animatediff_target_dimensions_for_source,
        calculate_video_source_offset,
        clamp_video_speed,
        comfyui_node_inputs_for_object_info,
        comfyui_video_output_suffixes,
        export_visual_segment_timing,
        fallback_visual_media_item,
        format_export_visual_segment_filename,
        format_experimental_sdxl_path_warning,
        format_ffmpeg_executable_arg,
        format_ffmpeg_still_image_segment_filter,
        format_ffmpeg_video_segment_filter,
        format_ffmpeg_visual_filter,
        format_comfyui_object_info_unavailable_blocker,
        format_incompatible_sdxl_motion_model_blocker,
        format_missing_sd15_checkpoint_blocker,
        format_missing_sd15_motion_model_blocker,
        format_missing_sdxl_checkpoint_blocker,
        format_missing_sdxl_motion_model_blocker,
        format_missing_comfyui_nodes_blocker,
        format_optional_sdxl_helper_nodes_warning,
        grok_imagine_video_resolution,
        group_time_ranges,
        is_video_source_path,
        looks_like_sd15_checkpoint,
        looks_like_sdxl_checkpoint,
        looks_like_sdxl_motion_model,
        main_timeline_speed_is_constant,
        normalize_speed_envelope_points,
        normalized_main_timeline_speed_envelope,
        parse_video_source_duration,
        resolve_export_dimensions,
        rounded_video_dimension,
        scheduled_group_media_items,
        scheduled_visual_image_media_items,
        source_image_aspect_ratio,
        split_range_by_group_media_timeline,
        svd_source_dimensions,
        video_i2v_backend_label,
        video_i2v_preset_option,
        video_i2v_preset_string_options,
         video_i2v_style_capped_int_setting,
         video_i2v_style_capped_int_value,
        video_i2v_style_delta_int_value,
        video_i2v_style_float_value,
        video_i2v_style_int_value,
        video_i2v_svd_numeric_options,
        visual_segment_source_value,
        wrap_video_source_offset,
    )
    from .xai_client import download_http_file, extract_xai_image_url, save_xai_image_url, xai_json_request

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
STUDIO_BUILD = "2026-05-13-xtts-studio-visual-consistency"
SVD_HISTORY_WAIT_TIMEOUT_SECONDS = 1800.0
XAI_IMAGINE_VIDEO_POLL_TIMEOUT_SECONDS = 900.0
XAI_IMAGINE_VIDEO_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_PRONUNCIATION_DICTIONARY = API_DIR / "pronunciation_dictionary.json"
DEFAULT_SILERO_API_URL = "http://127.0.0.1:7866"

try:
    from studio_defaults import (
        ANCIENT_PREHISTORY_NEGATIVE,
        ANIMATEDIFF_MOTION_MODEL,
        ANIMATEDIFF_SDXL_ENV_MODEL,
        ANIMATEDIFF_SDXL_MODEL_CANDIDATES,
        COMMON_REALVISXL_NEGATIVE,
        DEFAULT_VIDEO_GROUP_NEGATIVE,
        GROK_IMAGE_MODEL,
        GROK_IMAGE_RESOLUTIONS,
        GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS,
        GROK_IMAGINE_VIDEO_MODEL,
        GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS,
        GROK_REFERENCE_LIMITATION_NOTE,
        IMAGE_QUALITY_PRESETS,
        IMAGE_STYLE_PRESETS,
        LEGACY_GROK_IMAGE_MODELS,
        REALVISXL_CHECKPOINT,
        SVD_XT_CHECKPOINT,
        VIDEO_I2V_MOTION_STYLE_PRESETS,
        VIDEO_I2V_QUALITY_PRESETS,
        build_default_settings,
    )
except ImportError:  # pragma: no cover - package-style imports
    from .studio_defaults import (
        ANCIENT_PREHISTORY_NEGATIVE,
        ANIMATEDIFF_MOTION_MODEL,
        ANIMATEDIFF_SDXL_ENV_MODEL,
        ANIMATEDIFF_SDXL_MODEL_CANDIDATES,
        COMMON_REALVISXL_NEGATIVE,
        DEFAULT_VIDEO_GROUP_NEGATIVE,
        GROK_IMAGE_MODEL,
        GROK_IMAGE_RESOLUTIONS,
        GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS,
        GROK_IMAGINE_VIDEO_MODEL,
        GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS,
        GROK_REFERENCE_LIMITATION_NOTE,
        IMAGE_QUALITY_PRESETS,
        IMAGE_STYLE_PRESETS,
        LEGACY_GROK_IMAGE_MODELS,
        REALVISXL_CHECKPOINT,
        SVD_XT_CHECKPOINT,
        VIDEO_I2V_MOTION_STYLE_PRESETS,
        VIDEO_I2V_QUALITY_PRESETS,
        build_default_settings,
    )

DEFAULT_SETTINGS = build_default_settings(ROOT, DEFAULT_REF, DEFAULT_PRONUNCIATION_DICTIONARY)


XAI_VIDEO_GROUPS_ATTEMPTS = 3
XAI_VIDEO_GROUPS_TIMEOUT_SECONDS = 120
XAI_VIDEO_GROUPS_RETRY_BASE_DELAY_SECONDS = 1.5



video_group_ai_helpers = make_video_group_ai_helpers({
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "XAI_VIDEO_GROUPS_ATTEMPTS": XAI_VIDEO_GROUPS_ATTEMPTS,
    "XAI_VIDEO_GROUPS_RETRY_BASE_DELAY_SECONDS": XAI_VIDEO_GROUPS_RETRY_BASE_DELAY_SECONDS,
    "XAI_VIDEO_GROUPS_TIMEOUT_SECONDS": XAI_VIDEO_GROUPS_TIMEOUT_SECONDS,
    "active_project_id": lambda: active_project_id(),
    "resolve_xai_api_key": lambda project, project_id: resolve_xai_api_key(project, project_id),
})
fallback_video_groups = video_group_ai_helpers["fallback_video_groups"]
normalize_video_groups = video_group_ai_helpers["normalize_video_groups"]
renumber_video_groups = video_group_ai_helpers["renumber_video_groups"]
generate_video_groups_ai = video_group_ai_helpers["generate_video_groups_ai"]


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
    return normalize_tts_backend_with_default(settings, default_backend=DEFAULT_SETTINGS["tts_backend"])


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


media_stats_helpers = make_media_stats_helpers(rel_path)
wav_stats = media_stats_helpers["wav_stats"]
media_stats = media_stats_helpers["media_stats"]


group_media_helpers = make_group_media_helpers({
    "find_video_group": lambda project, group_id: find_video_group(project, group_id),
    "image_settings": lambda project: image_settings(project),
    "normalize_group_media_item": normalize_group_media_item,
    "normalize_group_media_items": normalize_group_media_items,
    "normalize_subtitle_blocks": normalize_subtitle_blocks,
    "ordered_project_chunks": ordered_project_chunks,
    "scheduled_group_media_items": scheduled_group_media_items,
    "scheduled_visual_image_media_items": scheduled_visual_image_media_items,
    "truncate_text": truncate_text,
})
append_group_media_library_item = group_media_helpers["append_group_media_library_item"]
group_timeline_duration = group_media_helpers["group_timeline_duration"]
auto_place_generated_group_media = group_media_helpers["auto_place_generated_group_media"]
scheduled_group_image_items = group_media_helpers["scheduled_group_image_items"]
group_media_source_for_video = group_media_helpers["group_media_source_for_video"]
append_or_replace_group_video_media = group_media_helpers["append_or_replace_group_video_media"]
auto_chunk_sequence_state = group_media_helpers["auto_chunk_sequence_state"]
auto_chunk_image_sources_for_video = group_media_helpers["auto_chunk_image_sources_for_video"]
chunk_timeline_span = group_media_helpers["chunk_timeline_span"]
find_chunk_in_group = group_media_helpers["find_chunk_in_group"]
group_subtitle_blocks_from_chunks = group_media_helpers["group_subtitle_blocks_from_chunks"]
group_with_chunk_video_source = group_media_helpers["group_with_chunk_video_source"]

def add_ai_stress_to_chunks_safe(project: dict[str, Any], chunks: list[dict[str, Any]]) -> tuple[int, str]:
    return add_ai_stress_to_chunks_safe_base(
        project,
        chunks,
        default_settings=DEFAULT_SETTINGS,
        resolve_xai_api_key=resolve_xai_api_key,
        safe_project_id=safe_project_id,
        active_project_id=active_project_id,
        truncate_text=truncate_text,
        logger=LOGGER,
        retry_base_delay_seconds=XAI_VIDEO_GROUPS_RETRY_BASE_DELAY_SECONDS,
    )


project_store_bindings = make_project_store_bindings({
    "DEFAULT_OUTPUT_DIR": DEFAULT_OUTPUT_DIR,
    "DEFAULT_PROJECT_PATH": DEFAULT_PROJECT_PATH,
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "PROJECTS_DIR": PROJECTS_DIR,
    "PROJECTS_INDEX_PATH": PROJECTS_INDEX_PATH,
    "PROJECTS_ROOT": PROJECTS_ROOT,
    "PROJECT_SAVE_LOCK": PROJECT_SAVE_LOCK,
    "UPLOADS_DIR": UPLOADS_DIR,
    "create_video_group_dict": lambda: create_video_group_dict,
    "normalize_arrangement": lambda project: normalize_arrangement(project),
    "normalize_chunk_pauses": lambda project, chunk: normalize_chunk_pauses(project, chunk),
    "normalize_chunk_versions": normalize_chunk_versions,
    "renumber_video_groups": lambda: renumber_video_groups,
})
globals().update(project_store_bindings)


def normalize_arrangement(project: dict[str, Any]) -> None:
    return normalize_project_arrangement_base(
        project,
        default_settings=DEFAULT_SETTINGS,
        normalize_video_groups=normalize_video_groups,
        ordered_project_chunks=ordered_project_chunks,
        migrate_ungrouped_chunks_to_video_groups=migrate_ungrouped_chunks_to_video_groups,
        normalize_speed_envelope_points=normalize_speed_envelope_points,
    )


chunk_pause_helpers = make_chunk_pause_helpers({
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "hashlib": hashlib,
    "json": json,
})
pause_range_for_boundary = chunk_pause_helpers["pause_range_for_boundary"]
stable_split_pause_after = chunk_pause_helpers["stable_split_pause_after"]
normalize_chunk_pauses = chunk_pause_helpers["normalize_chunk_pauses"]


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
    return image_settings_base(
        project,
        default_settings=DEFAULT_SETTINGS,
        image_quality_presets=IMAGE_QUALITY_PRESETS,
        realvisxl_checkpoint=REALVISXL_CHECKPOINT,
        grok_image_model=GROK_IMAGE_MODEL,
        legacy_grok_image_models=LEGACY_GROK_IMAGE_MODELS,
        grok_image_resolutions=GROK_IMAGE_RESOLUTIONS,
    )


def video_i2v_settings(project: dict[str, Any]) -> dict[str, Any]:
    return video_i2v_settings_base(
        project,
        default_settings=DEFAULT_SETTINGS,
        video_i2v_quality_presets=VIDEO_I2V_QUALITY_PRESETS,
        video_i2v_motion_style_presets=VIDEO_I2V_MOTION_STYLE_PRESETS,
        grok_imagine_video_resolution_presets=grok_imagine_video_resolution_options(GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS),
        grok_imagine_video_confirmed_resolutions=GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS,
        grok_imagine_video_model=GROK_IMAGINE_VIDEO_MODEL,
    )


comfyui_helpers = make_comfyui_helpers({
    "ROOT": ROOT,
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "REALVISXL_CHECKPOINT": REALVISXL_CHECKPOINT,
    "ANIMATEDIFF_MOTION_MODEL": ANIMATEDIFF_MOTION_MODEL,
    "ANIMATEDIFF_SDXL_ENV_MODEL": ANIMATEDIFF_SDXL_ENV_MODEL,
    "ANIMATEDIFF_SDXL_MODEL_CANDIDATES": ANIMATEDIFF_SDXL_MODEL_CANDIDATES,
    "resolve_user_path": resolve_user_path,
    "rel_path": rel_path,
    "truncate_text": truncate_text,
    "animatediff_motion_model_suffixes": animatediff_motion_model_suffixes,
    "animatediff_required_node_names": animatediff_required_node_names,
    "animatediff_sdxl_optional_node_names": animatediff_sdxl_optional_node_names,
    "animatediff_missing_node_names": animatediff_missing_node_names,
    "animatediff_combined_node_names": animatediff_combined_node_names,
    "comfyui_node_inputs_for_object_info": comfyui_node_inputs_for_object_info,
    "looks_like_sd15_checkpoint": looks_like_sd15_checkpoint,
    "looks_like_sdxl_checkpoint": looks_like_sdxl_checkpoint,
    "looks_like_sdxl_motion_model": looks_like_sdxl_motion_model,
    "format_missing_comfyui_nodes_blocker": format_missing_comfyui_nodes_blocker,
    "format_comfyui_object_info_unavailable_blocker": format_comfyui_object_info_unavailable_blocker,
    "format_missing_sd15_motion_model_blocker": format_missing_sd15_motion_model_blocker,
    "format_missing_sd15_checkpoint_blocker": format_missing_sd15_checkpoint_blocker,
    "format_missing_sdxl_checkpoint_blocker": format_missing_sdxl_checkpoint_blocker,
    "format_missing_sdxl_motion_model_blocker": format_missing_sdxl_motion_model_blocker,
    "format_incompatible_sdxl_motion_model_blocker": format_incompatible_sdxl_motion_model_blocker,
    "format_optional_sdxl_helper_nodes_warning": format_optional_sdxl_helper_nodes_warning,
    "format_experimental_sdxl_path_warning": format_experimental_sdxl_path_warning,
})
comfyui_url = comfyui_helpers["comfyui_url"]
http_json_request = comfyui_helpers["http_json_request"]
comfyui_health = comfyui_helpers["comfyui_health"]
comfyui_model_check = comfyui_helpers["comfyui_model_check"]
comfyui_models_dir = comfyui_helpers["comfyui_models_dir"]
comfyui_model_files = comfyui_helpers["comfyui_model_files"]
find_sd15_checkpoint = comfyui_helpers["find_sd15_checkpoint"]
find_sdxl_checkpoint = comfyui_helpers["find_sdxl_checkpoint"]
find_sdxl_motion_model = comfyui_helpers["find_sdxl_motion_model"]
animatediff_node_diagnostics = comfyui_helpers["animatediff_node_diagnostics"]
animatediff_environment_diagnostics = comfyui_helpers["animatediff_environment_diagnostics"]
animatediff_sdxl_node_diagnostics = comfyui_helpers["animatediff_sdxl_node_diagnostics"]
animatediff_sdxl_environment_diagnostics = comfyui_helpers["animatediff_sdxl_environment_diagnostics"]
comfyui_default_launch_candidates = comfyui_helpers["comfyui_default_launch_candidates"]
launch_comfyui_candidate = comfyui_helpers["launch_comfyui_candidate"]
start_comfyui_if_needed = comfyui_helpers["start_comfyui_if_needed"]
wait_for_comfyui = comfyui_helpers["wait_for_comfyui"]
comfyui_status = comfyui_helpers["comfyui_status"]

comfyui_runtime_helpers = make_comfyui_runtime_helpers({
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "active_project_id": active_project_id,
    "comfyui_url": comfyui_url,
    "comfyui_video_output_suffixes": comfyui_video_output_suffixes,
    "http_json_request": http_json_request,
    "project_images_dir": project_images_dir,
    "project_videos_dir": project_videos_dir,
    "rel_path": rel_path,
    "resolve_user_path": resolve_user_path,
    "safe_project_id": safe_project_id,
    "svd_source_dimensions": svd_source_dimensions,
    "truncate_text": truncate_text,
})
comfyui_submit_prompt = comfyui_runtime_helpers["comfyui_submit_prompt"]
comfyui_wait_history = comfyui_runtime_helpers["comfyui_wait_history"]
comfyui_first_output_image = comfyui_runtime_helpers["comfyui_first_output_image"]
comfyui_first_output_video = comfyui_runtime_helpers["comfyui_first_output_video"]
comfyui_download_image = comfyui_runtime_helpers["comfyui_download_image"]
comfyui_download_output = comfyui_runtime_helpers["comfyui_download_output"]
comfyui_output_dir = comfyui_runtime_helpers["comfyui_output_dir"]
comfyui_newest_video_by_prefix = comfyui_runtime_helpers["comfyui_newest_video_by_prefix"]
copy_comfyui_prefix_video_to_project = comfyui_runtime_helpers["copy_comfyui_prefix_video_to_project"]
copy_comfyui_animatediff_video_to_project = comfyui_runtime_helpers["copy_comfyui_animatediff_video_to_project"]

comfyui_workflow_helpers = make_comfyui_workflow_helpers({
    "ANIMATEDIFF_MOTION_MODEL": ANIMATEDIFF_MOTION_MODEL,
    "REALVISXL_CHECKPOINT": REALVISXL_CHECKPOINT,
    "SVD_HISTORY_WAIT_TIMEOUT_SECONDS": SVD_HISTORY_WAIT_TIMEOUT_SECONDS,
    "active_project_id": active_project_id,
    "animatediff_environment_diagnostics": animatediff_environment_diagnostics,
    "animatediff_sdxl_environment_diagnostics": animatediff_sdxl_environment_diagnostics,
    "animatediff_sdxl_target_dimensions_for_source": animatediff_sdxl_target_dimensions_for_source,
    "animatediff_target_dimensions_for_source": animatediff_target_dimensions_for_source,
    "comfyui_download_image": comfyui_download_image,
    "comfyui_download_output": comfyui_download_output,
    "comfyui_first_output_image": comfyui_first_output_image,
    "comfyui_first_output_video": comfyui_first_output_video,
    "comfyui_newest_video_by_prefix": comfyui_newest_video_by_prefix,
    "comfyui_submit_prompt": comfyui_submit_prompt,
    "comfyui_video_output_suffixes": comfyui_video_output_suffixes,
    "comfyui_wait_history": comfyui_wait_history,
    "compile_animatediff_i2v_workflow_base": compile_animatediff_i2v_workflow_base,
    "compile_animatediff_sdxl_i2v_workflow_base": compile_animatediff_sdxl_i2v_workflow_base,
    "compile_svd_i2v_workflow_base": compile_svd_i2v_workflow_base,
    "copy_comfyui_animatediff_video_to_project": copy_comfyui_animatediff_video_to_project,
    "copy_comfyui_prefix_video_to_project": copy_comfyui_prefix_video_to_project,
    "format_animatediff_prompt": format_animatediff_prompt,
    "project_images_dir": project_images_dir,
    "project_videos_dir": project_videos_dir,
    "rel_path": rel_path,
    "resolve_user_path": resolve_user_path,
    "run_xai_grok_imagine_video_i2v_workflow": lambda project, group, settings, video_settings, output_prefix: run_xai_grok_imagine_video_i2v_workflow(project, group, settings, video_settings, output_prefix),
    "safe_project_id": safe_project_id,
    "svd_source_dimensions": svd_source_dimensions,
    "truncate_text": truncate_text,
    "wait_for_comfyui": wait_for_comfyui,
})
animatediff_missing_dependency_error = comfyui_workflow_helpers["animatediff_missing_dependency_error"]
run_comfyui_animatediff_i2v_workflow = comfyui_workflow_helpers["run_comfyui_animatediff_i2v_workflow"]
run_comfyui_animatediff_sdxl_i2v_workflow = comfyui_workflow_helpers["run_comfyui_animatediff_sdxl_i2v_workflow"]
run_comfyui_svd_i2v_workflow = comfyui_workflow_helpers["run_comfyui_svd_i2v_workflow"]
run_comfyui_video_i2v_workflow = comfyui_workflow_helpers["run_comfyui_video_i2v_workflow"]
run_comfyui_workflow = comfyui_workflow_helpers["run_comfyui_workflow"]


chunk_media_generation_helpers = make_chunk_media_generation_helpers({
    "HTTPException": HTTPException,
    "active_project_id": active_project_id,
    "auto_chunk_image_sources_for_video": auto_chunk_image_sources_for_video,
    "auto_chunk_sequence_state": auto_chunk_sequence_state,
    "chunk_timeline_span": chunk_timeline_span,
    "find_chunk_in_group": find_chunk_in_group,
    "find_video_group": lambda project, group_id: find_video_group(project, group_id),
    "format_chunk_image_prompt": lambda project, group, chunk, settings: format_chunk_image_prompt(project, group, chunk, settings),
    "generate_group_image": lambda project, group, settings, prompt_bundle: generate_group_image(project, group, settings, prompt_bundle),
    "group_chunk_sequence_id": group_chunk_sequence_id,
    "group_with_chunk_video_source": group_with_chunk_video_source,
    "image_settings": image_settings,
    "normalize_group_image_meta": normalize_group_image_meta,
    "normalize_group_media_item": normalize_group_media_item,
    "normalize_group_media_items": normalize_group_media_items,
    "normalize_group_video_meta": normalize_group_video_meta,
    "run_comfyui_video_i2v_workflow": run_comfyui_video_i2v_workflow,
    "safe_project_id": safe_project_id,
    "video_i2v_settings": video_i2v_settings,
})
generate_chunk_image_now = chunk_media_generation_helpers["generate_chunk_image_now"]
generate_chunk_video_now = chunk_media_generation_helpers["generate_chunk_video_now"]
update_video_group_image = chunk_media_generation_helpers["update_video_group_image"]
update_video_group_video = chunk_media_generation_helpers["update_video_group_video"]


video_group_prompt_helpers = make_video_group_prompt_helpers({
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "fallback_video_groups": fallback_video_groups,
    "find_video_group": lambda project, group_id: find_video_group(project, group_id),
    "normalize_arrangement": normalize_arrangement,
    "normalize_group_media_duration": normalize_group_media_duration,
    "normalize_group_media_items": normalize_group_media_items,
    "normalize_group_media_layout": normalize_group_media_layout,
    "normalize_subtitle_blocks": normalize_subtitle_blocks,
    "ordered_project_chunks": ordered_project_chunks,
})
create_video_group_dict = video_group_prompt_helpers["create_video_group_dict"]
generate_prompt_for_group = video_group_prompt_helpers["generate_prompt_for_group"]
update_group_prompts = video_group_prompt_helpers["update_group_prompts"]


def find_video_group(project: dict[str, Any], group_id: str) -> dict[str, Any] | None:
    groups = project.get("arrangement", {}).get("video", {}).get("groups", [])
    return next((group for group in groups if isinstance(group, dict) and group.get("id") == group_id), None)


tts_generation_helpers = make_tts_generation_helpers({
    "MODEL_NAME": MODEL_NAME,
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "active_project_id": active_project_id,
    "chunk_tts_source_text": chunk_tts_source_text,
    "clean_text": clean_text,
    "http_json_request": http_json_request,
    "normalize_chunk_versions": normalize_chunk_versions,
    "normalize_tts_backend": normalize_tts_backend,
    "project_chunks_dir": project_chunks_dir,
    "rel_path": rel_path,
    "resolve_user_path": resolve_user_path,
    "tts_input_text": tts_input_text,
    "wav_stats": wav_stats,
})
generate_tts_chunk = tts_generation_helpers["generate_tts_chunk"]
generate_silero_chunk = tts_generation_helpers["generate_silero_chunk"]
generate_xtts_chunk = tts_generation_helpers["generate_xtts_chunk"]
get_tts_model = tts_generation_helpers["get_tts_model"]
is_tts_model_loaded = tts_generation_helpers["is_tts_model_loaded"]


queue_runtime_deps: dict[str, Any] = {
    "ExportRequest": ExportRequest,
    "VideoGroupsAiRequest": VideoGroupsAiRequest,
    "active_project_id": active_project_id,
    "append_or_replace_group_video_media": append_or_replace_group_video_media,
    "comfyui_newest_video_by_prefix": comfyui_newest_video_by_prefix,
    "copy_comfyui_prefix_video_to_project": copy_comfyui_prefix_video_to_project,
    "export_project_with_settings": lambda project, payload: export_project_with_settings(project, payload),
    "find_video_group": find_video_group,
    "format_image_prompt": lambda group, settings: format_image_prompt(group, settings),
    "generate_chunk_image_now": generate_chunk_image_now,
    "generate_chunk_video_now": generate_chunk_video_now,
    "generate_group_image": lambda project, group, settings, prompt_bundle: generate_group_image(project, group, settings, prompt_bundle),
    "generate_tts_chunk": lambda project, chunk: generate_tts_chunk(project, chunk),
    "generate_video_groups_ai": generate_video_groups_ai,
    "group_media_source_for_video": group_media_source_for_video,
    "image_settings": image_settings,
    "load_project": load_project,
    "normalize_arrangement": normalize_arrangement,
    "normalize_group_image_meta": normalize_group_image_meta,
    "normalize_group_video_meta": normalize_group_video_meta,
    "run_comfyui_video_i2v_workflow": run_comfyui_video_i2v_workflow,
    "safe_project_id": safe_project_id,
    "save_project": save_project,
    "set_status": set_status,
    "task_is_queued_or_running": lambda task: task_is_queued_or_running(task),
    "update_video_group_image": update_video_group_image,
    "update_video_group_video": update_video_group_video,
    "video_i2v_backend_label": video_i2v_backend_label,
    "video_i2v_settings": video_i2v_settings,
}
queue_runtime_helpers = make_queue_runtime_helpers(queue_runtime_deps)
_queue_lock = queue_runtime_helpers["_queue_lock"]
_task_queue = queue_runtime_helpers["_task_queue"]
_tasks = queue_runtime_helpers["_tasks"]
progress_snapshot = queue_runtime_helpers["progress_snapshot"]
queue_snapshot = queue_runtime_helpers["queue_snapshot"]
set_progress = queue_runtime_helpers["set_progress"]
ensure_worker = queue_runtime_helpers["ensure_worker"]
enqueue_task = queue_runtime_helpers["enqueue_task"]
active_task_by_kind_project = queue_runtime_helpers["active_task_by_kind_project"]
update_task = queue_runtime_helpers["update_task"]
remove_task = queue_runtime_helpers["remove_task"]
clear_completed_tasks = queue_runtime_helpers["clear_completed_tasks"]
move_task = queue_runtime_helpers["move_task"]
rebuild_queue_locked = queue_runtime_helpers["rebuild_queue_locked"]
queue_worker = queue_runtime_helpers["queue_worker"]


export_helpers = make_export_helpers({
    "ROOT": ROOT,
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "active_project_id": active_project_id,
    "active_visual_group_media_at": active_visual_group_media_at,
    "append_crossfaded": append_crossfaded,
    "build_ass_dialogue_lines": build_ass_dialogue_lines,
    "build_ass_style_lines": build_ass_style_lines,
    "build_subtitle_export_diagnostics": build_subtitle_export_diagnostics,
    "calculate_video_source_offset": calculate_video_source_offset,
    "clamp_subtitle_events_to_duration": clamp_subtitle_events_to_duration,
    "clamp_video_speed": clamp_video_speed,
    "clip_effective_duration": clip_effective_duration,
    "envelope_values": envelope_values,
    "export_visual_segment_timing": export_visual_segment_timing,
    "fallback_visual_media_item": fallback_visual_media_item,
    "format_ass_document": format_ass_document,
    "format_export_visual_segment_filename": format_export_visual_segment_filename,
    "format_ffmpeg_concat_file": format_ffmpeg_concat_file,
    "format_ffmpeg_executable_arg": format_ffmpeg_executable_arg,
    "format_ffmpeg_still_image_segment_filter": format_ffmpeg_still_image_segment_filter,
    "format_ffmpeg_video_segment_filter": format_ffmpeg_video_segment_filter,
    "format_ffmpeg_visual_filter": format_ffmpeg_visual_filter,
    "group_subtitle_blocks_from_chunks": group_subtitle_blocks_from_chunks,
    "group_time_ranges": group_time_ranges,
    "image_settings": image_settings,
    "is_video_source_path": is_video_source_path,
    "main_timeline_speed_is_constant": main_timeline_speed_is_constant,
    "media_stats": media_stats,
    "normalize_arrangement": normalize_arrangement,
    "normalize_chunk_pauses": normalize_chunk_pauses,
    "normalize_chunk_versions": normalize_chunk_versions,
    "normalize_group_media_items": normalize_group_media_items,
    "normalize_subtitle_blocks": normalize_subtitle_blocks,
    "normalize_subtitle_defaults": normalize_subtitle_defaults,
    "normalized_main_timeline_speed_envelope": normalized_main_timeline_speed_envelope,
    "parse_video_source_duration": parse_video_source_duration,
    "prepare_styled_ass_events": prepare_styled_ass_events,
    "project_exports_dir": project_exports_dir,
    "rel_path": rel_path,
    "resolve_export_dimensions": resolve_export_dimensions,
    "resolve_user_path": resolve_user_path,
    "room_tone": room_tone,
    "safe_project_id": safe_project_id,
    "sanitize_bitrate": sanitize_bitrate,
    "save_project": save_project,
    "selected_chunk_audio_path": lambda chunk: selected_chunk_audio_path_base(chunk, resolve_user_path),
    "subtitle_event_model_for_block": subtitle_event_model_for_block,
    "visual_segment_source_value": visual_segment_source_value,
    "wav_stats": wav_stats,
    "wrap_video_source_offset": wrap_video_source_offset,
})
build_export_visual_segments = export_helpers["build_export_visual_segments"]
build_visual_segment = export_helpers["build_visual_segment"]
export_audio_file = export_helpers["export_audio_file"]
export_project = export_helpers["export_project"]
export_project_with_settings = export_helpers["export_project_with_settings"]
export_subtitle_events = export_helpers["export_subtitle_events"]
export_video_file = export_helpers["export_video_file"]
locate_ffmpeg = export_helpers["locate_ffmpeg"]
mix_music_clip = export_helpers["mix_music_clip"]
mix_music_lane = export_helpers["mix_music_lane"]
project_for_export_scope = export_helpers["project_for_export_scope"]
read_audio_mono = export_helpers["read_audio_mono"]
render_project_audio = export_helpers["render_project_audio"]
run_ffmpeg = export_helpers["run_ffmpeg"]
subtitle_events_for_export_duration = export_helpers["subtitle_events_for_export_duration"]
write_export_subtitles_ass = export_helpers["write_export_subtitles_ass"]


grok_video_helpers = make_grok_video_helpers({
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS": GROK_IMAGINE_VIDEO_CONFIRMED_ASPECT_RATIOS,
    "GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS": GROK_IMAGINE_VIDEO_CONFIRMED_RESOLUTIONS,
    "GROK_IMAGINE_VIDEO_MODEL": GROK_IMAGINE_VIDEO_MODEL,
    "GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS": GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS,
    "XAI_IMAGINE_VIDEO_POLL_INTERVAL_SECONDS": XAI_IMAGINE_VIDEO_POLL_INTERVAL_SECONDS,
    "XAI_IMAGINE_VIDEO_POLL_TIMEOUT_SECONDS": XAI_IMAGINE_VIDEO_POLL_TIMEOUT_SECONDS,
    "active_project_id": active_project_id,
    "build_grok_imagine_video_request_payload": build_grok_imagine_video_request_payload,
    "download_http_file": download_http_file,
    "format_grok_imagine_video_prompt": format_grok_imagine_video_prompt,
    "grok_imagine_video_api_key_blockers": grok_imagine_video_api_key_blockers,
    "grok_imagine_video_diagnostics_aspect_ratio_behavior": grok_imagine_video_diagnostics_aspect_ratio_behavior,
    "grok_imagine_video_diagnostics_defaults": grok_imagine_video_diagnostics_defaults,
    "grok_imagine_video_diagnostics_docs": grok_imagine_video_diagnostics_docs,
    "grok_imagine_video_diagnostics_quality_options": grok_imagine_video_diagnostics_quality_options,
    "grok_imagine_video_diagnostics_warnings": grok_imagine_video_diagnostics_warnings,
    "format_grok_imagine_video_status_error": format_grok_imagine_video_status_error,
    "format_grok_imagine_video_timeout_error": format_grok_imagine_video_timeout_error,
    "image_settings": image_settings,
    "locate_ffmpeg": locate_ffmpeg,
    "normalize_grok_imagine_video_duration": normalize_grok_imagine_video_duration,
    "normalize_grok_imagine_video_resolution": normalize_grok_imagine_video_resolution,
    "normalize_grok_video_download_suffix": normalize_grok_video_download_suffix,
    "project_videos_dir": project_videos_dir,
    "rel_path": rel_path,
    "resolve_user_path": resolve_user_path,
    "resolve_xai_api_key": resolve_xai_api_key,
    "run_ffmpeg": run_ffmpeg,
    "safe_project_id": safe_project_id,
    "source_image_aspect_ratio": source_image_aspect_ratio,
    "svd_source_dimensions": svd_source_dimensions,
    "truncate_text": truncate_text,
    "video_i2v_settings": video_i2v_settings,
    "xai_json_request": xai_json_request,
    "xai_api_key_hint": xai_api_key_hint,
})
grok_imagine_video_diagnostics = grok_video_helpers["grok_imagine_video_diagnostics"]
locate_ffprobe_for_ffmpeg = grok_video_helpers["locate_ffprobe_for_ffmpeg"]
ffprobe_duration_sec = grok_video_helpers["ffprobe_duration_sec"]
postprocess_grok_loop_video = grok_video_helpers["postprocess_grok_loop_video"]
run_xai_grok_imagine_video_i2v_workflow = grok_video_helpers["run_xai_grok_imagine_video_i2v_workflow"]


image_generation_helpers = make_image_generation_helpers({
    "ANCIENT_PREHISTORY_NEGATIVE": ANCIENT_PREHISTORY_NEGATIVE,
    "COMMON_REALVISXL_NEGATIVE": COMMON_REALVISXL_NEGATIVE,
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "GROK_IMAGE_MODEL": GROK_IMAGE_MODEL,
    "GROK_IMAGE_RESOLUTIONS": GROK_IMAGE_RESOLUTIONS,
    "GROK_REFERENCE_LIMITATION_NOTE": GROK_REFERENCE_LIMITATION_NOTE,
    "IMAGE_STYLE_PRESETS": IMAGE_STYLE_PRESETS,
    "NO_PEOPLE_IMAGE_NEGATIVE": NO_PEOPLE_IMAGE_NEGATIVE,
    "NO_PEOPLE_VISUAL_INSTRUCTION": NO_PEOPLE_VISUAL_INSTRUCTION,
    "active_project_id": active_project_id,
    "append_unique_csv_terms": append_unique_csv_terms,
    "apply_no_text_to_prompts": apply_no_text_to_prompts,
    "build_grok_image_request_metadata": build_grok_image_request_metadata,
    "build_grok_image_request_payload": build_grok_image_request_payload,
    "extract_xai_image_url": extract_xai_image_url,
    "format_grok_image_request_prompt": format_grok_image_request_prompt,
    "format_xai_image_missing_url_error": format_xai_image_missing_url_error,
    "generate_fallback_chunk_prompts": lambda project, group: generate_fallback_chunk_prompts(project, group),
    "grok_image_dimensions_from_settings": grok_image_dimensions_from_settings,
    "grok_image_model_from_settings": grok_image_model_from_settings,
    "grok_image_negative_prompt_from_bundle": grok_image_negative_prompt_from_bundle,
    "image_orientation_phrase": image_orientation_phrase,
    "looks_like_ancient_prehistory_scene": looks_like_ancient_prehistory_scene,
    "project_images_dir": project_images_dir,
    "rel_path": rel_path,
    "resolve_user_path": resolve_user_path,
    "resolve_xai_api_key": resolve_xai_api_key,
    "run_comfyui_workflow": run_comfyui_workflow,
    "safe_project_id": safe_project_id,
    "save_xai_image_url": save_xai_image_url,
    "truncate_text": truncate_text,
    "visual_context_prefix": visual_context_prefix,
    "xai_json_request": xai_json_request,
})
compile_sdxl_txt2img_workflow = image_generation_helpers["compile_sdxl_txt2img_workflow"]
format_chunk_image_prompt = image_generation_helpers["format_chunk_image_prompt"]
format_image_prompt = image_generation_helpers["format_image_prompt"]
generate_group_placeholder_svg = image_generation_helpers["generate_group_placeholder_svg"]
generate_group_image = image_generation_helpers["generate_group_image"]
run_xai_grok_image_workflow = image_generation_helpers["run_xai_grok_image_workflow"]


app = FastAPI(title="XTTS Studio", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:7870"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def route_availability_summary() -> dict[str, Any]:
    return route_availability_summary_for_app(app)


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
register_basic_routes(app, {
    "STATIC_DIR": STATIC_DIR,
    "STUDIO_BUILD": STUDIO_BUILD,
    "load_project": load_project,
    "project_path": project_path,
    "rel_path": rel_path,
    "route_availability_summary": route_availability_summary,
    "is_tts_model_loaded": is_tts_model_loaded,
    "server_file": str(Path(__file__).resolve()),
    "module_name": __name__,
})


register_diagnostics_routes(app, {
    "load_project": load_project,
    "image_settings": image_settings,
    "comfyui_status": comfyui_status,
    "comfyui_health": comfyui_health,
    "comfyui_url": comfyui_url,
    "comfyui_model_files": comfyui_model_files,
    "animatediff_environment_diagnostics": animatediff_environment_diagnostics,
    "animatediff_sdxl_environment_diagnostics": animatediff_sdxl_environment_diagnostics,
    "find_sd15_checkpoint": find_sd15_checkpoint,
    "find_sdxl_checkpoint": find_sdxl_checkpoint,
    "find_sdxl_motion_model": find_sdxl_motion_model,
    "grok_imagine_video_diagnostics": grok_imagine_video_diagnostics,
    "ANIMATEDIFF_MOTION_MODEL": ANIMATEDIFF_MOTION_MODEL,
    "ANIMATEDIFF_SDXL_ENV_MODEL": ANIMATEDIFF_SDXL_ENV_MODEL,
    "ANIMATEDIFF_SDXL_MODEL_CANDIDATES": ANIMATEDIFF_SDXL_MODEL_CANDIDATES,
})


register_media_routes(app, {
    "resolve_user_path": resolve_user_path,
    "PROJECTS_ROOT": PROJECTS_ROOT,
    "PROJECTS_DIR": PROJECTS_DIR,
})


register_project_read_routes(app, {
    "load_project": load_project,
    "enrich_project": enrich_project,
    "HTTPException": HTTPException,
})


register_project_index_routes(app, {
    "load_projects_index": load_projects_index,
})


register_project_active_routes(app, {
    "active_project_id": active_project_id,
    "load_project": load_project,
    "enrich_project": enrich_project,
})


register_queue_read_routes(app, {
    "active_project_id": active_project_id,
    "queue_snapshot": queue_snapshot,
    "progress_snapshot": progress_snapshot,
})


register_queue_write_routes(app, {
    "active_project_id": active_project_id,
    "clear_completed_tasks": clear_completed_tasks,
    "enqueue_task": enqueue_task,
    "enrich_project": enrich_project,
    "load_project": load_project,
    "move_task": move_task,
    "prepare_clear_completed_tasks_response": prepare_clear_completed_tasks_response,
    "prepare_queue_progress_response": prepare_queue_progress_response,
    "prepare_queued_task_response": prepare_queued_task_response,
    "prepare_queued_tasks_plain_response": prepare_queued_tasks_plain_response,
    "progress_snapshot": progress_snapshot,
    "queue_snapshot": queue_snapshot,
    "remove_task": remove_task,
    "set_status": set_status,
})


media_task_enqueue_helpers = make_media_task_enqueue_helpers({
    "active_project_id": active_project_id,
    "enqueue_task": enqueue_task,
    "find_chunk_in_group": find_chunk_in_group,
    "find_video_group": find_video_group,
    "group_chunk_media_items": group_chunk_media_items,
    "normalize_group_media_items": normalize_group_media_items,
    "queue_lock": _queue_lock,
    "safe_project_id": safe_project_id,
    "scheduled_group_image_items": scheduled_group_image_items,
    "tasks": _tasks,
    "video_i2v_backend_label": video_i2v_backend_label,
    "video_i2v_settings": video_i2v_settings,
})
active_image_task_for_group = media_task_enqueue_helpers["active_image_task_for_group"]
active_chunk_image_task = media_task_enqueue_helpers["active_chunk_image_task"]
active_chunk_video_task = media_task_enqueue_helpers["active_chunk_video_task"]
active_video_task_for_group = media_task_enqueue_helpers["active_video_task_for_group"]
enqueue_chunk_image_task = media_task_enqueue_helpers["enqueue_chunk_image_task"]
enqueue_chunk_video_task = media_task_enqueue_helpers["enqueue_chunk_video_task"]
enqueue_group_image_task = media_task_enqueue_helpers["enqueue_group_image_task"]
enqueue_group_video_task = media_task_enqueue_helpers["enqueue_group_video_task"]
group_chunk_image_count = media_task_enqueue_helpers["group_chunk_image_count"]
group_has_chunk_image = media_task_enqueue_helpers["group_has_chunk_image"]
group_has_chunk_video = media_task_enqueue_helpers["group_has_chunk_video"]
task_is_queued_or_running = media_task_enqueue_helpers["task_is_queued_or_running"]

project_route_checks = make_project_route_checks({
    "active_project_id": active_project_id,
    "clean_text": clean_text,
    "ordered_project_chunks": ordered_project_chunks,
    "queue_lock": _queue_lock,
    "resolve_xai_api_key": resolve_xai_api_key,
    "safe_project_id": safe_project_id,
    "task_is_queued_or_running": task_is_queued_or_running,
    "tasks": _tasks,
})
project_has_active_tasks = project_route_checks["project_has_active_tasks"]
validate_grok_groups_enqueue_request = project_route_checks["validate_grok_groups_enqueue_request"]

chunk_prompt_helpers = make_chunk_prompt_helpers({
    "active_project_id": active_project_id,
    "append_unique_csv_terms": append_unique_csv_terms,
    "build_animation_positive_prompt": build_animation_positive_prompt,
    "DEFAULT_ANIMATION_NEGATIVE_PROMPT": DEFAULT_ANIMATION_NEGATIVE_PROMPT,
    "DEFAULT_VIDEO_GROUP_NEGATIVE": DEFAULT_VIDEO_GROUP_NEGATIVE,
    "extract_json_object": extract_json_object,
    "format_grok_imagine_video_prompt": format_grok_imagine_video_prompt,
    "group_visual_context": group_visual_context,
    "no_text_images_enabled": no_text_images_enabled,
    "NO_TEXT_IMAGE_INSTRUCTION": NO_TEXT_IMAGE_INSTRUCTION,
    "NO_TEXT_IMAGE_NEGATIVE": NO_TEXT_IMAGE_NEGATIVE,
    "ordered_project_chunks": ordered_project_chunks,
    "project_visual_context": project_visual_context,
    "resolve_xai_api_key": resolve_xai_api_key,
    "resolve_xai_text_model": lambda project=None, override=None: resolve_xai_text_model_base(override),
    "safe_project_id": safe_project_id,
    "truncate_text": truncate_text,
    "XAI_VIDEO_GROUPS_TIMEOUT_SECONDS": XAI_VIDEO_GROUPS_TIMEOUT_SECONDS,
})
apply_chunk_prompt_items = chunk_prompt_helpers["apply_chunk_prompt_items"]
apply_chunk_prompt_items_missing_only = chunk_prompt_helpers["apply_chunk_prompt_items_missing_only"]
chunk_prompt_fields_are_empty = chunk_prompt_helpers["chunk_prompt_fields_are_empty"]
generate_chunk_prompt_items = chunk_prompt_helpers["generate_chunk_prompt_items"]
generate_fallback_chunk_prompts = chunk_prompt_helpers["generate_fallback_chunk_prompts"]
normalize_chunk_prompt_fields = chunk_prompt_helpers["normalize_chunk_prompt_fields"]


create_chunk_dict = lambda project, payload, order: create_chunk_dict_base(project, payload, order, normalize_chunk_pauses)
selected_chunk_audio_path = lambda chunk: selected_chunk_audio_path_base(chunk, resolve_user_path)


register_project_write_routes(app, {
    "create_project_storage": create_project_storage,
    "default_project": default_project,
    "enrich_project": enrich_project,
    "load_project": load_project,
    "load_projects_index": load_projects_index,
    "prepare_active_project_response": prepare_active_project_response,
    "prepare_created_project_response": prepare_created_project_response,
    "prepare_deleted_project_response": prepare_deleted_project_response,
    "prepare_patched_project_response": prepare_patched_project_response,
    "prepare_project_create_index_update": prepare_project_create_index_update,
    "prepare_project_delete_index_update": prepare_project_delete_index_update,
    "project_dir": project_dir,
    "project_has_active_tasks": project_has_active_tasks,
    "project_metadata_from_project": project_metadata_from_project,
    "repair_mojibake_text": repair_mojibake_text,
    "safe_project_id": safe_project_id,
    "save_project": save_project,
    "save_projects_index": save_projects_index,
    "set_active_project": set_active_project,
    "set_status": set_status,
    "slugify_project_name": slugify_project_name,
})


register_project_settings_routes(app, {
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "active_project_id": active_project_id,
    "apply_safe_secret_settings": apply_safe_secret_settings,
    "enrich_project": enrich_project,
    "load_project": load_project,
    "load_project_secrets": load_project_secrets,
    "normalize_arrangement": normalize_arrangement,
    "safe_project_id": safe_project_id,
    "save_project_secrets": save_project_secrets,
    "set_status": set_status,
})


register_project_group_prompt_routes(app, {
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "active_project_id": active_project_id,
    "active_task_by_kind_project": active_task_by_kind_project,
    "apply_chunk_prompt_items": apply_chunk_prompt_items,
    "apply_chunk_prompt_items_missing_only": apply_chunk_prompt_items_missing_only,
    "chunk_prompt_fields_are_empty": chunk_prompt_fields_are_empty,
    "enqueue_task": enqueue_task,
    "enrich_project": enrich_project,
    "fallback_video_groups": fallback_video_groups,
    "find_video_group": find_video_group,
    "generate_chunk_prompt_items": generate_chunk_prompt_items,
    "generate_prompt_for_group": generate_prompt_for_group,
    "group_subtitle_blocks_from_chunks": group_subtitle_blocks_from_chunks,
    "load_project": load_project,
    "normalize_arrangement": normalize_arrangement,
    "normalize_subtitle_defaults": normalize_subtitle_defaults,
    "ordered_project_chunks": ordered_project_chunks,
    "prepare_queued_task_response": prepare_queued_task_response,
    "progress_snapshot": progress_snapshot,
    "queue_snapshot": queue_snapshot,
    "renumber_video_groups": renumber_video_groups,
    "safe_project_id": safe_project_id,
    "set_status": set_status,
    "truncate_text": truncate_text,
    "update_group_prompts": update_group_prompts,
    "validate_grok_groups_enqueue_request": validate_grok_groups_enqueue_request,
})


register_project_media_generation_routes(app, {
    "active_project_id": active_project_id,
    "auto_chunk_image_sources_for_video": auto_chunk_image_sources_for_video,
    "auto_chunk_sequence_state": auto_chunk_sequence_state,
    "chunk_order_ids": chunk_order_ids,
    "create_video_group_dict": create_video_group_dict,
    "enqueue_chunk_image_task": enqueue_chunk_image_task,
    "enqueue_chunk_video_task": enqueue_chunk_video_task,
    "enqueue_group_image_task": enqueue_group_image_task,
    "enqueue_group_video_task": enqueue_group_video_task,
    "enrich_project": enrich_project,
    "find_video_group": find_video_group,
    "group_chunk_id_strings": group_chunk_id_strings,
    "group_chunk_sequence_id": group_chunk_sequence_id,
    "load_project": load_project,
    "normalize_arrangement": normalize_arrangement,
    "ordered_project_chunks": ordered_project_chunks,
    "prepare_optional_queued_task_response": prepare_optional_queued_task_response,
    "prepare_optional_queued_tasks_response": prepare_optional_queued_tasks_response,
    "prepare_queued_tasks_empty_skipped_response": prepare_queued_tasks_empty_skipped_response,
    "prepare_queued_tasks_response": prepare_queued_tasks_response,
    "prepare_queued_tasks_skipped_response": prepare_queued_tasks_skipped_response,
    "progress_snapshot": progress_snapshot,
    "queue_snapshot": queue_snapshot,
    "renumber_video_groups": renumber_video_groups,
    "safe_project_id": safe_project_id,
    "scheduled_group_image_items": scheduled_group_image_items,
    "set_status": set_status,
    "video_i2v_backend_label": video_i2v_backend_label,
    "video_i2v_settings": video_i2v_settings,
})


register_chunk_export_routes(app, {
    "add_ai_stress_to_chunks_safe": add_ai_stress_to_chunks_safe,
    "CHUNK_PROMPT_LIMITS": CHUNK_PROMPT_LIMITS,
    "clamp_pause": clamp_pause,
    "clean_text": clean_text,
    "compact_stress_validation_text": compact_stress_validation_text,
    "create_chunk_dict": create_chunk_dict,
    "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
    "enqueue_task": enqueue_task,
    "enrich_project": enrich_project,
    "ensure_chunk_stress_fields": ensure_chunk_stress_fields,
    "fallback_video_groups": fallback_video_groups,
    "load_project": load_project,
    "LOGGER": LOGGER,
    "normalize_arrangement": normalize_arrangement,
    "normalize_chunk_pauses": normalize_chunk_pauses,
    "normalize_chunk_prompt_fields": normalize_chunk_prompt_fields,
    "normalize_chunk_versions": normalize_chunk_versions,
    "pause_range_for_boundary": pause_range_for_boundary,
    "prepare_project_queue_progress_response": prepare_project_queue_progress_response,
    "prepare_queued_task_response": prepare_queued_task_response,
    "progress_snapshot": progress_snapshot,
    "project_uploads_dir": project_uploads_dir,
    "queue_snapshot": queue_snapshot,
    "rel_path": rel_path,
    "renumber_project_chunks": renumber_project_chunks,
    "repair_mojibake_text": repair_mojibake_text,
    "reset_current_chunk_audio_selection": reset_current_chunk_audio_selection,
    "sanitize_split_chunk_for_response": sanitize_split_chunk_for_response,
    "set_status": set_status,
    "split_text_into_chunks": split_text_into_chunks,
    "stable_split_pause_after": stable_split_pause_after,
    "sync_chunk_to_selected_version": sync_chunk_to_selected_version,
    "truncate_text": truncate_text,
})
app.mount("/studio", NoStoreStaticFiles(directory=str(STATIC_DIR), html=True, studio_build=STUDIO_BUILD), name="studio")

