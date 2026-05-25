import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

try:
    from .studio_defaults import ANCIENT_PREHISTORY_NEGATIVE, DEFAULT_VIDEO_GROUP_NEGATIVE
    from .studio_json_helpers import extract_json_object
    from .studio_prompt_helpers import (
        DEFAULT_ANIMATION_NEGATIVE_PROMPT,
        NO_PEOPLE_IMAGE_NEGATIVE,
        append_unique_csv_terms,
        truncate_text,
    )
    from .studio_storage import chunk_order_ids
except ImportError:  # pragma: no cover - direct script imports
    from studio_defaults import ANCIENT_PREHISTORY_NEGATIVE, DEFAULT_VIDEO_GROUP_NEGATIVE
    from studio_json_helpers import extract_json_object
    from studio_prompt_helpers import (
        DEFAULT_ANIMATION_NEGATIVE_PROMPT,
        NO_PEOPLE_IMAGE_NEGATIVE,
        append_unique_csv_terms,
        truncate_text,
    )
    from studio_storage import chunk_order_ids


def call_xai_video_groups_api(
    chunks: list[dict[str, Any]],
    payload: Any,
    api_key: str,
    *,
    section_context: str = "",
    scope_label: str = "project",
    xai_timeout_seconds: int | float,
    resolve_xai_text_model: Callable[[dict[str, Any] | None, str | None], str],
    compact_ai_chunks: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    normalize_video_groups: Callable[..., list[dict[str, Any]]],
    repair_ai_video_groups: Callable[..., list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Call xAI/Grok to build normalized video groups for a chunk batch."""

    api_key = (api_key or "").strip()
    if not api_key:
        raise RuntimeError("xAI API key is not configured for this project and XAI_API_KEY is not set")
    base_url = (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
    model = resolve_xai_text_model(None, payload.model)
    min_chunks = max(1, int(payload.min_chunks_per_group or 2))
    max_chunks = max(min_chunks, int(payload.max_chunks_per_group or 8))
    compact_chunks = compact_ai_chunks(chunks)
    exclude_people = bool(payload.exclude_people_from_images)
    system_prompt = (
        "You group narration chunks into visually coherent video scenes and write image-generation prompts plus simple loop animation prompts. "
        "For each group, imagine the single frame an SDXL/RealVisXL model should render from the narration. "
        "Maintain project-wide visual consistency unless the narration clearly changes scene: shared style, palette, era, camera language, environment logic, and recurring character/subject identity. "
        "Also describe a calm seamless image-to-video loop using only subtle cyclic natural ambient motion, with the first and last frame matching naturally. "
        "Return strictly valid JSON only, with root object {\"groups\":[...]}."
    )
    group_schema = {
        "id": "string; any temporary id is accepted, server will renumber",
        "title": "short human-readable title",
        "summary": "1-2 sentence factual summary of the narration covered by this group",
        "chunk_ids": "array of provided chunk ids, one contiguous range, preserving order",
        "visual_prompt": (
            "English SDXL/RealVisXL positive prompt, 60-120 words. Describe one concrete unified scene, not an abstract list. "
            "Infer the lecture setting and era from this group's own narration; do not assume the whole project is ancient, modern, space, medical, or any other fixed theme. "
            "Include subject, location, historical era or time period when implied, lighting, composition/camera, characters, "
            "important objects/materials, atmosphere and mood. Use realistic documentary/cinematic language. "
            "For ancient, prehistory, Stone Age, hominid, hunter-gatherer, campfire, or historical scenes, name the people specifically "
            "instead of generic 'figures' (for example two prehistoric humans, early hominids, ancient villagers) and make clothing/materials "
            "explicitly visible: barefoot prehistoric humans, rough animal-hide wraps, fur cloaks, handmade leather, plant-fiber cordage, or linen tunics only if era-appropriate. "
            "For prehistoric scenes, include no modern objects visible and no tailored clothing visible in the positive prompt when people or camps are shown. "
            "Do not include text overlays, subtitles, captions, watermarks, logos, UI, signs, labels, readable writing, markdown, or multiple alternative scenes."
            + (" If exclude_people_from_images is true, this field must contain no people, faces, bodies, hands, crowds, characters, portraits, or clothing; describe only environmental, object, nature, architecture, or artifact-focused scenes." if exclude_people else "")
        ),
        "visual_context": (
            "English shared continuity context for this group, 35-90 words. Specify recurring characters/subjects, exact visual style, camera language, palette, era, clothing/materials, environment, lighting, and mood. "
            "This field will be prepended to per-chunk image prompts to keep a consistent visual sequence. No story action and no text-in-image instructions except the no-text ban."
        ),
        "negative_prompt": (
            "English comma-separated SDXL negative prompt, 18-35 concise terms. Include quality/anatomy/text artifacts and "
            "scene-specific exclusions selected for this group's inferred setting. For ancient/prehistory scenes, include modern clothing, "
            "business suit, office suit, shirt and tie, jacket, blazer, dress pants, modern shoes, sneakers, watch, glasses, phone, city, office, modern buildings, cars. "
            "For non-ancient lectures, choose different relevant exclusions instead of copying ancient-world exclusions. No sentences."
        ),
        "animation_positive_prompt": (
            "English image-to-video positive prompt, 40-85 words. Request a calm, subtle, seamless looping video / perfect loop where the first and last frame match naturally. "
            "Keep the camera locked or nearly locked, with no cuts, no scene change, no sudden camera movement, and no beginning/end reveal. "
            "Use only natural ambient motion appropriate to the still image, such as grass swaying, leaves moving, water ripple, smoke/fire/candle flicker, "
            "dust motes, clouds drifting, or fabric lightly moving in cyclic gentle patterns. Preserve the scene and avoid story action."
        ),
        "animation_negative_prompt": (
            "English comma-separated animation negative prompt, 18-35 concise terms. Exclude character motion, fast action, cuts, zooms, pans, camera shake, "
            "morphing, warping, new objects appearing, objects disappearing, non-looping motion, one-way motion, sudden ending, start/end mismatch, object popping, text, subtitles, watermarks, jitter, and flicker artifacts."
        ),
        "grok_video_prompt": "English Grok Imagine Video prompt, editable later; can reuse animation_positive_prompt but should stand alone and mention loop, locked camera, subtle ambient motion.",
        "mood": "2-6 English words describing the emotional tone",
        "scene_type": "2-6 English words describing the visual scene category",
    }
    user_prompt = {
        "task": "Create semantic video groups for XTTS Studio chunks.",
        "section_context": section_context,
        "output_schema": {"groups": [group_schema]},
        "rules": [
            "Root must be exactly an object with key groups.",
            "Each group fields: id, title, summary, chunk_ids, visual_prompt, visual_context, negative_prompt, animation_positive_prompt, animation_negative_prompt, grok_video_prompt, mood, scene_type.",
            "Use every chunk exactly once.",
            "Do not omit any chunk id, even if a chunk is short or transitional.",
            "Keep original chunk order.",
            "Every group must be one contiguous range of chunks.",
            "Do not invent chunk ids.",
            "Do not reference chunks outside the provided chunks list.",
            "Prefer groups representing about 30-90 seconds of coherent visual meaning.",
            "For a sleepy lecture, do not change scenes too often; keep transitions calm and sparse.",
            f"Aim for {min_chunks}-{max_chunks} chunks per group unless semantic boundaries require otherwise.",
            f"exclude_people_from_images is {'true' if exclude_people else 'false'}.",
            "When exclude_people_from_images is true, it overrides all ancient/prehistory/historical examples and rules that would otherwise include humans or clothing.",
            "When exclude_people_from_images is true, visual_prompt must avoid people, faces, bodies, crowds, hands, characters, portraits, human silhouettes, skin, eyes, hair, and clothing; create calm environmental/object/nature/architecture/artifact-focused scenes instead.",
            "When exclude_people_from_images is true, negative_prompt must include people, person, human, face, body, crowd, hands, characters, clothing, portrait, skin, eyes, hair.",
            "visual_prompt must be written in English and be directly usable as the main SDXL/RealVisXL scene description.",
            "visual_context must be written in English and define the group's shared consistency bible: characters/subjects, camera language, palette, era, clothing/materials, environment, and lighting for all chunk images in this group.",
            "Across the whole response, keep a shared project look and palette unless the narration explicitly changes it; do not redesign recurring characters or subjects between groups.",
            "No generated image should contain visible text: avoid all words, letters, subtitles, captions, UI, signs, labels, watermarks, logos, readable writing, numbers, and glyph-like markings unless the user explicitly requested text inside the image.",
            "visual_prompt must be 60-120 words when possible, detailed enough to render a specific frame.",
            "visual_prompt must describe exactly one coherent image: what is visible, where it is, approximate era, light, composition, people, objects, materials, and mood.",
            "Infer the setting, era, and visual rules separately for each group from the provided chunk text and section context; never force one lecture theme globally across all groups.",
            "For prehistory, Stone Age, early human, hominid, hunter-gatherer, ancient camp, campfire, or historical scenes only, never rely on generic people words like 'figures' or 'persons'; write specific subjects such as two prehistoric humans, early hominids, ancient villagers, or hunter-gatherers.",
            "For ancient/prehistory people only, explicitly state visible clothing and materials: barefoot prehistoric humans, rough animal-hide wraps, fur cloaks, handmade leather, plant-fiber cordage, bone or stone tools, simple linen tunics only when era-appropriate.",
            "For prehistoric or ancient campfire scenes only, include no modern objects visible and no tailored clothing visible in visual_prompt, while still positively describing the correct clothing and materials.",
            "Avoid ambiguous modernizing words for ancient/prehistory scenes only, including outfit, trousers, pants, shirt, jacket, coat, uniform, formal wear, dressed figures, camping trip, tourists, or safari.",
            "Avoid abstract themes, bullet-like keyword dumps, vague phrases such as 'the concept of', and instructions to the viewer or model.",
            "If the narration is abstract, convert it into a plausible calm documentary scene anchored in the text instead of listing concepts.",
            "negative_prompt must be English, comma-separated, SDXL-friendly, and useful for RealVisXL quality control.",
            "negative_prompt should include common defects: text, letters, words, captions, subtitles, UI, signs, labels, readable writing, watermark, logo, low quality, blurry, deformed hands, extra fingers, bad anatomy, oversaturated, cartoon, anime, cgi.",
            "negative_prompt must add exclusions relevant to the specific group setting: e.g. anachronistic objects for historical scenes, neon UI for calm nature scenes, spacesuits for naked-eye astronomy scenes, horror or action for sleep-documentary scenes, or other theme-specific problems inferred from context.",
            "For ancient/prehistory/historical scenes only, negative_prompt must strongly exclude modern clothing, business suit, office suit, shirt and tie, jacket, blazer, dress pants, modern shoes, sneakers, watch, glasses, phone, modern objects, city, office, modern buildings, cars, tourists, safari, modern campfire scene.",
            "For non-ancient lectures, do not copy ancient/prehistory exclusions unless that group's own visual setting actually implies them; choose exclusions that match that non-ancient topic.",
            "Do not put positive visual details inside negative_prompt.",
            "animation_positive_prompt must be written in English and must describe a simple calm seamless looping video, perfect loop, first and last frame match naturally.",
            "animation_positive_prompt must keep the camera locked or nearly locked, with very low camera movement, no cuts, no scene change, no sudden camera movement, no beginning/end reveal, and no object popping.",
            "animation_positive_prompt must use only cyclic natural ambient motion: grass swaying, leaves moving, water ripple, smoke/fire/candle flicker, dust motes, clouds drifting, or fabric lightly moving when appropriate.",
            "For landscape/environment scenes, animation_positive_prompt must say leaves, grass, water, or clouds move in a gentle cyclic pattern when those elements are visible.",
            "animation_positive_prompt must avoid character motion, gestures, walking, talking, fast action, cuts, zooms, pans, morphing, camera shake, new objects appearing, objects disappearing, text, and start/end mismatch.",
            "animation_negative_prompt must be English, comma-separated, and focused on preventing non-loop-friendly motion artifacts and scene changes; include cuts, jump cut, scene transition, camera zoom, camera pan, new objects appearing, objects disappearing, non-looping motion, one-way motion, sudden ending, start/end mismatch.",
            "grok_video_prompt must be populated for every group and usable directly by Grok Imagine Video; if unsure, adapt animation_positive_prompt into one standalone prompt.",
        ],
        "ancient_riverside_visual_prompt_example_for_historical_scenes_only": (
            "A quiet realistic reconstruction of an ancient riverside settlement at dawn, with two linen-clad figures preparing clay vessels beside a low mud-brick wall. "
            "Reeds and calm water frame the background, warm amber sunlight touches stone, wood, and woven baskets, and the camera sits at eye level with a gentle wide composition. "
            "The scene feels peaceful, historically plausible, softly cinematic, and suitable for a slow sleep documentary."
        ),
        "prehistoric_campfire_visual_prompt_example_for_prehistoric_scenes_only": (
            "A realistic archaeology-documentary reconstruction of two prehistoric humans sitting beside a small campfire at dusk outside a shallow cave. "
            "Both are barefoot and visibly wrapped in rough animal-hide garments and fur cloaks tied with simple plant-fiber cordage, with stone tools and unshaped branches near the fire. "
            "Warm ember light illuminates natural skin, ash, rock, dirt, and smoke; no modern objects visible, no tailored clothing visible. Calm eye-level composition, peaceful sleep documentary mood."
        ),
        "generic_quality_negative_prompt_example_for_all_scenes": DEFAULT_VIDEO_GROUP_NEGATIVE,
        "prehistoric_campfire_negative_prompt_example_for_prehistoric_scenes_only": append_unique_csv_terms(
            DEFAULT_VIDEO_GROUP_NEGATIVE,
            ANCIENT_PREHISTORY_NEGATIVE,
            limit=700,
        ),
        "non_ancient_negative_prompt_note": "For non-ancient lectures, choose different exclusions relevant to that setting instead of using prehistoric/ancient clothing or modern-object exclusions by default.",
        "good_animation_positive_prompt_example": (
            "Calm seamless image-to-video loop, perfect loop, first and last frame match naturally, with a locked eye-level camera. Reeds and grass move in a gentle cyclic breeze, calm river water forms slow repeating ripples, "
            "warm dawn light remains steady, and tiny dust motes drift subtly. No cuts, no beginning/end reveal, no object popping, peaceful realistic ambient movement only."
        ),
        "good_animation_negative_prompt_example": DEFAULT_ANIMATION_NEGATIVE_PROMPT,
        "optional_user_instruction": truncate_text(payload.instruction, 1000),
        "exclude_people_from_images": exclude_people,
        "chunks": compact_chunks,
    }
    if exclude_people:
        user_prompt["no_people_visual_prompt_example"] = (
            "A quiet prehistoric riverside at dawn with reeds, smooth stones, handmade clay vessels, scattered bone and stone tools, ash from an old fire, animal-hide bundles with no body present, "
            "soft mist over calm water, warm natural light, realistic archaeology-documentary composition, peaceful sleep documentary mood, no people or human figures visible."
        )
        user_prompt["no_people_negative_prompt_example"] = append_unique_csv_terms(DEFAULT_VIDEO_GROUP_NEGATIVE, NO_PEOPLE_IMAGE_NEGATIVE, limit=700)
    request_body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=xai_timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"xAI request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"xAI request failed: {exc.reason}") from exc
    completion = json.loads(response_body)
    content = completion.get("choices", [{}])[0].get("message", {}).get("content", "")
    ai_json = extract_json_object(content)
    raw_groups = ai_json.get("groups")
    expected_ids = chunk_order_ids(chunks)
    try:
        return normalize_video_groups(
            raw_groups,
            chunks,
            source="grok",
            require_all_chunks=True,
            expected_ordered_ids=expected_ids,
            scope_label=scope_label,
        )
    except ValueError:
        return repair_ai_video_groups(raw_groups, chunks, expected_ids, scope_label, source="grok_repaired", exclude_people=exclude_people)
