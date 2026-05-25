import json
import time
from typing import Any

from fastapi import HTTPException

try:
    from .studio_defaults import ANCIENT_PREHISTORY_NEGATIVE, DEFAULT_VIDEO_GROUP_NEGATIVE
    from .studio_json_helpers import extract_json_object, is_transient_xai_error, resolve_xai_text_model as resolve_xai_text_model_base
    from .studio_media_meta import (
        build_media_subtitle_normalizer_context,
        build_normalized_video_group_media_field_args,
        build_normalized_video_group_media_subtitle_fields,
        normalize_group_image_meta,
        normalize_group_video_meta,
    )
    from .studio_project_store import safe_project_id
    from .studio_prompt_helpers import (
        DEFAULT_ANIMATION_NEGATIVE_PROMPT,
        NO_PEOPLE_IMAGE_NEGATIVE,
        NO_PEOPLE_VISUAL_INSTRUCTION,
        append_unique_csv_terms,
        build_animation_positive_prompt,
        build_no_usable_video_group_ids_note,
        build_normalized_video_group_prompt_fields,
        build_repaired_video_group_fields,
        build_repaired_video_group_note,
        format_grok_imagine_video_prompt,
        looks_like_ancient_prehistory_scene,
        truncate_text,
    )
    from .studio_storage import (
        chunk_order_ids,
        collect_repaired_video_group_anchors,
        normalize_video_group_playback_speed,
        ordered_project_chunks,
        repaired_video_group_spans,
        video_group_coverage_error,
    )
    from .studio_subtitles import build_normalized_video_group_subtitle_field_args, normalize_subtitle_defaults
    from .studio_video_groups_xai import call_xai_video_groups_api
except ImportError:  # pragma: no cover - direct script imports
    from studio_defaults import ANCIENT_PREHISTORY_NEGATIVE, DEFAULT_VIDEO_GROUP_NEGATIVE
    from studio_json_helpers import extract_json_object, is_transient_xai_error, resolve_xai_text_model as resolve_xai_text_model_base
    from studio_media_meta import (
        build_media_subtitle_normalizer_context,
        build_normalized_video_group_media_field_args,
        build_normalized_video_group_media_subtitle_fields,
        normalize_group_image_meta,
        normalize_group_video_meta,
    )
    from studio_project_store import safe_project_id
    from studio_prompt_helpers import (
        DEFAULT_ANIMATION_NEGATIVE_PROMPT,
        NO_PEOPLE_IMAGE_NEGATIVE,
        NO_PEOPLE_VISUAL_INSTRUCTION,
        append_unique_csv_terms,
        build_animation_positive_prompt,
        build_no_usable_video_group_ids_note,
        build_normalized_video_group_prompt_fields,
        build_repaired_video_group_fields,
        build_repaired_video_group_note,
        format_grok_imagine_video_prompt,
        looks_like_ancient_prehistory_scene,
        truncate_text,
    )
    from studio_storage import (
        chunk_order_ids,
        collect_repaired_video_group_anchors,
        normalize_video_group_playback_speed,
        ordered_project_chunks,
        repaired_video_group_spans,
        video_group_coverage_error,
    )
    from studio_subtitles import build_normalized_video_group_subtitle_field_args, normalize_subtitle_defaults
    from studio_video_groups_xai import call_xai_video_groups_api


