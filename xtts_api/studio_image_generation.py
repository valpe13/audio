import html
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any


def make_image_generation_helpers(ctx: dict[str, Any]) -> dict[str, Any]:
    default_settings = ctx["DEFAULT_SETTINGS"]
    grok_image_model = ctx["GROK_IMAGE_MODEL"]
    grok_image_resolutions = ctx["GROK_IMAGE_RESOLUTIONS"]
    grok_reference_limitation_note = ctx["GROK_REFERENCE_LIMITATION_NOTE"]

    def format_image_prompt(group: dict[str, Any], settings: dict[str, Any]) -> dict[str, str]:
        visual = ctx["truncate_text"](group.get("visual_prompt") or group.get("summary") or group.get("title"), 1400)
        context = ctx["truncate_text"](". ".join(part for part in [settings.get("project_visual_context"), group.get("visual_context")] if part), 1400)
        if context:
            visual = ctx["truncate_text"](f"{context}. Scene prompt: {visual}", 2200)
        negative_group = ctx["truncate_text"](group.get("negative_prompt"), 700)
        mood = ctx["truncate_text"](group.get("mood") or "calm", 120)
        scene_type = ctx["truncate_text"](group.get("scene_type") or "sleep lecture", 120)
        ancient_prehistory = ctx["looks_like_ancient_prehistory_scene"](visual, scene_type)
        group_already_uses_ancient_negative = bool(negative_group) and ctx["looks_like_ancient_prehistory_scene"](negative_group)
        orientation = ctx["image_orientation_phrase"](settings)
        model = str(settings.get("model") or "sdxl")
        exclude_people = bool(settings.get("exclude_people"))
        style = ctx["IMAGE_STYLE_PRESETS"].get(
            str(settings.get("style_preset") or default_settings["image_style_preset"]).strip(),
            ctx["IMAGE_STYLE_PRESETS"]["sleep_documentary"],
        )
        style_negative = str(style.get("negative") or "")
        negatives = ", ".join(part for part in [negative_group, style_negative, ctx["COMMON_REALVISXL_NEGATIVE"]] if part)
        if exclude_people:
            visual = ctx["truncate_text"](f"{ctx['NO_PEOPLE_VISUAL_INSTRUCTION']}{visual}", 1400)
            negatives = ctx["append_unique_csv_terms"](negatives, ctx["NO_PEOPLE_IMAGE_NEGATIVE"], limit=1500)
        if ancient_prehistory and group_already_uses_ancient_negative:
            negatives = ctx["append_unique_csv_terms"](negatives, ctx["ANCIENT_PREHISTORY_NEGATIVE"])
        if model in {"realvisxl", "sdxl", "juggernautxl", "dreamshaperxl"}:
            era_positive = ""
            if ancient_prehistory and not exclude_people:
                era_positive = (
                    "ancient/prehistory authenticity, era-appropriate humans, visible natural-material clothing, "
                    "barefoot prehistoric humans or ancient villagers as appropriate, rough animal-hide wraps or fur cloaks for Stone Age scenes, "
                    "linen tunics only when historically appropriate, no modern objects visible, no tailored clothing visible"
                )
            positive = ", ".join(part for part in [
                visual,
                era_positive,
                style.get("positive_prefix"),
                "single clear subject-focused frame",
                "realistic documentary photography",
                "soft natural light",
                mood,
                scene_type,
                orientation,
                style.get("positive_suffix"),
                "high detail, gentle colors",
            ] if part)
            negative = negatives
        elif model == "flux":
            positive = (
                f"Create a calm cinematic image for a sleep lecture. Show: {visual}. "
                f"Mood: {mood}. Scene type: {scene_type}. Use {orientation}, soft natural light, "
                "documentary-inspired atmosphere, no visible text."
            )
            negative = negative_group or "text, watermark, logo"
        else:
            positive = f"{visual}. {orientation}".strip()
            negative = negative_group
        return ctx["apply_no_text_to_prompts"](positive.strip(), negative.strip(), enabled=bool(settings.get("no_text", True)))

    def generate_group_placeholder_svg(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], prompt_bundle: dict[str, str], error: str = "") -> dict[str, Any]:
        pid = ctx["safe_project_id"](str(project.get("id") or ctx["active_project_id"]()))
        out_dir = ctx["project_images_dir"](pid)
        out_dir.mkdir(parents=True, exist_ok=True)
        group_id = str(group.get("id") or uuid.uuid4().hex[:10])
        out = out_dir / f"{group_id}_{int(time.time())}.svg"
        width = int(settings.get("width") or 1024)
        height = int(settings.get("height") or 1792)
        title = html.escape(str(group.get("title") or group_id))
        summary = html.escape(ctx["truncate_text"](group.get("summary") or group.get("visual_prompt") or "", 260))
        positive = html.escape(ctx["truncate_text"](prompt_bundle.get("positive_prompt"), 520))
        error_text = html.escape(ctx["truncate_text"](error, 300))
        accent = "#7aa2ff" if settings.get("aspect_ratio") == "vertical" else "#8ee6c9"
        fallback_line = ""
        if error_text:
            fallback_line = (
                f'<text x="{int(width * 0.09)}" y="{int(height * 0.90)}" fill="#ffb4a8" '
                f'font-family="Segoe UI, Arial, sans-serif" font-size="{max(18, int(width * 0.022))}">'
                f'Fallback reason: {error_text}</text>'
            )
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#141827"/>
      <stop offset="55%" stop-color="#26304d"/>
      <stop offset="100%" stop-color="#0f1320"/>
    </linearGradient>
    <radialGradient id="moon" cx="50%" cy="35%" r="55%">
      <stop offset="0%" stop-color="#fff6d6" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#fff6d6" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <circle cx="{int(width * 0.72)}" cy="{int(height * 0.18)}" r="{max(80, int(min(width, height) * 0.12))}" fill="url(#moon)"/>
  <path d="M0 {int(height * 0.72)} C {int(width * 0.18)} {int(height * 0.62)}, {int(width * 0.34)} {int(height * 0.82)}, {int(width * 0.52)} {int(height * 0.70)} S {int(width * 0.82)} {int(height * 0.64)}, {width} {int(height * 0.74)} L {width} {height} L 0 {height} Z" fill="#0b1020" opacity="0.72"/>
  <rect x="{int(width * 0.07)}" y="{int(height * 0.08)}" width="{int(width * 0.86)}" height="{int(height * 0.84)}" rx="28" fill="none" stroke="{accent}" stroke-width="4" opacity="0.55"/>
  <text x="{int(width * 0.09)}" y="{int(height * 0.13)}" fill="{accent}" font-family="Segoe UI, Arial, sans-serif" font-size="{max(28, int(width * 0.035))}" font-weight="700">XTTS Studio placeholder</text>
  <text x="{int(width * 0.09)}" y="{int(height * 0.19)}" fill="#f4f1e8" font-family="Segoe UI, Arial, sans-serif" font-size="{max(34, int(width * 0.047))}" font-weight="700">{title}</text>
  <foreignObject x="{int(width * 0.09)}" y="{int(height * 0.24)}" width="{int(width * 0.82)}" height="{int(height * 0.20)}">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: Segoe UI, Arial, sans-serif; color: #dbe4ff; font-size: {max(24, int(width * 0.030))}px; line-height: 1.35;">{summary}</div>
  </foreignObject>
  <foreignObject x="{int(width * 0.09)}" y="{int(height * 0.50)}" width="{int(width * 0.82)}" height="{int(height * 0.23)}">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: Consolas, monospace; color: #aebcf2; font-size: {max(18, int(width * 0.022))}px; line-height: 1.35;">Prompt: {positive}</div>
  </foreignObject>
  <text x="{int(width * 0.09)}" y="{int(height * 0.86)}" fill="#bcc7e8" font-family="Segoe UI, Arial, sans-serif" font-size="{max(20, int(width * 0.025))}">provider={html.escape(str(settings.get('provider')))} · model={html.escape(str(settings.get('model')))} · seed={int(settings.get('seed') or 0)}</text>
  {fallback_line}
