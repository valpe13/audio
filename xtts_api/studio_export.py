import copy
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf
from fastapi import HTTPException

try:
    from studio_schemas import ExportRequest
except ImportError:  # pragma: no cover - package-style imports
    from .studio_schemas import ExportRequest


def make_export_helpers(ctx: dict[str, Any]) -> dict[str, Any]:
    ROOT = ctx["ROOT"]
    DEFAULT_SETTINGS = ctx["DEFAULT_SETTINGS"]
    active_project_id = ctx["active_project_id"]
    active_visual_group_media_at = ctx["active_visual_group_media_at"]
    append_crossfaded = ctx["append_crossfaded"]
    build_ass_dialogue_lines = ctx["build_ass_dialogue_lines"]
    build_ass_style_lines = ctx["build_ass_style_lines"]
    build_subtitle_export_diagnostics = ctx["build_subtitle_export_diagnostics"]
    calculate_video_source_offset = ctx["calculate_video_source_offset"]
    clamp_subtitle_events_to_duration = ctx["clamp_subtitle_events_to_duration"]
    clamp_video_speed = ctx["clamp_video_speed"]
    clip_effective_duration = ctx["clip_effective_duration"]
    envelope_values = ctx["envelope_values"]
    export_visual_segment_timing = ctx["export_visual_segment_timing"]
    fallback_visual_media_item = ctx["fallback_visual_media_item"]
    format_ass_document = ctx["format_ass_document"]
    format_export_visual_segment_filename = ctx["format_export_visual_segment_filename"]
    format_ffmpeg_concat_file = ctx["format_ffmpeg_concat_file"]
    format_ffmpeg_executable_arg = ctx["format_ffmpeg_executable_arg"]
    format_ffmpeg_still_image_segment_filter = ctx["format_ffmpeg_still_image_segment_filter"]
    format_ffmpeg_video_segment_filter = ctx["format_ffmpeg_video_segment_filter"]
    format_ffmpeg_visual_filter = ctx["format_ffmpeg_visual_filter"]
    group_subtitle_blocks_from_chunks = ctx["group_subtitle_blocks_from_chunks"]
    group_time_ranges = ctx["group_time_ranges"]
    image_settings = ctx["image_settings"]
    is_video_source_path = ctx["is_video_source_path"]
    main_timeline_speed_is_constant = ctx["main_timeline_speed_is_constant"]
    media_stats = ctx["media_stats"]
    normalize_arrangement = ctx["normalize_arrangement"]
    normalize_chunk_pauses = ctx["normalize_chunk_pauses"]
    normalize_chunk_versions = ctx["normalize_chunk_versions"]
    normalize_group_media_items = ctx["normalize_group_media_items"]
    normalize_subtitle_blocks = ctx["normalize_subtitle_blocks"]
    normalize_subtitle_defaults = ctx["normalize_subtitle_defaults"]
    normalized_main_timeline_speed_envelope = ctx["normalized_main_timeline_speed_envelope"]
    parse_video_source_duration = ctx["parse_video_source_duration"]
    prepare_styled_ass_events = ctx["prepare_styled_ass_events"]
    project_exports_dir = ctx["project_exports_dir"]
    rel_path = ctx["rel_path"]
    resolve_export_dimensions = ctx["resolve_export_dimensions"]
    resolve_user_path = ctx["resolve_user_path"]
    room_tone = ctx["room_tone"]
    safe_project_id = ctx["safe_project_id"]
    sanitize_bitrate = ctx["sanitize_bitrate"]
    save_project = ctx["save_project"]
    selected_chunk_audio_path = ctx["selected_chunk_audio_path"]
    subtitle_event_model_for_block = ctx["subtitle_event_model_for_block"]
    visual_segment_source_value = ctx["visual_segment_source_value"]
    wav_stats = ctx["wav_stats"]
    wrap_video_source_offset = ctx["wrap_video_source_offset"]

    def read_audio_mono(path: Path, target_sr: int | None = None) -> tuple[np.ndarray, int]:
        y, sr = sf.read(path, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = np.mean(y, axis=1)
        if target_sr and sr != target_sr:
            y = librosa.resample(y.astype(np.float32), orig_sr=sr, target_sr=target_sr)
            sr = target_sr
        return y.astype(np.float32), sr


    def mix_music_clip(music_mix: np.ndarray, music: np.ndarray, sr: int, start_sec: float, offset_sec: float, volume: float, duration_sec: float | None = None, volume_curve: np.ndarray | None = None) -> None:
        if music.size == 0 or music_mix.size == 0:
            return
        start = int(max(0.0, start_sec) * sr)
        if start >= len(music_mix):
            return
        offset = min(len(music), int(max(0.0, offset_sec) * sr))
        clip = music[offset:]
        if duration_sec is not None and duration_sec > 0:
            clip = clip[:int(duration_sec * sr)]
        if clip.size == 0:
            return
        available = len(music_mix) - start
        clip = clip[:available]
        base_volume = max(0.0, min(2.0, volume))
        if volume_curve is not None and volume_curve.size:
            curve = volume_curve[start:start + len(clip)]
            if curve.size < len(clip):
                curve = np.pad(curve, (0, len(clip) - curve.size), mode="edge")
            music_mix[start:start + len(clip)] += clip * base_volume * curve[:len(clip)]
        else:
            music_mix[start:start + len(clip)] += clip * base_volume


    def mix_music_lane(music_mix: np.ndarray, audio: np.ndarray, sr: int, lane: dict[str, Any], final_duration_sec: float) -> None:
        clips = lane.get("clips") if isinstance(lane.get("clips"), list) else []
        if audio.size == 0 or not clips:
            return
        lane_volume = max(0.0, min(2.0, float(lane.get("volume", 1.0) or 1.0)))
        lane_curve = envelope_values(
            lane.get("volume_envelope", []),
            len(music_mix),
            sr,
            1.0,
        )
        prepared: list[tuple[dict[str, Any], float, float]] = []
        for clip in clips:
            if not isinstance(clip, dict):
                continue
            start_sec = max(0.0, float(clip.get("start_time", 0.0) or 0.0))
            duration_sec = clip_effective_duration(audio, sr, clip)
            if duration_sec > 0:
                prepared.append((clip, start_sec, start_sec + duration_sec))
        if not prepared:
            return
        pattern_start = min(item[1] for item in prepared)
        pattern_end = max(item[2] for item in prepared)
        pattern_len = max(0.001, pattern_end - pattern_start)
        repeat_start = pattern_start
        while repeat_start < final_duration_sec:
            for clip, start_sec, _end_sec in prepared:
                clip_volume = max(0.0, min(2.0, float(clip.get("volume", 1.0) or 1.0)))
                duration_sec = clip_effective_duration(audio, sr, clip)
                mix_music_clip(
                    music_mix,
                    audio,
                    sr,
                    repeat_start + (start_sec - pattern_start),
                    float(clip.get("offset_sec", 0.0) or 0.0),
                    lane_volume * clip_volume,
                    duration_sec,
                    lane_curve,
                )
            if not lane.get("loop", False):
                break
            repeat_start += pattern_len


    def locate_ffmpeg(project: dict[str, Any] | None = None) -> str:
        settings = image_settings(project) if isinstance(project, dict) else {}
        candidates: list[Path] = []
        comfy_root = resolve_user_path(str(settings.get("comfyui_path") or DEFAULT_SETTINGS["image_comfyui_path"])) if settings else resolve_user_path(DEFAULT_SETTINGS["image_comfyui_path"])
        if comfy_root:
            candidates.extend([
                comfy_root / "ffmpeg.exe",
                comfy_root / "ComfyUI" / "ffmpeg.exe",
                comfy_root / "python_embeded" / "ffmpeg.exe",
            ])
        candidates.extend([ROOT / "ComfyUI_windows_portable" / "ffmpeg.exe", ROOT / "ffmpeg.exe"])
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return shutil.which("ffmpeg") or ""


    def run_ffmpeg(cmd: list[str], cwd: Path | None = None) -> None:
        proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "ffmpeg failed").strip()[:2000])


    def export_subtitle_events(project: dict[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for group, group_start, group_end in group_time_ranges(project):
            defaults = normalize_subtitle_defaults(group.get("subtitle_defaults"))
            raw_blocks = group.get("subtitle_blocks")
            if not raw_blocks:
                raw_blocks = group_subtitle_blocks_from_chunks(project, group)
            blocks = normalize_subtitle_blocks(raw_blocks, {**group, "duration": max(0.05, group_end - group_start), "subtitle_defaults": defaults})
            for block in blocks:
                merged = normalize_subtitle_defaults({**defaults, **block})
                styled_block = {**block, **merged}
                for event in subtitle_event_model_for_block(styled_block, group_start, group_end):
                    event["group_id"] = str(group.get("id") or "")
                    events.append(event)
        return sorted(events, key=lambda item: (float(item.get("start") or 0.0), float(item.get("end") or 0.0)))


    def write_export_subtitles_ass(project: dict[str, Any], width: int, height: int, out: Path, subtitle_events: list[dict[str, Any]] | None = None) -> bool:
        styled_events, style_values = prepare_styled_ass_events(subtitle_events if subtitle_events is not None else export_subtitle_events(project))
        events = build_ass_dialogue_lines(styled_events, width, height)
        if not events:
            return False
        style_lines = build_ass_style_lines(style_values, width, height)
        out.write_text(format_ass_document(width, height, style_lines, events), encoding="utf-8-sig")
        return True


    def project_for_export_scope(project: dict[str, Any], payload: ExportRequest) -> tuple[dict[str, Any], str]:
        scope = str(payload.export_scope or "full").strip().lower()
        if scope not in {"selected_groups", "all_groups_separate"}:
            return project, "full"
        selected_ids = {str(item) for item in (payload.group_ids or []) if str(item)}
        groups = [group for group in project.get("arrangement", {}).get("video", {}).get("groups", []) if isinstance(group, dict)]
        if scope == "all_groups_separate":
            selected = groups
        else:
            selected = [group for group in groups if str(group.get("id")) in selected_ids]
        if not selected:
            raise HTTPException(status_code=400, detail="No groups selected for export")
        original_ranges = group_time_ranges(project)
        selected_range_starts = [start for group, start, _end in original_ranges if str(group.get("id")) in {str(item.get("id")) for item in selected}]
        timeline_offset = min(selected_range_starts) if selected_range_starts else 0.0
        chunk_ids = {str(chunk_id) for group in selected for chunk_id in (group.get("chunk_ids") or [])}
        scoped = copy.deepcopy(project)
        scoped["chunks"] = [chunk for chunk in project.get("chunks", []) if str(chunk.get("id")) in chunk_ids]
        scoped.setdefault("arrangement", {}).setdefault("video", {})["groups"] = copy.deepcopy(selected)
        scoped["_export_scope"] = scope
        scoped["_export_timeline_offset_sec"] = round(max(0.0, float(timeline_offset or 0.0)), 3)
        return scoped, scope


    def subtitle_events_for_export_duration(project: dict[str, Any], duration: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Return subtitle events guaranteed to overlap the exported video timeline.

        Exported selected-group videos are rendered from a rebased audio/visual timeline
        that starts at 0. This function defensively clamps generated events to that final
        mux duration and exposes diagnostics so a "burned" status cannot hide an empty
        or out-of-range ASS file.
        """
        raw_events = export_subtitle_events(project)
        clamped, outside = clamp_subtitle_events_to_duration(raw_events, duration)
        diagnostics = build_subtitle_export_diagnostics(
            raw_events,
            clamped,
            outside,
            duration,
            project.get("_export_scope") or "full",
            project.get("_export_timeline_offset_sec", 0.0),
        )
        return clamped, diagnostics


    def build_visual_segment(project: dict[str, Any], group: dict[str, Any], duration: float, width: int, height: int, fps: int, fit: str, out: Path, speed: float = 1.0, local_start_sec: float = 0.0) -> bool:
        ffmpeg = locate_ffmpeg(project)
        video_meta = group.get("video") if isinstance(group.get("video"), dict) else {}
        image_meta = group.get("image") if isinstance(group.get("image"), dict) else {}
        local_start = max(0.0, float(local_start_sec or 0.0))
        media_items = normalize_group_media_items(group.get("media_items"), group)
        selected_media, has_scheduled_media = active_visual_group_media_at(group, media_items, local_start)
        if not selected_media and not has_scheduled_media:
            selected_media = fallback_visual_media_item(media_items)
        source_value = visual_segment_source_value(selected_media, video_meta, image_meta)
        source_path = resolve_user_path(source_value) if source_value else None
        if not source_path or not source_path.exists():
            return False
        vf = format_ffmpeg_visual_filter(width, height, fit)
        speed_value = clamp_video_speed(speed)
        out.parent.mkdir(parents=True, exist_ok=True)
        if is_video_source_path(source_path):
            source_offset = calculate_video_source_offset(selected_media, local_start)
            source_duration = parse_video_source_duration(selected_media)
            source_offset = wrap_video_source_offset(source_offset, source_duration)
            cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1"]
            if source_offset > 0.001:
                cmd += ["-ss", f"{source_offset:.3f}"]
            cmd += ["-i", str(source_path), "-t", f"{duration:.3f}", "-vf", format_ffmpeg_video_segment_filter(vf, fps, duration, speed_value), "-an", "-pix_fmt", "yuv420p", str(out)]
        else:
            cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-i", str(source_path), "-t", f"{duration:.3f}", "-vf", format_ffmpeg_still_image_segment_filter(vf, fps), "-an", "-pix_fmt", "yuv420p", str(out)]
        run_ffmpeg(cmd)
        return True

    def build_export_visual_segments(project: dict[str, Any], ranges: list[tuple[dict[str, Any], float, float]], duration: float, width: int, height: int, fps: int, fit: str, work_dir: Path, speed_points: list[dict[str, float]]) -> list[Path]:
        segments: list[Path] = []
        current = 0.0
        segment_index = 1
        for group, start, end in ranges:
            if start > current + 0.05:
                # Fill timeline gaps with the next group's still image/video if available; otherwise skip to the group.
                current = start
            range_end = min(end, duration)
            if range_end - current <= 0:
                continue
            media_items = normalize_group_media_items(group.get("media_items"), group)
            for seg_start, seg_end in split_range_by_group_media_timeline(current, range_end, group, start, speed_points, media_items):
                segment_duration, segment_speed = export_visual_segment_timing(seg_start, seg_end, speed_points)
                if segment_duration <= 0:
                    continue
                segment_path = work_dir / format_export_visual_segment_filename(segment_index)
                segment_index += 1
                if build_visual_segment(project, group, segment_duration, width, height, fps, fit, segment_path, speed=segment_speed, local_start_sec=seg_start - start):
                    segments.append(segment_path)
                    current = seg_end
            if current >= duration:
                break
        if current < duration - 0.05 and ranges:
            last_group = ranges[-1][0]
            tail_group_start = ranges[-1][1]
            tail_media_items = normalize_group_media_items(last_group.get("media_items"), last_group)
            for seg_start, seg_end in split_range_by_group_media_timeline(current, duration, last_group, tail_group_start, speed_points, tail_media_items):
                tail_path = work_dir / format_export_visual_segment_filename(segment_index)
                segment_index += 1
                tail_duration, tail_speed = export_visual_segment_timing(seg_start, seg_end, speed_points)
                if build_visual_segment(project, last_group, tail_duration, width, height, fps, fit, tail_path, speed=tail_speed, local_start_sec=seg_start - tail_group_start):
                    segments.append(tail_path)
        return segments


    def render_project_audio(project: dict[str, Any], *, target_sr: int | None = None, channels: int = 1) -> tuple[np.ndarray, int]:
        settings = project["settings"]
        chunks = sorted(project.get("chunks", []), key=lambda c: c.get("order", 0))
        rendered: list[np.ndarray] = []
        sr: int | None = None
        seed = int(settings.get("seed", DEFAULT_SETTINGS["seed"]))
        voice_cursor = 0
        voice_multiplier = envelope_values(
            project.get("arrangement", {}).get("voice", {}).get("volume_envelope", []),
            max(1, int(max(1.0, sum(float(c.get("duration_sec", 0.0) or 0.0) + float(c.get("pause_after", 0.0) or 0.0) for c in chunks)) * 48000)),
            48000,
            1.0,
        )
        for idx, chunk in enumerate(chunks):
            normalize_chunk_versions(chunk)
            normalize_chunk_pauses(project, chunk)
            audio_path = selected_chunk_audio_path(chunk)
            if not audio_path or not audio_path.exists():
                continue
            y, this_sr = read_audio_mono(audio_path, sr)
            sr = this_sr if sr is None else sr
            after = float(chunk.get("pause_after", 0.0))
            if sr != 48000 or len(voice_multiplier) < voice_cursor + len(y):
                voice_multiplier = envelope_values(
                    project.get("arrangement", {}).get("voice", {}).get("volume_envelope", []),
                    max(voice_cursor + len(y) + int(after * sr), 1),
                    sr,
                    1.0,
                )
            # Voice automation is a multiplier over the global voice_volume setting.
            y_voice = y * float(settings.get("voice_volume", 1.0)) * voice_multiplier[voice_cursor: voice_cursor + len(y)]
            append_crossfaded(rendered, y_voice, sr, float(settings.get("crossfade_sec", 0.055)))
            voice_cursor += len(y)
            if settings.get("room_tone", True):
                tone = room_tone(sr, after, seed + idx, float(settings.get("room_tone_level", 0.0012)))
                append_crossfaded(rendered, tone, sr, float(settings.get("crossfade_sec", 0.055)))
                voice_cursor += len(tone)
            else:
                silence = np.zeros(int(after * sr), dtype=np.float32)
                append_crossfaded(rendered, silence, sr, 0.0)
                voice_cursor += len(silence)

        if not rendered or sr is None:
            raise HTTPException(status_code=400, detail="No generated chunks to export.")
        final = np.concatenate(rendered).astype(np.float32)
        normalize_arrangement(project)
        music_cfg = project.get("arrangement", {}).get("music", {})
        music_lanes = [lane for lane in (music_cfg.get("lanes") or []) if isinstance(lane, dict) and lane.get("enabled", True) and lane.get("clips")]
        if music_lanes:
            music_mix = np.zeros(len(final), dtype=np.float32)
            audio_cache: dict[str, np.ndarray] = {}

            def lane_audio(lane: dict[str, Any]) -> np.ndarray | None:
                music_path = resolve_user_path(lane.get("path")) if lane.get("path") else None
                if not music_path or not music_path.exists():
                    return None
                key = str(music_path)
                if key not in audio_cache:
                    audio_cache[key], _ = read_audio_mono(music_path, sr)
                return audio_cache[key]

            for lane in music_lanes:
                audio = lane_audio(lane)
                if audio is None or audio.size == 0:
                    continue
                mix_music_lane(music_mix, audio, sr, lane, len(final) / sr)
            envelope = envelope_values(
                music_cfg.get("volume_envelope", []),
                len(final),
                sr,
                float(settings.get("music_volume", 0.18)),
            )
            music_mix = music_mix * envelope
            fade = min(len(music_mix) // 5, int(1.5 * sr))
            if fade > 1:
                music_mix[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
                music_mix[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
            final = final + music_mix
        peak = float(np.max(np.abs(final))) if final.size else 0.0
        if peak > 0.94:
            final = final * (0.94 / peak)
        final = np.clip(final, -0.98, 0.98).astype(np.float32)
        if target_sr and sr != target_sr:
            final = librosa.resample(final, orig_sr=sr, target_sr=target_sr).astype(np.float32)
            sr = target_sr
        speed_points = normalized_main_timeline_speed_envelope(project)
        constant_speed, speed_value = main_timeline_speed_is_constant(speed_points)
        if constant_speed and abs(speed_value - 1.0) > 0.001:
            final = librosa.effects.time_stretch(final.astype(np.float32), rate=speed_value).astype(np.float32)
        if channels == 2:
            final = np.column_stack([final, final]).astype(np.float32)
        return final, sr


    def export_audio_file(project: dict[str, Any], payload: ExportRequest | None = None) -> dict[str, Any]:
        request = payload or ExportRequest()
        audio_format = str(request.audio_format or "wav").strip().lower()
        if audio_format not in {"wav", "mp3", "m4a", "aac", "flac", "ogg", "opus"}:
            raise HTTPException(status_code=400, detail="audio_format must be wav, mp3, m4a, aac, flac, ogg, or opus")
        channels = 2 if int(request.channels or 1) == 2 else 1
        final, sr = render_project_audio(project, target_sr=request.sample_rate, channels=channels)
        pid = safe_project_id(str(project.get("id") or active_project_id()))
        out_dir = project_exports_dir(pid)
        out_dir.mkdir(parents=True, exist_ok=True)
        ext = "m4a" if audio_format in {"m4a", "aac"} else "ogg" if audio_format == "opus" else audio_format
        base = out_dir / f"final_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        wav_source = base.with_suffix(".wav")
        sf.write(wav_source, final, sr, subtype="PCM_16")
        if audio_format == "wav":
            out = wav_source
            result = wav_stats(out)
            result.update({"media_type": "audio", "format": "wav", "channels": channels})
        else:
            ffmpeg = locate_ffmpeg(project)
            if not ffmpeg:
                raise HTTPException(status_code=400, detail="ffmpeg was not found. Install ffmpeg on PATH or configure ComfyUI_windows_portable with ffmpeg.exe.")
            out = base.with_suffix(f".{ext}")
            cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_source)]
            bitrate = sanitize_bitrate(request.audio_bitrate, "192k")
            if audio_format == "mp3":
                cmd += ["-codec:a", "libmp3lame", "-b:a", bitrate]
            elif audio_format in {"m4a", "aac"}:
                cmd += ["-codec:a", "aac", "-b:a", bitrate]
            elif audio_format == "flac":
                cmd += ["-codec:a", "flac"]
            elif audio_format in {"ogg", "opus"}:
                cmd += ["-codec:a", "libopus", "-b:a", sanitize_bitrate(request.audio_bitrate, "128k")]
            run_ffmpeg(cmd + [str(out)])
            try:
                wav_source.unlink()
            except OSError:
                pass
            result = media_stats(out, sample_rate=sr, duration_sec=(len(final) / sr), media_type="audio")
            result.update({"channels": channels, "bitrate": bitrate})
        project["export"] = result
        project.setdefault("exports", []).append(result)
        save_project(project)
        return result


    def export_video_file(project: dict[str, Any], payload: ExportRequest) -> dict[str, Any]:
        ffmpeg = locate_ffmpeg(project)
        if not ffmpeg:
            raise HTTPException(status_code=400, detail="ffmpeg was not found. Install ffmpeg on PATH or configure ComfyUI_windows_portable with ffmpeg.exe.")
        ffmpeg_cmd = format_ffmpeg_executable_arg(ffmpeg)
        video_format = str(payload.video_format or "mp4").strip().lower()
        if video_format not in {"mp4", "webm", "mov"}:
            raise HTTPException(status_code=400, detail="video_format must be mp4, webm, or mov")
        img_settings = image_settings(project)
        source_width = int(img_settings.get("width") or DEFAULT_SETTINGS.get("image_width") or 896)
        source_height = int(img_settings.get("height") or DEFAULT_SETTINGS.get("image_height") or 1152)
        width, height, orientation = resolve_export_dimensions(payload.orientation, payload.resolution, source_width, source_height, img_settings.get("aspect_ratio"))
        fps = max(1, min(60, int(payload.fps or 30)))
        pid = safe_project_id(str(project.get("id") or active_project_id()))
        out_dir = project_exports_dir(pid)
        work_dir = out_dir / f"work_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        work_dir.mkdir(parents=True, exist_ok=True)
        work_dir_abs = work_dir.resolve()
        final_audio, sr = render_project_audio(project, target_sr=int(payload.sample_rate or 48000), channels=2)
        duration = len(final_audio) / float(sr)
        audio_wav = work_dir / "audio.wav"
        sf.write(audio_wav, final_audio, sr, subtype="PCM_16")
        ranges = group_time_ranges(project)
        speed_points = normalized_main_timeline_speed_envelope(project)
        speed_curve_applied = False
        speed_note = "global/main timeline speed disabled; export uses constant 1.0x generated audio/group-local timing"
        segments = build_export_visual_segments(project, ranges, duration, width, height, fps, str(payload.video_fit or "cover"), work_dir, speed_points)
        if not segments:
            raise HTTPException(status_code=400, detail="No group video/image assets found for video export. Generate at least one group image or video first.")
        concat_file = work_dir / "segments.txt"
        concat_file.write_text(format_ffmpeg_concat_file(segments), encoding="utf-8")
        visual_mp4 = work_dir / "visual.mp4"
        run_ffmpeg([ffmpeg_cmd, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(visual_mp4)])
        subtitle_ass = work_dir / "subtitles.ass"
        subtitle_visual = visual_mp4
        subtitle_events, subtitle_diagnostics = subtitle_events_for_export_duration(project, duration)
        subtitle_event_count = len(subtitle_events)
        subtitle_ass_created = write_export_subtitles_ass(project, width, height, subtitle_ass, subtitle_events)
        subtitle_ass_size = subtitle_ass.stat().st_size if subtitle_ass.exists() else 0
        subtitles_burned = False
        subtitle_burn_status = "no_events"
        subtitle_burn_error = ""
        final_video_input = visual_mp4
        if subtitle_ass_created:
            subtitle_burn_status = "attempted"
            # Use a short relative filename and run from the work directory. This avoids
            # Windows drive-colon escaping and non-ASCII OneDrive path parsing problems
            # in FFmpeg's subtitles filter while preserving normal absolute executable use.
            subtitle_visual = work_dir / "visual_subtitled.mp4"
            try:
                run_ffmpeg([
                    ffmpeg_cmd, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", "visual.mp4",
                    "-vf", "subtitles=subtitles.ass",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-an",
                    "visual_subtitled.mp4",
                ], cwd=work_dir_abs)
                subtitles_burned = subtitle_visual.exists() and subtitle_visual.stat().st_size > 0
                subtitle_burn_status = "burned" if subtitles_burned else "missing_output"
                if not subtitles_burned:
                    raise RuntimeError("FFmpeg subtitle burn completed without producing visual_subtitled.mp4")
                final_video_input = subtitle_visual
            except Exception as exc:
                subtitle_burn_error = str(exc)[:1000]
                subtitle_burn_status = "failed"
                raise RuntimeError(f"Subtitle burn-in failed after generating {subtitle_event_count} subtitle events at {subtitle_ass}: {subtitle_burn_error}") from exc
        elif subtitle_diagnostics.get("raw_event_count", 0) > 0:
            subtitle_burn_status = "events_outside_export_duration"
            raise RuntimeError(
                "Subtitle events were generated but none overlap the exported video duration "
                f"({subtitle_diagnostics.get('raw_event_count')} raw events, duration {duration:.3f}s, "
                f"scope {subtitle_diagnostics.get('export_scope')}, offset {subtitle_diagnostics.get('export_timeline_offset_sec')}s)"
            )
        ext = "mov" if video_format == "mov" else "webm" if video_format == "webm" else "mp4"
        out = out_dir / f"final_video_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"
        if video_format == "webm":
            cmd = [ffmpeg_cmd, "-y", "-hide_banner", "-loglevel", "error", "-i", str(final_video_input), "-i", str(audio_wav), "-t", f"{duration:.3f}", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34" if payload.video_quality == "small" else "30", "-c:a", "libopus", "-b:a", sanitize_bitrate(payload.audio_bitrate, "128k"), "-shortest", str(out)]
        else:
            crf = "28" if payload.video_quality == "small" else "18" if payload.video_quality == "high" else "23"
            cmd = [ffmpeg_cmd, "-y", "-hide_banner", "-loglevel", "error", "-i", str(final_video_input), "-i", str(audio_wav), "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", sanitize_bitrate(payload.audio_bitrate, "192k"), "-movflags", "+faststart", "-shortest", str(out)]
        run_ffmpeg(cmd)
        try:
            shutil.rmtree(work_dir)
        except OSError:
            pass
        result = media_stats(out, sample_rate=sr, duration_sec=duration, media_type="video")
        result.update({
            "width": width,
            "height": height,
            "orientation": orientation,
            "fps": fps,
            "container": video_format,
            "visual_segments": len(segments),
            "fit": str(payload.video_fit or "cover"),
            "speed_curve_applied": speed_curve_applied,
            "speed_curve_points": len(speed_points),
            "speed_curve_scope": "disabled_main_timeline",
            "speed_curve_note": speed_note,
            "subtitles_burned": subtitles_burned,
            "subtitle_event_count": subtitle_event_count,
            "subtitle_raw_event_count": subtitle_diagnostics.get("raw_event_count", subtitle_event_count),
            "subtitle_events_outside_export_duration": subtitle_diagnostics.get("events_outside_export_duration", 0),
            "subtitle_event_time_min": subtitle_diagnostics.get("event_time_min", 0.0),
            "subtitle_event_time_max": subtitle_diagnostics.get("event_time_max", 0.0),
            "subtitle_ass_created": subtitle_ass_created,
            "subtitle_ass_size": subtitle_ass_size,
            "subtitle_burn_status": subtitle_burn_status,
            "subtitle_burn_error": subtitle_burn_error,
            "subtitle_visual_input": "visual_subtitled.mp4" if final_video_input == subtitle_visual and subtitles_burned else "visual.mp4",
            "subtitle_export_timeline_offset_sec": subtitle_diagnostics.get("export_timeline_offset_sec", 0.0),
            "timeline_fidelity": "group ranges from chunk timings; scheduled group media blocks are selected by local timeline time like the main preview, global speed is ignored at 1.0x, subtitles are rebased/clamped to the exported group-local timeline, burned into the visual file, then muxed with audio",
        })
        project["export"] = result
        project.setdefault("exports", []).append(result)
        save_project(project)
        return result


    def export_project_with_settings(project: dict[str, Any], payload: ExportRequest | None = None) -> dict[str, Any]:
        request = payload or ExportRequest()
        scoped_project, scope = project_for_export_scope(project, request)
        if bool(request.separate_groups) or scope == "all_groups_separate":
            results: list[dict[str, Any]] = []
            groups = scoped_project.get("arrangement", {}).get("video", {}).get("groups", [])
            for group in groups:
                single_request = request.copy(update={"export_scope": "selected_groups", "group_ids": [str(group.get("id"))], "separate_groups": False})
                single_project, _ = project_for_export_scope(project, single_request)
                result = export_project_with_settings(single_project, single_request)
                result["group_id"] = group.get("id")
                result["group_title"] = group.get("title")
                results.append(result)
            summary = {"media_type": "batch", "format": request.video_format if request.export_type == "video" else request.audio_format, "files": results, "file_count": len(results), "export_scope": "all_groups_separate", "url": results[0].get("url") if results else ""}
            project["export"] = summary
            project.setdefault("exports", []).append(summary)
            save_project(project)
            return summary
        export_type = str(request.export_type or "audio").strip().lower()
        if export_type in {"video", "video_audio", "video_with_audio"}:
            result = export_video_file(scoped_project, request)
        else:
            result = export_audio_file(scoped_project, request)
        if scope != "full":
            result["export_scope"] = scope
            project["export"] = result
            project.setdefault("exports", []).append(result)
            save_project(project)
        return result


    def export_project(project: dict[str, Any]) -> dict[str, Any]:
        out = project_exports_dir(project.get("id") or active_project_id()) / f"final_{int(time.time())}.wav"
        final, sr = render_project_audio(project)
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out, final, sr, subtype="PCM_16")
        result = wav_stats(out)
        result.update({"media_type": "audio", "format": "wav", "channels": 1})
        project["export"] = result
        project.setdefault("exports", []).append(result)
        save_project(project)
        return result

    return {
        "build_export_visual_segments": build_export_visual_segments,
        "build_visual_segment": build_visual_segment,
        "export_audio_file": export_audio_file,
        "export_project": export_project,
        "export_project_with_settings": export_project_with_settings,
        "export_subtitle_events": export_subtitle_events,
        "export_video_file": export_video_file,
        "locate_ffmpeg": locate_ffmpeg,
        "mix_music_clip": mix_music_clip,
        "mix_music_lane": mix_music_lane,
        "project_for_export_scope": project_for_export_scope,
        "read_audio_mono": read_audio_mono,
        "render_project_audio": render_project_audio,
        "run_ffmpeg": run_ffmpeg,
        "subtitle_events_for_export_duration": subtitle_events_for_export_duration,
        "write_export_subtitles_ass": write_export_subtitles_ass,
    }