def make_video_group_ai_helpers(deps: dict[str, Any]) -> dict[str, Any]:
    """Build video-group fallback/AI helpers from entrypoint-provided dependencies."""

    DEFAULT_SETTINGS = deps["DEFAULT_SETTINGS"]
    XAI_VIDEO_GROUPS_ATTEMPTS = deps["XAI_VIDEO_GROUPS_ATTEMPTS"]
    XAI_VIDEO_GROUPS_RETRY_BASE_DELAY_SECONDS = deps["XAI_VIDEO_GROUPS_RETRY_BASE_DELAY_SECONDS"]
    XAI_VIDEO_GROUPS_TIMEOUT_SECONDS = deps["XAI_VIDEO_GROUPS_TIMEOUT_SECONDS"]
    active_project_id = deps["active_project_id"]
    resolve_xai_api_key = deps["resolve_xai_api_key"]

    def resolve_xai_text_model(project: dict[str, Any] | None = None, override: str | None = None) -> str:
        return resolve_xai_text_model_base(override)

    def fallback_video_groups(chunks: list[dict[str, Any]], max_chunks_per_group: int = 4, *, exclude_people: bool = False) -> list[dict[str, Any]]:
        ordered_ids = chunk_order_ids(chunks)
        group_size = max(1, int(max_chunks_per_group or 4))
        groups: list[dict[str, Any]] = []
        for start in range(0, len(ordered_ids), group_size):
            ids = ordered_ids[start:start + group_size]
            number = len(groups) + 1
            texts = [truncate_text(chunk.get("text", ""), 140) for chunk in chunks[start:start + group_size]]
            summary = truncate_text(" ".join(texts), 260)
            ancient_prehistory = looks_like_ancient_prehistory_scene(summary)
            scene_lead = "A calm realistic documentary scene inspired by the narration: "
            material_rule = ""
            if ancient_prehistory and not exclude_people:
                scene_lead = "A calm realistic archaeology documentary scene inspired by the narration: "
                material_rule = (
                    "Show era-specific humans, not generic figures: prehistoric humans, early hominids, or ancient villagers as appropriate. "
                    "Make clothing visibly handmade from natural materials: rough animal-hide wraps, fur cloaks, barefoot bodies, or simple linen tunics only when era-appropriate. "
                    "No modern objects visible; no tailored clothing visible. "
                )
            if exclude_people:
                visual_prompt = truncate_text(
                    scene_lead +
                    f"{summary}. {NO_PEOPLE_VISUAL_INSTRUCTION}Show one coherent place with relevant objects, artifacts, natural materials, "
                    "soft natural light, balanced cinematic composition, muted colors, atmospheric depth, "
                    "and a peaceful sleep-lecture mood. Avoid symbolic collages; make it a single specific image.",
                    900,
                )
            else:
                visual_prompt = truncate_text(
                    scene_lead +
                    f"{summary}. {material_rule}Show one coherent place with believable characters, relevant objects, "
                    "soft natural light, balanced cinematic composition, muted colors, atmospheric depth, "
                    "and a peaceful sleep-lecture mood. Avoid symbolic collages; make it a single specific image.",
                    900,
                )
            animation_positive_prompt = build_animation_positive_prompt(summary, visual_prompt)
            negative_prompt = DEFAULT_VIDEO_GROUP_NEGATIVE
            if ancient_prehistory and not exclude_people:
                negative_prompt = append_unique_csv_terms(DEFAULT_VIDEO_GROUP_NEGATIVE, ANCIENT_PREHISTORY_NEGATIVE, limit=700)
            if exclude_people:
                negative_prompt = append_unique_csv_terms(DEFAULT_VIDEO_GROUP_NEGATIVE, NO_PEOPLE_IMAGE_NEGATIVE, limit=700)
            groups.append({
                "id": f"video_group_{number:03d}",
                "title": f"Video group {number}",
                "summary": summary,
                "chunk_ids": ids,
                "visual_prompt": visual_prompt,
                "visual_context": truncate_text(
                    "Shared group continuity: keep the same documentary style, muted palette, camera language, era, environment, materials, and any character/subject identity across this group.",
                    700,
                ),
                "negative_prompt": negative_prompt,
                "animation_positive_prompt": animation_positive_prompt,
                "animation_negative_prompt": DEFAULT_ANIMATION_NEGATIVE_PROMPT,
                "grok_video_prompt": format_grok_imagine_video_prompt({"animation_positive_prompt": animation_positive_prompt, "visual_prompt": visual_prompt, "summary": summary}),
                "mood": "calm",
                "scene_type": "sleep lecture",
                "order": number - 1,
                "source": "fallback",
            })
        return groups

    def compact_ai_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"id": str(chunk.get("id") or ""), "order": idx, "text": truncate_text(chunk.get("text", ""), 1200)}
            for idx, chunk in enumerate(chunks)
            if str(chunk.get("id") or "")
        ]

    def compact_ai_payload_chars(chunks: list[dict[str, Any]], payload: Any) -> int:
        sample = {
            "optional_user_instruction": truncate_text(payload.instruction, 1000),
            "chunks": compact_ai_chunks(chunks),
        }
        return len(json.dumps(sample, ensure_ascii=False))

    def split_chunks_for_ai_batches(chunks: list[dict[str, Any]], payload: Any) -> list[list[dict[str, Any]]]:
        max_chunks = max(1, int(payload.max_section_chunks or 40))
        max_chars = max(5000, int(payload.max_request_chars or 22000))
        sections: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_chars = 0
        for chunk in chunks:
            chunk_chars = max(1, len(json.dumps(compact_ai_chunks([chunk]), ensure_ascii=False)))
            would_overflow = bool(current) and (len(current) >= max_chunks or current_chars + chunk_chars > max_chars)
            if would_overflow:
                sections.append(current)
                current = []
                current_chars = 0
            current.append(chunk)
            current_chars += chunk_chars
        if current:
            sections.append(current)
        return sections

    def normalize_video_groups(raw_groups: Any, chunks: list[dict[str, Any]], *, source: str | None = None, require_all_chunks: bool = False, expected_ordered_ids: list[str] | None = None, scope_label: str = "project") -> list[dict[str, Any]]:
        if not isinstance(raw_groups, list):
            if require_all_chunks:
                raise ValueError("AI response field 'groups' must be a list")
            return []
        ordered_ids = expected_ordered_ids or chunk_order_ids(chunks)
        valid_ids = set(ordered_ids)
        cursor = 0
        flattened: list[str] = []
        normalized: list[dict[str, Any]] = []
        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                if require_all_chunks:
                    raise ValueError("Each group must be an object")
                continue
            raw_chunk_ids = raw_group.get("chunk_ids")
            if not isinstance(raw_chunk_ids, list):
                if require_all_chunks:
                    raise ValueError("Each group must include chunk_ids list")
                continue
            ids = [str(chunk_id) for chunk_id in raw_chunk_ids if str(chunk_id) in valid_ids]
            if not ids:
                if require_all_chunks:
                    raise ValueError("Group contains no valid chunk_ids")
                continue
            if require_all_chunks:
                expected_slice = ordered_ids[cursor:cursor + len(ids)]
                if ids != expected_slice:
                    raise ValueError("Groups must preserve chunk order and use contiguous chunk ranges")
            number = len(normalized) + 1
            prompt_fields = build_normalized_video_group_prompt_fields(raw_group, ids, number, source=source)
            image = normalize_group_image_meta(raw_group.get("image")) if isinstance(raw_group.get("image"), dict) else None
            video = normalize_group_video_meta(raw_group.get("video")) if isinstance(raw_group.get("video"), dict) else None
            subtitle_defaults = normalize_subtitle_defaults(raw_group.get("subtitle_defaults"))
            media_group, subtitle_group = build_media_subtitle_normalizer_context(
                prompt_fields,
                image=image,
                video=video,
                subtitle_defaults=subtitle_defaults,
            )
            item = build_normalized_video_group_media_subtitle_fields(
                prompt_fields,
                playback_speed=normalize_video_group_playback_speed(raw_group.get("playback_speed", 1.0)),
                **build_normalized_video_group_media_field_args(raw_group, media_group),
                **build_normalized_video_group_subtitle_field_args(raw_group, subtitle_group),
                repair_note=truncate_text(raw_group.get("repair_note"), 500) if raw_group.get("repair_note") else "",
            )
            normalized.append(item)
            flattened.extend(ids)
            cursor += len(ids)
        if require_all_chunks and flattened != ordered_ids:
            raise ValueError(video_group_coverage_error(flattened, ordered_ids, scope_label))
        return normalized

    def repair_ai_video_groups(raw_groups: Any, chunks: list[dict[str, Any]], expected_ordered_ids: list[str], scope_label: str = "project", *, source: str = "grok_repaired", exclude_people: bool = False) -> list[dict[str, Any]]:
        ordered_ids = [str(chunk_id) for chunk_id in expected_ordered_ids if str(chunk_id)]
        if not ordered_ids:
            return []
        fallback_groups = fallback_video_groups(chunks, 4, exclude_people=exclude_people)
        if not isinstance(raw_groups, list):
            return normalize_video_groups(
                fallback_groups,
                chunks,
                source="fallback",
                require_all_chunks=True,
                expected_ordered_ids=ordered_ids,
                scope_label=f"{scope_label} repair fallback",
            )

        anchors, seen_ids, duplicate_ids, extra_ids = collect_repaired_video_group_anchors(raw_groups, ordered_ids)
        if not anchors:
            repaired_fallback = normalize_video_groups(
                fallback_groups,
                chunks,
                source="fallback",
                require_all_chunks=True,
                expected_ordered_ids=ordered_ids,
                scope_label=f"{scope_label} repair fallback",
            )
            for group in repaired_fallback:
                group["repair_note"] = build_no_usable_video_group_ids_note(scope_label)
            return repaired_fallback

        spans = repaired_video_group_spans(anchors, len(ordered_ids))
        repaired: list[dict[str, Any]] = []
        missing_ids = [chunk_id for chunk_id in ordered_ids if chunk_id not in seen_ids]
        repair_note = build_repaired_video_group_note(scope_label, extra_ids, duplicate_ids, missing_ids)

        for start, end, raw_group, _group_ids in spans:
            ids = ordered_ids[start:end + 1]
            if not ids:
                continue
            number = len(repaired) + 1
            repaired.append(build_repaired_video_group_fields(raw_group, ids, number, source=source, repair_note=repair_note))

        return normalize_video_groups(
            repaired,
            chunks,
            source=source,
            require_all_chunks=True,
            expected_ordered_ids=ordered_ids,
            scope_label=f"{scope_label} repaired",
        )

    def call_xai_video_groups_with_retry(
        chunks: list[dict[str, Any]],
        payload: Any,
        api_key: str,
        *,
        section_context: str = "",
        scope_label: str = "project",
        progress_callback: Any | None = None,
        progress_base: float | None = None,
        progress_span: float = 0.0,
    ) -> list[dict[str, Any]]:
        attempts = max(1, XAI_VIDEO_GROUPS_ATTEMPTS)
        last_exc: BaseException | None = None
        for attempt in range(1, attempts + 1):
            if progress_callback:
                progress = progress_base if progress_base is not None else 35
                if progress_base is not None and progress_span > 0:
                    progress = progress_base + ((attempt - 1) / max(1, attempts)) * min(progress_span, 6)
                progress_callback(f"Grok grouping {scope_label} (attempt {attempt}/{attempts})", progress)
            try:
                return call_xai_video_groups(chunks, payload, api_key, section_context=section_context, scope_label=scope_label)
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts or not is_transient_xai_error(exc):
                    break
                delay = XAI_VIDEO_GROUPS_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                if progress_callback:
                    progress = progress_base if progress_base is not None else 35
                    progress_callback(f"Grok retrying {scope_label} after transient error (attempt {attempt}/{attempts} failed): {exc}", progress)
                time.sleep(delay)
        raise RuntimeError(f"{scope_label} failed after {attempts} attempt{'s' if attempts != 1 else ''}: {last_exc}") from last_exc

    def call_xai_video_groups(chunks: list[dict[str, Any]], payload: Any, api_key: str, *, section_context: str = "", scope_label: str = "project") -> list[dict[str, Any]]:
        return call_xai_video_groups_api(
            chunks,
            payload,
            api_key,
            section_context=section_context,
            scope_label=scope_label,
            xai_timeout_seconds=XAI_VIDEO_GROUPS_TIMEOUT_SECONDS,
            resolve_xai_text_model=resolve_xai_text_model,
            compact_ai_chunks=compact_ai_chunks,
            normalize_video_groups=normalize_video_groups,
            repair_ai_video_groups=repair_ai_video_groups,
        )

    def renumber_video_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        renumbered: list[dict[str, Any]] = []
        for idx, group in enumerate(groups, start=1):
            item = dict(group)
            item["id"] = f"video_group_{idx:03d}"
            item["order"] = idx - 1
            renumbered.append(item)
        return renumbered

    def generate_video_groups_ai(project: dict[str, Any], payload: Any, progress_callback: Any | None = None) -> list[dict[str, Any]]:
        chunks = ordered_project_chunks(project)
        if not chunks:
            raise HTTPException(status_code=400, detail="Project has no chunks to group")
        if payload.exclude_people_from_images is None:
            payload.exclude_people_from_images = bool(project.get("settings", {}).get("image_exclude_people", DEFAULT_SETTINGS["image_exclude_people"]))
        project_id = safe_project_id(str(project.get("id") or active_project_id()))
        api_key = resolve_xai_api_key(project, project_id)
        if not api_key:
            if payload.fallback_on_error:
                max_chunks = int(payload.max_chunks_per_group or 4)
                return fallback_video_groups(chunks, max_chunks if max_chunks > 0 else 4, exclude_people=bool(payload.exclude_people_from_images))
            raise HTTPException(status_code=400, detail="Grok/xAI API key is not configured")
        strategy = (payload.strategy or "auto").strip().lower()
        if strategy not in {"single", "batched", "auto"}:
            raise HTTPException(status_code=400, detail="strategy must be single, batched, or auto")
        should_batch = strategy == "batched" or (strategy == "auto" and compact_ai_payload_chars(chunks, payload) > int(payload.max_request_chars or 22000))
        try:
            if not should_batch:
                if progress_callback:
                    progress_callback("Calling Grok for project", 35)
                return call_xai_video_groups_with_retry(chunks, payload, api_key, scope_label="project", progress_callback=progress_callback, progress_base=35)
            sections = split_chunks_for_ai_batches(chunks, payload)
            all_groups: list[dict[str, Any]] = []
            for idx, section_chunks in enumerate(sections, start=1):
                section_label = f"section {idx}/{len(sections)}"
                attempts = max(1, XAI_VIDEO_GROUPS_ATTEMPTS)
                if progress_callback:
                    base = 20 + ((idx - 1) / max(1, len(sections))) * 70
                    progress_callback(f"Grok grouping {section_label} (attempt 1/{attempts})", base)
                context = (
                    f"This is section {idx} of {len(sections)} of a long lecture; "
                    "keep visual groups coherent, do not reference chunks outside this section."
                )
                try:
                    section_base = 20 + ((idx - 1) / max(1, len(sections))) * 70
                    section_span = 70 / max(1, len(sections))
                    section_groups = call_xai_video_groups_with_retry(
                        section_chunks,
                        payload,
                        api_key,
                        section_context=context,
                        scope_label=section_label,
                        progress_callback=progress_callback,
                        progress_base=section_base,
                        progress_span=section_span,
                    )
                except Exception as exc:
                    if payload.fallback_on_error:
                        if progress_callback:
                            progress_callback(f"Grok {section_label} failed after {attempts} attempts; using fallback groups", 20 + ((idx - 1) / max(1, len(sections))) * 70)
                        section_groups = fallback_video_groups(section_chunks, int(payload.max_chunks_per_group or 4), exclude_people=bool(payload.exclude_people_from_images))
                        section_groups = normalize_video_groups(
                            section_groups,
                            section_chunks,
                            source="fallback",
                            require_all_chunks=True,
                            expected_ordered_ids=chunk_order_ids(section_chunks),
                            scope_label=f"{section_label} fallback",
                        )
                    else:
                        raise RuntimeError(f"Section {idx}/{len(sections)} failed after {attempts} attempts: {exc}") from exc
                all_groups.extend(section_groups)
                if progress_callback:
                    done = 20 + (idx / max(1, len(sections))) * 70
                    progress_callback(f"Grok grouped {section_label}", done)
            return normalize_video_groups(
                renumber_video_groups(all_groups),
                chunks,
                source="grok-batched",
                require_all_chunks=True,
                expected_ordered_ids=chunk_order_ids(chunks),
                scope_label="project after merging sections",
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to generate video groups via xAI: {exc}") from exc

    return {
        "fallback_video_groups": fallback_video_groups,
        "normalize_video_groups": normalize_video_groups,
        "renumber_video_groups": renumber_video_groups,
        "generate_video_groups_ai": generate_video_groups_ai,
    }


def make_video_group_prompt_helpers(deps: dict[str, Any]) -> dict[str, Any]:
    """Build video-group prompt mutation helpers from entrypoint-provided dependencies."""

    def update_group_prompts(project: dict[str, Any], group_id: str, payload: Any) -> dict[str, Any]:
        group = deps["find_video_group"](project, group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Video group not found")
        data = payload.dict(exclude_unset=True)
        limits = {
            "title": 120,
            "summary": 600,
            "visual_prompt": 1400,
            "visual_context": 1400,
            "negative_prompt": 1500,
            "animation_positive_prompt": 900,
            "animation_negative_prompt": 700,
            "grok_video_prompt": 1800,
            "mood": 80,
            "scene_type": 80,
            "video_motion_intensity": 80,
            "video_loop_notes": 700,
        }
        valid_chunk_ids = set(chunk_order_ids(deps["ordered_project_chunks"](project)))
        for key, value in data.items():
            if value is None:
                continue
            if key == "chunk_ids":
                group["chunk_ids"] = [str(chunk_id) for chunk_id in value if str(chunk_id) in valid_chunk_ids]
                continue
            if key == "media_items":
                group["media_items"] = deps["normalize_group_media_items"]([item.dict() if hasattr(item, "dict") else item for item in value], group)
                continue
            if key == "media_layout":
                group["media_layout"] = deps["normalize_group_media_layout"](value)
                continue
            if key == "default_media_duration_sec":
                group["default_media_duration_sec"] = deps["normalize_group_media_duration"](value, 0.0)
                continue
            if key == "subtitle_defaults":
                group["subtitle_defaults"] = normalize_subtitle_defaults(value)
                continue
            if key == "subtitle_blocks":
                group["subtitle_blocks"] = deps["normalize_subtitle_blocks"](value, group)
                continue
            group[key] = truncate_text(value, limits.get(key, 500))
        deps["normalize_arrangement"](project)
        return deps["find_video_group"](project, group_id) or group

    def create_video_group_dict(title: str, summary: str, chunk_ids: list[str], *, order: int = 0, source: str = "manual") -> dict[str, Any]:
        visual_prompt = truncate_text(summary or title or "Manual visual scene", 900)
        animation_positive = build_animation_positive_prompt(summary, visual_prompt)
        group = {
            "id": f"video_group_{order + 1:03d}",
            "title": truncate_text(title or f"Video group {order + 1}", 120),
            "summary": truncate_text(summary, 600),
            "chunk_ids": [str(chunk_id) for chunk_id in chunk_ids if str(chunk_id)],
            "visual_prompt": visual_prompt,
            "visual_context": truncate_text(
                f"Shared continuity for {title or 'Group'}: keep a consistent documentary style, palette, camera language, era, subject identity, clothing/materials, environment, and lighting across all related images.",
                1400,
            ),
            "negative_prompt": DEFAULT_VIDEO_GROUP_NEGATIVE,
            "animation_positive_prompt": animation_positive,
            "animation_negative_prompt": DEFAULT_ANIMATION_NEGATIVE_PROMPT,
            "grok_video_prompt": format_grok_imagine_video_prompt({"animation_positive_prompt": animation_positive, "visual_prompt": visual_prompt, "summary": summary, "title": title}),
            "mood": "calm",
            "scene_type": "sleep lecture",
            "order": order,
            "source": source,
            "media_items": [],
            "media_layout": "sequence",
            "default_media_duration_sec": 0.0,
        }
        return group

    def generate_prompt_for_group(project: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
        chunks_by_id = {str(chunk.get("id") or ""): chunk for chunk in deps["ordered_project_chunks"](project)}
        texts = [str(chunks_by_id.get(str(chunk_id), {}).get("text") or "") for chunk_id in group.get("chunk_ids", [])]
        summary = truncate_text(group.get("summary") or " ".join(texts), 600)
        exclude_people = bool(project.get("settings", {}).get("image_exclude_people", deps["DEFAULT_SETTINGS"]["image_exclude_people"]))
        fallback = deps["fallback_video_groups"]([chunks_by_id[str(chunk_id)] for chunk_id in group.get("chunk_ids", []) if str(chunk_id) in chunks_by_id], max_chunks_per_group=max(1, len(group.get("chunk_ids", []) or [1])), exclude_people=exclude_people)
        prompt_source = fallback[0] if fallback else create_video_group_dict(group.get("title") or "Group", summary, group.get("chunk_ids", []), order=int(group.get("order") or 0), source="prompt-fallback")
        for key in ("summary", "visual_prompt", "visual_context", "negative_prompt", "animation_positive_prompt", "animation_negative_prompt", "grok_video_prompt", "mood", "scene_type"):
            if prompt_source.get(key):
                group[key] = prompt_source[key]
        group["source"] = "generated-selected-group-prompt"
        return group

    return {
        "create_video_group_dict": create_video_group_dict,
        "generate_prompt_for_group": generate_prompt_for_group,
        "update_group_prompts": update_group_prompts,
    }