</svg>
'''
        out.write_text(svg, encoding="utf-8")
        path = ctx["rel_path"](out)
        return {
            "status": "ready",
            "provider": "placeholder",
            "model": settings.get("model"),
            "aspect_ratio": settings.get("aspect_ratio"),
            "width": width,
            "height": height,
            "seed": int(settings.get("seed") or 0),
            "path": path,
            "url": f"/api/image?path={path}&v={int(out.stat().st_mtime)}",
            "positive_prompt": prompt_bundle.get("positive_prompt", ""),
            "negative_prompt": prompt_bundle.get("negative_prompt", ""),
            "error": error,
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    def compile_sdxl_txt2img_workflow(settings: dict[str, Any], prompt_bundle: dict[str, str], output_prefix: str) -> dict[str, Any]:
        checkpoint = str(settings.get("model_checkpoint") or "").strip()
        if not checkpoint:
            raise RuntimeError("SDXL checkpoint is not configured; set image_model_checkpoint to a .safetensors filename")
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": checkpoint},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt_bundle.get("positive_prompt", ""), "clip": ["1", 1]},
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": prompt_bundle.get("negative_prompt", ""), "clip": ["1", 1]},
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": int(settings.get("width") or 1024),
                    "height": int(settings.get("height") or 1024),
                    "batch_size": 1,
                },
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": int(settings.get("seed") or 1),
                    "steps": int(settings.get("steps") or default_settings["image_steps"]),
                    "cfg": float(settings.get("cfg") or default_settings["image_cfg"]),
                    "sampler_name": str(settings.get("sampler") or default_settings["image_sampler"]),
                    "scheduler": str(settings.get("scheduler") or default_settings["image_scheduler"]),
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                },
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": output_prefix, "images": ["6", 0]},
            },
        }

    def generate_group_image(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], prompt_bundle: dict[str, str]) -> dict[str, Any]:
        prompt_bundle = ctx["apply_no_text_to_prompts"](prompt_bundle.get("positive_prompt", ""), prompt_bundle.get("negative_prompt", ""), enabled=bool(settings.get("no_text", True)))
        if settings.get("provider") == "grok":
            try:
                return run_xai_grok_image_workflow(project, group, settings, prompt_bundle)
            except Exception as exc:
                raise RuntimeError(f"Grok/xAI image generation failed: {exc}") from exc
        if settings.get("provider") != "comfyui":
            return generate_group_placeholder_svg(project, group, settings, prompt_bundle)
        if settings.get("model") == "flux":
            return generate_group_placeholder_svg(project, group, settings, prompt_bundle, "FLUX generated workflow is not implemented yet; use SDXL/Juggernaut/DreamShaper")
        workflow_mode = str(settings.get("workflow_mode") or "generated")
        output_prefix = re.sub(r"[^A-Za-z0-9_-]+", "_", f"xtts_{ctx['safe_project_id'](str(project.get('id') or ctx['active_project_id']()))}_{group.get('id', 'group')}").strip("_")
        if workflow_mode == "disabled":
            return generate_group_placeholder_svg(project, group, settings, prompt_bundle, "ComfyUI workflow mode is disabled")
        if workflow_mode == "generated":
            try:
                workflow = compile_sdxl_txt2img_workflow(settings, prompt_bundle, output_prefix)
                return ctx["run_comfyui_workflow"](project, group, settings, prompt_bundle, workflow, output_prefix)
            except Exception as exc:
                return generate_group_placeholder_svg(project, group, settings, prompt_bundle, f"ComfyUI generated workflow failed: {exc}")
        if workflow_mode != "template":
            return generate_group_placeholder_svg(project, group, settings, prompt_bundle, f"Unsupported ComfyUI workflow mode: {workflow_mode}")
        workflow_path = ctx["resolve_user_path"](settings.get("workflow_path")) if settings.get("workflow_path") else None
        if not workflow_path or not workflow_path.exists():
            return generate_group_placeholder_svg(project, group, settings, prompt_bundle, "ComfyUI workflow template is not configured")
        try:
            template = workflow_path.read_text(encoding="utf-8")
            rendered = template
            for key, value in {
                "positive_prompt": prompt_bundle.get("positive_prompt", ""),
                "negative_prompt": prompt_bundle.get("negative_prompt", ""),
                "width": str(settings.get("width")),
                "height": str(settings.get("height")),
                "seed": str(settings.get("seed")),
                "output_prefix": output_prefix,
                "model_checkpoint": settings.get("model_checkpoint", ""),
                "steps": str(settings.get("steps")),
                "cfg": str(settings.get("cfg")),
                "sampler": settings.get("sampler", ""),
                "scheduler": settings.get("scheduler", ""),
            }.items():
                rendered = rendered.replace("{{" + key + "}}", str(value))
            workflow = json.loads(rendered)
            if not isinstance(workflow, dict):
                raise RuntimeError("Workflow template root must be a JSON object")
            return ctx["run_comfyui_workflow"](project, group, settings, prompt_bundle, workflow, output_prefix)
        except Exception as exc:
            return generate_group_placeholder_svg(project, group, settings, prompt_bundle, f"ComfyUI workflow template failed: {exc}")

    def run_xai_grok_image_workflow(project: dict[str, Any], group: dict[str, Any], settings: dict[str, Any], prompt_bundle: dict[str, str]) -> dict[str, Any]:
        project_id = ctx["safe_project_id"](str(project.get("id") or ctx["active_project_id"]()))
        api_key = ctx["resolve_xai_api_key"](project, project_id)
        if not api_key:
            raise RuntimeError("Grok/xAI API key is not configured; set a project key in XTTS Studio settings or XAI_API_KEY")
        base_url = (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
        model = ctx["grok_image_model_from_settings"](settings, grok_image_model)
        width, height = ctx["grok_image_dimensions_from_settings"](settings)
        no_text = bool(settings.get("no_text", True))
        prompt = ctx["format_grok_image_request_prompt"](prompt_bundle, width, height, no_text=no_text)
        request_payload = ctx["build_grok_image_request_payload"]({**settings, "grok_model": model}, prompt, str(default_settings["image_grok_resolution"]), grok_image_resolutions)
        response = ctx["xai_json_request"](base_url, "/images/generations", api_key, method="POST", payload=request_payload, timeout=180.0, operation_label="xAI image generation request")
        image_url = ctx["extract_xai_image_url"](response)
        if not image_url:
            raise RuntimeError(ctx["format_xai_image_missing_url_error"](response))
        out_dir = ctx["project_images_dir"](project_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{group.get('id', 'group')}_{int(time.time())}_grok.png"
        ctx["save_xai_image_url"](image_url, out)
        path = ctx["rel_path"](out)
        now = time.time()
        return {
            "status": "ready",
            "provider": "xai",
            "model": model,
            "aspect_ratio": settings.get("aspect_ratio"),
            "width": width,
            "height": height,
            "path": path,
            "url": f"/api/image?path={path}&v={int(out.stat().st_mtime)}",
            "positive_prompt": prompt,
            "negative_prompt": ctx["grok_image_negative_prompt_from_bundle"](prompt_bundle, no_text=no_text),
            "xai_request": ctx["build_grok_image_request_metadata"](width, height, grok_reference_limitation_note),
            "created_at": now,
            "updated_at": now,
        }

    def format_chunk_image_prompt(project: dict[str, Any], group: dict[str, Any], chunk: dict[str, Any], settings: dict[str, Any]) -> dict[str, str]:
        positive = ctx["truncate_text"](chunk.get("image_prompt"), 3000)
        negative = ctx["truncate_text"](chunk.get("image_negative_prompt"), 1500)
        context = ctx["visual_context_prefix"](project, group)
        if positive and context:
            positive = ctx["truncate_text"](f"{context}. Chunk image prompt: {positive}", 3000)
        if not positive:
            fallback = ctx["generate_fallback_chunk_prompts"](project, group)
            fallback_item = next((item for item in fallback if str(item.get("id") or "") == str(chunk.get("id") or "")), None)
            if fallback_item:
                positive = ctx["truncate_text"](fallback_item.get("image_prompt"), 3000)
                negative = negative or ctx["truncate_text"](fallback_item.get("image_negative_prompt"), 1500)
        if not positive:
            positive = format_image_prompt(group, settings).get("positive_prompt", "")
        if not negative:
            negative = format_image_prompt(group, settings).get("negative_prompt", "")
        return ctx["apply_no_text_to_prompts"](positive, negative, enabled=bool(settings.get("no_text", True)))

    return {
        "compile_sdxl_txt2img_workflow": compile_sdxl_txt2img_workflow,
        "format_image_prompt": format_image_prompt,
        "format_chunk_image_prompt": format_chunk_image_prompt,
        "generate_group_placeholder_svg": generate_group_placeholder_svg,
        "generate_group_image": generate_group_image,
        "run_xai_grok_image_workflow": run_xai_grok_image_workflow,
    }
