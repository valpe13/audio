import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

try:
    from .studio_route_deps import dep
except ImportError:  # pragma: no cover - direct script imports
    from studio_route_deps import dep


CHUNK_PROMPT_LIMITS = {
    "image_prompt": 1400,
    "image_negative_prompt": 1500,
    "animation_positive_prompt": 900,
    "animation_negative_prompt": 700,
    "grok_video_prompt": 1800,
    "prompt_context_note": 700,
    "prompt_source": 80,
}


def make_chunk_prompt_helpers(deps: dict[str, Any]) -> dict[str, Any]:
    """Build helpers for per-chunk visual prompt generation and application."""

    def normalize_chunk_prompt_fields(chunk: dict[str, Any], patch: dict[str, Any], *, source: str = "manual") -> None:
        for key, limit in CHUNK_PROMPT_LIMITS.items():
            if key in patch and patch.get(key) is not None:
                chunk[key] = dep(deps, "truncate_text")(patch.get(key), limit)
        if source:
            chunk["prompt_source"] = dep(deps, "truncate_text")(source, CHUNK_PROMPT_LIMITS["prompt_source"])
        chunk["prompt_updated_at"] = time.time()

    def generate_fallback_chunk_prompts(project: dict[str, Any], group: dict[str, Any]) -> list[dict[str, Any]]:
        chunks_by_id = {str(chunk.get("id") or ""): chunk for chunk in dep(deps, "ordered_project_chunks")(project)}
        group_ids = [str(chunk_id) for chunk_id in group.get("chunk_ids", []) if str(chunk_id) in chunks_by_id]
        context = dep(deps, "truncate_text")(". ".join(part for part in [dep(deps, "project_visual_context")(project), dep(deps, "group_visual_context")(group), group.get("visual_prompt") or group.get("summary") or group.get("title")] if part), 900)
        out: list[dict[str, Any]] = []
        for index, chunk_id in enumerate(group_ids):
            chunk = chunks_by_id[chunk_id]
            text = dep(deps, "truncate_text")(chunk.get("text") or chunk.get("tts_text"), 260)
            prev_text = dep(deps, "truncate_text")(chunks_by_id[group_ids[index - 1]].get("text"), 120) if index > 0 else ""
            next_text = dep(deps, "truncate_text")(chunks_by_id[group_ids[index + 1]].get("text"), 120) if index + 1 < len(group_ids) else ""
            visual = dep(deps, "truncate_text")(
                f"A coherent close-up or continuation shot within the same scene as the group prompt: {context}. Chunk narration focus: {text}. Keep the same project and group style, era, location, lighting, lens, color palette, materials, characters/subjects and atmosphere as adjacent chunks; do not create a hard scene cut. {dep(deps, 'NO_TEXT_IMAGE_INSTRUCTION') if dep(deps, 'no_text_images_enabled')(project) else ''}",
                1400,
            )
            note = dep(deps, "truncate_text")(f"Группа: {group.get('title') or group.get('summary')}. Предыдущий чанк: {prev_text}. Следующий чанк: {next_text}.", 700)
            out.append({
                "id": chunk_id,
                "image_prompt": visual,
                "image_negative_prompt": dep(deps, "append_unique_csv_terms")(group.get("negative_prompt") or dep(deps, "DEFAULT_VIDEO_GROUP_NEGATIVE"), dep(deps, "NO_TEXT_IMAGE_NEGATIVE") if dep(deps, "no_text_images_enabled")(project) else "", limit=1500),
                "animation_positive_prompt": dep(deps, "build_animation_positive_prompt")(text, visual),
                "animation_negative_prompt": group.get("animation_negative_prompt") or dep(deps, "DEFAULT_ANIMATION_NEGATIVE_PROMPT"),
                "grok_video_prompt": dep(deps, "format_grok_imagine_video_prompt")({"visual_prompt": visual, "summary": text, "animation_positive_prompt": group.get("animation_positive_prompt")}),
                "prompt_context_note": note,
            })
        return out

    def group_chunks_for_prompts(project: dict[str, Any], group: dict[str, Any]) -> list[dict[str, Any]]:
        chunks_by_id = {str(chunk.get("id") or ""): chunk for chunk in dep(deps, "ordered_project_chunks")(project)}
        return [chunks_by_id[str(chunk_id)] for chunk_id in group.get("chunk_ids", []) if str(chunk_id) in chunks_by_id]

    def normalize_xai_chunk_prompt_items(raw_items: Any, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("chunks") or raw_items.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("AI response field chunks must be a list")
        valid_ids = {str(chunk.get("id") or "") for chunk in chunks if str(chunk.get("id") or "")}
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            chunk_id = str(raw.get("id") or raw.get("chunk_id") or "")
            if chunk_id not in valid_ids or chunk_id in seen:
                continue
            seen.add(chunk_id)
            item = {"id": chunk_id}
            for key, limit in CHUNK_PROMPT_LIMITS.items():
                if key == "prompt_source":
                    continue
                if raw.get(key) is not None:
                    item[key] = dep(deps, "truncate_text")(raw.get(key), limit)
            out.append(item)
        missing = [str(chunk.get("id") or "") for chunk in chunks if str(chunk.get("id") or "") not in seen]
        if missing:
            raise ValueError(f"AI chunk prompts missing ids: {', '.join(missing[:20])}{'…' if len(missing) > 20 else ''}")
        return out

    def call_xai_chunk_prompts(project: dict[str, Any], group: dict[str, Any], api_key: str) -> list[dict[str, Any]]:
        chunks = group_chunks_for_prompts(project, group)
        if not chunks:
            return []
        base_url = (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
        model = dep(deps, "resolve_xai_text_model")(project, str(project.get("settings", {}).get("ai_chunk_prompt_model") or ""))
        compact_chunks = [{"id": str(chunk.get("id") or ""), "order": idx, "text": dep(deps, "truncate_text")(chunk.get("text") or chunk.get("tts_text"), 900)} for idx, chunk in enumerate(chunks)]
        project_context = dep(deps, "project_visual_context")(project)
        no_text_enabled = dep(deps, "no_text_images_enabled")(project)
        payload = {
            "task": "Create per-chunk visual prompts for XTTS Studio within one existing video group.",
            "project_visual_context": project_context,
            "group_context": {
                "id": str(group.get("id") or ""),
                "title": dep(deps, "truncate_text")(group.get("title"), 160),
                "summary": dep(deps, "truncate_text")(group.get("summary"), 700),
                "shared_visual_prompt": dep(deps, "truncate_text")(group.get("visual_prompt"), 1400),
                "shared_visual_context": dep(deps, "group_visual_context")(group),
                "shared_negative_prompt": dep(deps, "truncate_text")(group.get("negative_prompt"), 900),
                "shared_animation_prompt": dep(deps, "truncate_text")(group.get("animation_positive_prompt"), 900),
                "mood": dep(deps, "truncate_text")(group.get("mood"), 120),
                "scene_type": dep(deps, "truncate_text")(group.get("scene_type"), 120),
            },
            "output_schema": {"chunks": [{"id": "same chunk id", "image_prompt": "English positive image prompt", "image_negative_prompt": "English comma-separated negative prompt", "animation_positive_prompt": "English loop animation prompt", "animation_negative_prompt": "English comma-separated animation negative prompt", "grok_video_prompt": "English Grok Imagine Video loop prompt", "prompt_context_note": "Russian note about continuity with adjacent chunks"}]},
            "rules": [
                "Return strictly valid JSON object only with key chunks.",
                "Return exactly one item for every provided chunk id; keep chunk order and do not invent ids.",
                "Use one consistent shared visual style, era, location, lighting, lens, color palette, materials, atmosphere, and recurring character/subject identity across all chunks in this group.",
                "Apply project_visual_context to every chunk prompt when it is provided; it is the project-wide consistency bible for style, palette, camera language, era, clothing/materials, environment, and recurring identity.",
                "Apply group_context.shared_visual_context to every chunk prompt; it is the group-level consistency bible for this sequence.",
                "Each image_prompt must be a render-ready English prompt for one still image corresponding to that chunk, 45-110 words, concrete and coherent, not a keyword dump.",
                "Prompts must feel sequential on a group timeline: use continuation shots, different details, or gentle camera framing changes without hard scene cuts unless the text demands it.",
                "Use the group shared_negative_prompt as a base for image_negative_prompt and add chunk-specific exclusions when useful.",
                "animation_positive_prompt and grok_video_prompt must request a calm seamless loop with locked camera and subtle ambient motion only.",
                "prompt_context_note must be short Russian text explaining how this chunk connects visually to neighboring chunks.",
                "Avoid visible text, subtitles, UI, logos, watermarks, sudden action, and inconsistent style.",
                f"no_text_images is {'true' if no_text_enabled else 'false'}.",
                "When no_text_images is true, every image_prompt must explicitly ban visible text and every image_negative_prompt must include text, letters, words, captions, subtitles, UI, signs, labels, readable writing, watermark, logo.",
            ],
            "chunks": compact_chunks,
        }
        request_body = {
            "model": model,
            "temperature": 0.25,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You write structured per-chunk image and loop-video prompts. Return JSON only."},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        }
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=dep(deps, "XAI_VIDEO_GROUPS_TIMEOUT_SECONDS")) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"xAI chunk prompt request failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"xAI chunk prompt request failed: {exc.reason}") from exc
        completion = json.loads(response_body)
        content = completion.get("choices", [{}])[0].get("message", {}).get("content", "")
        ai_json = dep(deps, "extract_json_object")(content)
        return normalize_xai_chunk_prompt_items(ai_json.get("chunks"), chunks)

    def generate_chunk_prompt_items(project: dict[str, Any], group: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
        pid = dep(deps, "safe_project_id")(str(project.get("id") or dep(deps, "active_project_id")()))
        api_key = dep(deps, "resolve_xai_api_key")(project, pid)
        if api_key:
            try:
                return call_xai_chunk_prompts(project, group, api_key), "grok", "Grok/xAI"
            except Exception as exc:
                fallback = generate_fallback_chunk_prompts(project, group)
                note = dep(deps, "truncate_text")(f"Grok не сработал, использован локальный fallback: {type(exc).__name__}: {exc}", 700)
                for item in fallback:
                    item["prompt_context_note"] = dep(deps, "truncate_text")(f"{item.get('prompt_context_note') or ''} {note}", 700)
                return fallback, "group-context-fallback", note
        return generate_fallback_chunk_prompts(project, group), "group-context-fallback", "Grok/xAI ключ не настроен; использован локальный fallback"

    def apply_chunk_prompt_items(project: dict[str, Any], items: list[dict[str, Any]], *, source: str = "manual") -> int:
        chunks_by_id = {str(chunk.get("id") or ""): chunk for chunk in project.get("chunks", []) if isinstance(chunk, dict)}
        updated = 0
        for item in items:
            chunk = chunks_by_id.get(str(item.get("id") or ""))
            if not chunk:
                continue
            normalize_chunk_prompt_fields(chunk, item, source=source)
            updated += 1
        return updated

    def chunk_prompt_fields_are_empty(chunk: dict[str, Any]) -> bool:
        return not any(str(chunk.get(key) or "").strip() for key in CHUNK_PROMPT_LIMITS if key != "prompt_source")

    def apply_chunk_prompt_items_missing_only(project: dict[str, Any], items: list[dict[str, Any]], *, source: str = "manual", missing_only: bool = False) -> int:
        chunks_by_id = {str(chunk.get("id") or ""): chunk for chunk in project.get("chunks", []) if isinstance(chunk, dict)}
        updated = 0
        for item in items:
            chunk = chunks_by_id.get(str(item.get("id") or ""))
            if not chunk:
                continue
            if missing_only and not chunk_prompt_fields_are_empty(chunk):
                continue
            normalize_chunk_prompt_fields(chunk, item, source=source)
            updated += 1
        return updated

    return {
        "CHUNK_PROMPT_LIMITS": CHUNK_PROMPT_LIMITS,
        "apply_chunk_prompt_items": apply_chunk_prompt_items,
        "apply_chunk_prompt_items_missing_only": apply_chunk_prompt_items_missing_only,
        "chunk_prompt_fields_are_empty": chunk_prompt_fields_are_empty,
        "generate_chunk_prompt_items": generate_chunk_prompt_items,
        "generate_fallback_chunk_prompts": generate_fallback_chunk_prompts,
        "normalize_chunk_prompt_fields": normalize_chunk_prompt_fields,
    }
