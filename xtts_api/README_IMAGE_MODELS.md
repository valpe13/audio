# Image model checkpoints for XTTS Studio + ComfyUI

This folder contains safe installer wrappers for adding SDXL checkpoint files to a local ComfyUI portable installation. The current XTTS Studio image workflow uses ComfyUI `CheckpointLoaderSimple`, so download full checkpoint `.safetensors` files only. Do not download LoRA files for these installers.

## GitHub Release manifest installer

Image/video model binaries are distributed through GitHub Release assets, not through Git commits. The manifest is stored at `xtts_api/image_video_models_manifest.json` and currently points to release tag `image-video-models-v1` in repository `valpe13/audio`.

The optional ComfyUI portable runtime is managed separately from model files. Its manifest is `xtts_api/comfyui_portable_manifest.json`, release tag is `comfyui-portable-v1`, and target folder is `ComfyUI_windows_portable`. Run it before model/custom-node installers when a machine does not already have ComfyUI portable:

```cmd
xtts_api\install_comfyui_portable.cmd --yes --allow-pending
```

Dry-run without downloading or changing an existing local runtime:

```cmd
xtts_api\install_comfyui_portable.cmd --dry-run --yes --allow-pending
```

Runtime installer behavior:

- validates `ComfyUI_windows_portable\ComfyUI\main.py`, `run_nvidia_gpu.bat`, and `run_cpu.bat`;
- exits successfully without changes when an existing runtime is valid;
- refuses to overwrite an invalid existing `ComfyUI_windows_portable` unless `--force` is used;
- with `--force`, renames the existing folder to a timestamped backup instead of deleting it;
- downloads split release parts into `.installer_cache\comfyui-portable`, reassembles the zip, verifies SHA256 when present, extracts to a temporary folder, validates, then moves into place;
- keeps ComfyUI runtime binaries out of Git commits.

The current ComfyUI portable manifest is intentionally marked `pending_review`. Use `--allow-pending` only for local testing before release approval. Do not upload runtime assets or change the status to `approved` until ComfyUI, embedded Python/packages, custom nodes, and bundled binary licenses allow redistribution.

Package a sanitized local archive without upload:

```cmd
python xtts_api\package_comfyui_portable.py --write-manifest --force
```

The packaging script excludes model folders, input/output/temp/user/cache folders, logs, bytecode, generated/user media, Hugging Face caches, torch caches, and model binaries such as `.safetensors`, `.ckpt`, `.pth`, `.pt`, `.onnx`, `.bin`, and `.gguf`. It writes local artifacts under `release_assets\comfyui-portable-v1`, computes size/SHA256 values, splits below the configured GitHub asset limit, writes a generated manifest copy when requested, and prints `gh release create/upload` commands without running them.

Run from the project root:

```cmd
xtts_api\install_image_video_models.cmd --yes --allow-pending
```

Dry-run without downloading:

```cmd
python xtts_api\install_image_video_models.py --dry-run --yes --allow-pending
```

The installer:

- reads the manifest and installs only missing files under `ComfyUI_windows_portable/ComfyUI/models`;
- writes each download to `*.part`, then renames after completion;
- supports split GitHub Release assets for files larger than GitHub's per-asset upload limit;
- verifies SHA256 when present;
- never overwrites an existing model unless `--force` is passed;
- skips entries with `redistribution_status` other than `approved` unless `--allow-pending` is passed;
- can fall back to original source URLs when explicitly run with `--allow-original-source-fallback`.

Current manifest assets and local integrity values:

| Model | Target path under `ComfyUI/models` | Size | SHA256 | Redistribution status |
| --- | --- | ---: | --- | --- |
| RealVisXL V5.0 FP16 SDXL checkpoint | `checkpoints/RealVisXL_V5.0_fp16.safetensors` | 6.5 GB | `6a35a7855770ae9820a3c931d4964c3817b6d9e3c6f9c4dabb5b3a94e5643b80` | `pending_review` |
| Stable Video Diffusion XT 1.1 checkpoint | `checkpoints/svd_xt.safetensors` | 4.5 GB | `69ccfea1bb45dd63b3ba8b6cfe8b0d45d780995dfdde590aeaa97cc567018d33` | `pending_review` |
| DreamShaper 8 pruned SD1.5 checkpoint | `checkpoints/DreamShaper_8_pruned.safetensors` | 2.0 GB | `879db523c30d3b9017143d56705015e15a2cb5628762c11d086fed9538abd7fd` | `pending_review` |
| AnimateDiff SD1.5 motion module v2 | `animatediff_models/mm_sd_v15_v2.ckpt` | 1.7 GB | `69ed0f5fef82b110aca51bcab73b21104242bc65d6ab4b8b2a2a94d31cad1bf0` | `pending_review` |
| HotshotXL temporal layers SDXL motion model | `animatediff_models/hsxl_temporal_layers.safetensors` | 905.4 MB | `3a3a8013f99ba2991da633a9b82c833c7e7e6b62020b6cab41756601ad06c484` | `pending_review` |

GitHub Release upload note: GitHub rejects assets above 2 GiB, so `RealVisXL_V5.0_fp16.safetensors` and `svd_xt.safetensors` are published as `.partNN` assets in the manifest. The installer streams these parts into one local `*.part` file, verifies the final SHA256, then renames to the target model filename.

Licensing/rehosting warning: all entries are intentionally marked `pending_review` until each upstream model license and terms allow redistribution through this project's GitHub Releases. Do not mark entries `approved` until that review is complete. Do not commit `.safetensors`, `.ckpt`, `.pt`, `.pth`, `.onnx`, `.bin`, or other model binaries to Git; `.gitignore` keeps these files excluded.

If GitHub Release assets are unavailable, keep using the legacy Hugging Face installers below or run the manifest installer with explicit fallback:

```cmd
xtts_api\install_image_video_models.cmd --yes --allow-pending --allow-original-source-fallback
```

## Installed now

RealVisXL full SDXL checkpoint is already installed in the ComfyUI checkpoint folder and is compatible with ComfyUI `CheckpointLoaderSimple`.

- Checkpoint filename: `RealVisXL_V5.0_fp16.safetensors`
- Installed path: `ComfyUI_windows_portable/ComfyUI/models/checkpoints/RealVisXL_V5.0_fp16.safetensors`
- Approximate size: `6.46 GiB`
- In XTTS Studio set:

  ```text
  image_model_checkpoint=RealVisXL_V5.0_fp16.safetensors
  ```

AnimateDiff dependencies may also be installed locally, but the starter motion module `mm_sd_v15_v2.ckpt` is an **SD1.5** AnimateDiff motion model. It is not compatible with the installed SDXL RealVisXL checkpoint. For XTTS Studio `generated_animatediff`, install one full SD1.5 checkpoint in:

```text
ComfyUI_windows_portable\ComfyUI\models\checkpoints\
```

Recommended SD1.5 checkpoint examples include DreamShaper 8, Realistic Vision 5.1, Deliberate, epiCRealism, or the official Stable Diffusion v1-5 pruned checkpoint. After installing, restart ComfyUI and open:

```text
http://127.0.0.1:7870/api/comfyui/animatediff/diagnostics
```

XTTS Studio will only use `generated_animatediff` when ComfyUI reports the required AnimateDiff-Evolved nodes, VideoHelperSuite `VHS_VideoCombine`, `mm_sd_v15_v2.ckpt`, and a detectable SD1.5 checkpoint. Keep `generated_svd` as the default if you only have SDXL/SVD models installed.

## Experimental SDXL AnimateDiff / HotshotXL path

XTTS Studio now exposes a **separate** workflow mode named `generated_hotshotxl` for SDXL-compatible AnimateDiff / HotshotXL experiments. It does not replace `generated_svd` and does not reuse the SD1.5 `generated_animatediff` checkpoint path.

Why this exists:

- Source images are generated with SDXL `RealVisXL_V5.0_fp16.safetensors`.
- The SD1.5 AnimateDiff starter path uses `mm_sd_v15_v2.ckpt` plus an SD1.5 image checkpoint such as `DreamShaper_8_pruned.safetensors`.
- Sending an SDXL RealVisXL image through an SD1.5 AnimateDiff model can soften or change the image because the animation model/checkpoint family does not match the source image family.
- An SDXL/HotshotXL motion model can preserve SDXL checkpoint style better in principle, but it is heavier, more experimental, and more sensitive to exact ComfyUI custom-node versions.

Current local discovery:

- `ComfyUI-AnimateDiff-Evolved` is installed under `ComfyUI_windows_portable/ComfyUI/custom_nodes/ComfyUI-AnimateDiff-Evolved`.
- The installed source code contains HotshotXL / SDXL motion module support and SDXL per-block helper nodes.
- Only the SD1.5 motion model `mm_sd_v15_v2.ckpt` was found in `ComfyUI_windows_portable/ComfyUI/models/animatediff_models` during inspection.
- No SDXL-compatible motion model was found locally, so `generated_hotshotxl` remains guarded by diagnostics until such a model exists.

Diagnostics endpoint:

```text
http://127.0.0.1:7870/api/comfyui/animatediff-sdxl/diagnostics
```

The endpoint reports:

- whether ComfyUI is reachable;
- required node classes from AnimateDiff-Evolved and VideoHelperSuite;
- available checkpoint files;
- available `animatediff_models` files;
- selected SDXL checkpoint;
- selected SDXL/HotshotXL motion model;
- exact blockers before XTTS Studio will submit a generated graph.

Expected model placement:

```text
ComfyUI_windows_portable\ComfyUI\models\animatediff_models\
```

Common SDXL-compatible motion model filenames that XTTS Studio will auto-detect if present:

```text
hsxl_temporal_layers.safetensors
hotshotxl.safetensors
mm_sdxl_v10_beta.ckpt
mm_sdxl_v10_beta.safetensors
```

If your filename differs, set this environment variable before launching XTTS Studio:

```cmd
set XTTS_ANIMATEDIFF_SDXL_MOTION_MODEL=your_sdxl_motion_model_filename.safetensors
```

Optional SDXL checkpoint override:

```cmd
set XTTS_ANIMATEDIFF_SDXL_CHECKPOINT=RealVisXL_V5.0_fp16.safetensors
```

Recommended testing sequence:

1. Keep `generated_svd` selected for production batches.
2. Install or manually place one SDXL-compatible motion module in `ComfyUI_windows_portable\ComfyUI\models\animatediff_models\` without deleting any existing files.
3. Restart ComfyUI so AnimateDiff-Evolved reloads model names.
4. Open `http://127.0.0.1:7870/api/comfyui/animatediff-sdxl/diagnostics`.
5. Only if `ready` is `true`, choose `generated_hotshotxl (SDXL/HotshotXL experimental)` in Advanced ComfyUI settings.
6. Start with the Fast video quality preset and a short group image. Do not batch many groups until one tiny test finishes.

Limitations and VRAM expectations:

- SDXL AnimateDiff / HotshotXL generally needs more VRAM than SVD-XT and much more than SD1.5 AnimateDiff. A 16GB GPU may need short clips, lower resolution, fewer frames, and no other GPU-heavy processes.
- The built-in graph is intentionally minimal: RealVisXL/SDXL checkpoint, loaded source image repeated into a latent batch, AnimateDiff-Evolved motion model injection, KSampler, VAE decode, and VideoHelperSuite MP4 combine.
- It does not yet add IPAdapter, ControlNet, masks, or reference-only conditioning. Those can improve image lock/object-only motion but require more custom-node schemas and more VRAM.
- If diagnostics are not ready, the backend raises a clear blocker instead of silently falling back or submitting an uncertain graph.

## Practical recommendation for 16GB VRAM and many images

1. **Current installed quality-balanced choice:** RealVisXL V5.0 full SDXL checkpoint.
   - Already installed locally as `RealVisXL_V5.0_fp16.safetensors`.
   - Use this first for balanced and quality image generation in XTTS Studio.
   - This is a full SDXL checkpoint, not a LoRA, and works with the current `CheckpointLoaderSimple` workflow.

2. **Fast-many-images alternative:** SDXL Lightning 4-step checkpoint from `ByteDance/SDXL-Lightning`.
   - Best when you need to generate many images quickly.
   - Use the 4-step **checkpoint** `.safetensors` file.
   - Do **not** use the SDXL Lightning LoRA file with the current workflow.
   - In XTTS Studio set:

     ```text
     image_model_checkpoint=sdxl_lightning_4step.safetensors
     ```

3. **Quality-balanced alternative:** Juggernaut XL checkpoint.
   - Slower than Lightning, but better for balanced/quality output if you choose to install it instead of using the installed RealVisXL checkpoint.
   - Use a full checkpoint `.safetensors` file.
   - In XTTS Studio set:

     ```text
     image_model_checkpoint=juggernautXL.safetensors
     ```

## Files

- `install_sdxl_lightning_model.cmd` — Windows launcher for the recommended fast SDXL Lightning 4-step checkpoint.
- `install_sdxl_lightning_model.py` — Python helper that validates the URL, asks for manual confirmation, creates the target folder, and downloads the SDXL Lightning checkpoint.
- `install_juggernaut_xl_model.cmd` — Windows launcher for the Juggernaut XL quality/balanced checkpoint.
- `install_juggernaut_xl_model.py` — Python helper that validates the URL, asks for manual confirmation, creates the target folder, and downloads the Juggernaut XL checkpoint.
- `install_svd_xt_model.cmd` — Windows launcher for the Stability AI SVD-XT 1.1 image-to-video checkpoint.
- `install_svd_xt_model.py` — Python helper that validates the URL, asks for manual confirmation, creates the target folder, and downloads the SVD-XT checkpoint.
- `install_animatediff_deps.cmd` — Windows launcher for installing missing AnimateDiff custom nodes and one starter motion module.
- `install_animatediff_deps.py` — Python helper that locates ComfyUI portable, clones missing custom-node folders without overwriting existing installs, downloads a motion model without overwriting existing model files, and prints manual fallback steps.
- `install_animatediff_sd15_checkpoint.cmd` — Windows launcher for installing one SD1.5 checkpoint required by the `mm_sd_v15_v2.ckpt` AnimateDiff motion module.
- `install_animatediff_sd15_checkpoint.py` — Python helper that validates a direct SD1.5 checkpoint URL, asks for manual confirmation unless `--yes` is used, downloads to the ComfyUI checkpoints folder, and never overwrites existing checkpoint files.
- `install_hotshotxl_deps.cmd` — Windows launcher for installing one SDXL/HotshotXL motion module for the guarded `generated_hotshotxl` backend.
- `install_hotshotxl_deps.py` — Python helper that validates ComfyUI portable, verifies AnimateDiff-Evolved and VideoHelperSuite, downloads a motion model into `ComfyUI_windows_portable/ComfyUI/models/animatediff_models`, and never overwrites existing files.
- `install_comfyui_portable.cmd` — Windows launcher for installing a missing ComfyUI portable runtime from split GitHub Release assets.
- `install_comfyui_portable.py` — manifest-driven runtime installer that validates an existing portable folder, downloads/reassembles/verifies split archives, and avoids overwriting user installs.
- `package_comfyui_portable.py` — local-only sanitized runtime packager/splitter that prints upload commands but never uploads assets.
- `comfyui_portable_manifest.json` — release metadata, required-file validation list, split-asset URLs, exclusions, checksums, and redistribution review status for the portable runtime.

## Target folder

By default, the installers save checkpoints to:

```text
ComfyUI_windows_portable\ComfyUI\models\checkpoints\
```

Default output filenames:

- Installed RealVisXL: `RealVisXL_V5.0_fp16.safetensors`
- SDXL Lightning: `sdxl_lightning_4step.safetensors`
- Juggernaut XL: `juggernautXL.safetensors`
- SVD-XT 1.1: `svd_xt.safetensors`
- AnimateDiff SD1.5: `DreamShaper_8_pruned.safetensors`
- HotshotXL / SDXL AnimateDiff motion model: `hsxl_temporal_layers.safetensors`

The installers treat the path as a string and only create it when you run the script, provide a URL, and confirm the download with `Y`.

## Configure the Hugging Face URL

Model files and access rules can change, and some Hugging Face repositories require accepting terms or using a token. To avoid downloading the wrong checkpoint, the scripts do not hard-code uncertain URLs.

Use a direct Hugging Face checkpoint URL in this form:

```text
https://huggingface.co/<owner>/<repo>/resolve/main/<file>.safetensors
```

### SDXL Lightning fast checkpoint

Use the 4-step checkpoint from `ByteDance/SDXL-Lightning`, not a LoRA:

```cmd
set SDXL_LIGHTNING_MODEL_URL=https://huggingface.co/ByteDance/SDXL-Lightning/resolve/main/<4-step-checkpoint-file>.safetensors
xtts_api\install_sdxl_lightning_model.cmd
```

Alternatively, edit `MODEL_URL` in `install_sdxl_lightning_model.cmd`.

### Juggernaut XL quality/balanced checkpoint

Use a direct Juggernaut XL checkpoint `.safetensors` URL:

```cmd
set JUGGERNAUT_XL_MODEL_URL=https://huggingface.co/<owner>/<repo>/resolve/main/<file>.safetensors
xtts_api\install_juggernaut_xl_model.cmd
```

Alternatively, edit `MODEL_URL` in `install_juggernaut_xl_model.cmd`.

### SVD-XT 1.1 image-to-video checkpoint

The SVD-XT installer includes the recommended Stability AI direct URL by default:

```cmd
xtts_api\install_svd_xt_model.cmd
```

### AnimateDiff SD1.5 checkpoint

The installed starter motion module `mm_sd_v15_v2.ckpt` requires a full SD1.5 image checkpoint. SDXL checkpoints such as RealVisXL and video checkpoints such as SVD-XT are not compatible with this AnimateDiff setup.

The safe installer defaults to DreamShaper 8 pruned:

```cmd
xtts_api\install_animatediff_sd15_checkpoint.cmd
```

Direct checkpoint URL used by default:

```text
https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors
```

Target path:

```text
ComfyUI_windows_portable\ComfyUI\models\checkpoints\DreamShaper_8_pruned.safetensors
```

If the default URL is blocked or the upstream filename changes, override both URL and filename:

```cmd
set ANIMATEDIFF_SD15_CHECKPOINT_URL=https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors
set ANIMATEDIFF_SD15_CHECKPOINT_FILENAME=DreamShaper_8_pruned.safetensors
xtts_api\install_animatediff_sd15_checkpoint.cmd
```

Manual fallback: download a full SD1.5 checkpoint such as DreamShaper 8, Realistic Vision 5.1, Deliberate, epiCRealism, or official Stable Diffusion v1-5 pruned. Save the `.safetensors` or `.ckpt` file without overwriting existing files in `ComfyUI_windows_portable\ComfyUI\models\checkpoints\`, then restart ComfyUI and XTTS Studio.

Model page:

```text
https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1
```

Direct checkpoint URL used by default:

```text
https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1/resolve/main/svd_xt_1_1.safetensors
```

The installer saves this checkpoint as `svd_xt.safetensors` so it matches XTTS Studio's default `video_i2v_model_checkpoint` value. If the upstream filename changes, override the URL with `SVD_XT_MODEL_URL`:

```cmd
set SVD_XT_MODEL_URL=https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1/resolve/main/svd_xt_1_1.safetensors
xtts_api\install_svd_xt_model.cmd
```

## Manual confirmation and safety

Each script prints a warning before downloading. It will only continue if you type exactly:

```text
Y
```

If the model URL is empty, invalid, or still a placeholder, the script exits before creating folders or downloading files. Any answer other than `Y` cancels the operation without creating folders or downloading files.

## Hugging Face login or token

If Hugging Face returns an HTTP error, the repository may require login, license acceptance, or a token.

Recommended steps:

1. Open the model page in a browser and accept any required terms.
2. Create a Hugging Face access token if needed.
3. Run the installer with `HF_TOKEN` or `HUGGINGFACE_TOKEN` set.

Example for SDXL Lightning:

```cmd
set HF_TOKEN=hf_your_token_here
set SDXL_LIGHTNING_MODEL_URL=https://huggingface.co/ByteDance/SDXL-Lightning/resolve/main/<4-step-checkpoint-file>.safetensors
xtts_api\install_sdxl_lightning_model.cmd
```

Example for Juggernaut XL:

```cmd
set HF_TOKEN=hf_your_token_here
set JUGGERNAUT_XL_MODEL_URL=https://huggingface.co/<owner>/<repo>/resolve/main/<file>.safetensors
xtts_api\install_juggernaut_xl_model.cmd
```

Example for SVD-XT 1.1:

```cmd
set HF_TOKEN=hf_your_token_here
set SVD_XT_MODEL_URL=https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1/resolve/main/svd_xt_1_1.safetensors
xtts_api\install_svd_xt_model.cmd
```

Example for AnimateDiff SD1.5:

```cmd
set HF_TOKEN=hf_your_token_here
set ANIMATEDIFF_SD15_CHECKPOINT_URL=https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors
xtts_api\install_animatediff_sd15_checkpoint.cmd
```

Example for HotshotXL / SDXL AnimateDiff:

```cmd
set HF_TOKEN=hf_your_token_here
xtts_api\install_hotshotxl_deps.cmd
```

## HotshotXL / SDXL AnimateDiff install

The guarded `generated_hotshotxl` backend expects the existing AnimateDiff-Evolved and VideoHelperSuite custom nodes plus one SDXL-compatible motion model in:

```text
ComfyUI_windows_portable\ComfyUI\models\animatediff_models\
```

Run the safe installer from the project root:

```cmd
xtts_api\install_hotshotxl_deps.cmd
```

The default direct model URL is:

```text
https://huggingface.co/hotshotco/Hotshot-XL/resolve/main/hsxl_temporal_layers.safetensors
```

The default local filename is:

```text
hsxl_temporal_layers.safetensors
```

Override URL or filename only if the upstream file changes or you choose a different SDXL-compatible motion module:

```cmd
set HOTSHOTXL_MOTION_MODEL_URL=https://huggingface.co/hotshotco/Hotshot-XL/resolve/main/hsxl_temporal_layers.safetensors
set HOTSHOTXL_MOTION_MODEL_FILENAME=hsxl_temporal_layers.safetensors
xtts_api\install_hotshotxl_deps.cmd
```

After install:

1. Restart ComfyUI so AnimateDiff-Evolved reloads `animatediff_models`.
2. Restart XTTS Studio if it was already open.
3. Open diagnostics:

   ```text
   http://127.0.0.1:7870/api/comfyui/animatediff-sdxl/diagnostics
   ```

4. Use `generated_hotshotxl` only when diagnostics reports `ready: true`.
5. Start with Fast video quality, short clips, and no batch generation until one tiny test succeeds.

Manual fallback: if the direct download fails, open the HotshotXL model page in a browser, accept any required terms, download `hsxl_temporal_layers.safetensors`, save it without overwriting anything into `ComfyUI_windows_portable\ComfyUI\models\animatediff_models\`, then restart ComfyUI and re-check diagnostics.

## Recommended generation settings

## Grok prompt style and loop animation prompts

Grok/xAI video grouping now asks for concise SDXL/RealVisXL prompts that are subject-first and concrete. The positive image prompt should usually be `35–70` words, start with exact main subject count/type/pose/action, and avoid broad ambiguous terms that can introduce unwanted elements. Do not mention animals, crowds, water sources, broad landscapes, weapons, or background objects unless they should literally appear.

For prehistoric or early-human scenes, a safer prompt style is:

```text
Two early hominids standing near sparse dry grassland at dawn, one adult holding a child, one adult holding a small stone tool, no animals visible. Soft amber light, simple earth tones, realistic skin and coarse natural hair, low eye-level documentary composition, quiet prehistoric atmosphere, uncluttered background.
```

Scene-specific negative prompts should directly exclude common unwanted additions when relevant, for example `elephants, mammoths, modern safari, extra animals, crowds, weapons, fantasy armor, modern clothing, modern buildings`.

Grok/xAI video grouping also stores separate `animation_positive_prompt`, `animation_negative_prompt`, `video_motion_intensity`, and `video_loop_notes` fields for each video group. These prompts are written for simple seamless image-to-video loops: locked or nearly locked camera, first and last frame match naturally, calm cyclic natural ambient motion, no beginning/end reveal, and no cuts, zooms, pans, scene changes, character action, morphing, object popping, new objects, disappearing objects, or text. XTTS Studio displays these fields in the group detail card for future or alternate video workflows; the current vanilla SVD/SVD-XT workflow does not wire text prompts into nodes that do not support them.

### RealVisXL V5.0 — balanced, recommended for 16GB VRAM

- Checkpoint: `RealVisXL_V5.0_fp16.safetensors`
- Steps: `20` or `24`
- CFG: `5.5` or `6.0`
- Sampler: `dpmpp_2m_sde`
- Scheduler: `karras`
- Vertical size: `832x1216`
- Horizontal size: `1216x832`

### RealVisXL V5.0 — quality, recommended for 16GB VRAM if speed is acceptable

- Checkpoint: `RealVisXL_V5.0_fp16.safetensors`
- Steps: `28`
- CFG: `6.0`
- Sampler: `dpmpp_2m_sde`
- Scheduler: `karras`
- Vertical size: `1024x1536` only if generation speed is acceptable
- Horizontal size: `1536x1024` only if generation speed is acceptable

### SDXL Lightning 4-step — fast many images alternative

- Checkpoint: `sdxl_lightning_4step.safetensors`
- Steps: `4`
- CFG: `1.0`
- Sampler: `euler`
- Scheduler: `sgm_uniform` if available, otherwise `normal` or `simple`
- Vertical size: `832x1216`
- Horizontal size: `1216x832`

### Juggernaut XL — balanced alternative

- Checkpoint: `juggernautXL.safetensors`
- Steps: `16`
- CFG: `6.0`
- Sampler: `dpmpp_2m_sde`
- Scheduler: `karras`
- Vertical size: `832x1216`
- Horizontal size: `1216x832`

### Juggernaut XL — quality alternative

- Checkpoint: `juggernautXL.safetensors`
- Steps: `28`
- CFG: `6.5`
- Sampler: `dpmpp_2m_sde`
- Scheduler: `karras`
- Use the same aspect-ratio sizes as balanced unless the workflow requires another size.

## XTTS Studio setting summary

For the currently installed RealVisXL full SDXL checkpoint:

```text
image_model_checkpoint=RealVisXL_V5.0_fp16.safetensors
```

For fast generation with the optional Lightning alternative:

```text
image_model_checkpoint=sdxl_lightning_4step.safetensors
```

For balanced/quality generation with the optional Juggernaut XL alternative:

```text
image_model_checkpoint=juggernautXL.safetensors
```

## SVD/SVD-XT image-to-video stage

XTTS Studio can now use the RealVisXL group image as a source frame and queue a ComfyUI SVD/SVD-XT image-to-video job for the same group.

Recommended first setup:

1. Install ComfyUI VideoHelperSuite, because the generated SVD workflow uses `VHS_VideoCombine` for MP4 output.
2. Ensure VideoHelperSuite can find ffmpeg for MP4 output. The most reliable portable fix for VideoHelperSuite is to place a real `ffmpeg.exe` directly in `ComfyUI_windows_portable\`, because this is one of the explicit locations VideoHelperSuite checks.

If `imageio-ffmpeg` is installed in ComfyUI's embedded Python, copy its bundled executable to that location:

```cmd
ComfyUI_windows_portable\python_embeded\python.exe -m pip install imageio-ffmpeg
ComfyUI_windows_portable\python_embeded\python.exe -c "import imageio_ffmpeg, os; p=imageio_ffmpeg.get_ffmpeg_exe(); print(p); print(os.path.exists(p))"
copy /Y ComfyUI_windows_portable\python_embeded\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe ComfyUI_windows_portable\ffmpeg.exe
ComfyUI_windows_portable\ffmpeg.exe -version
```

If the bundled filename differs, use the actual `ffmpeg-*.exe` file present under `ComfyUI_windows_portable\python_embeded\Lib\site-packages\imageio_ffmpeg\binaries\`. If the embedded Python path is unavailable, install ffmpeg separately and still place/copy the executable as `ComfyUI_windows_portable\ffmpeg.exe`, or add ffmpeg to the system `PATH`.

3. Download an SVD/SVD-XT checkpoint and place it in:

```text
ComfyUI_windows_portable\ComfyUI\models\checkpoints\
```

Recommended model:

- Model page: `https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1`
- Direct checkpoint URL: `https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1/resolve/main/svd_xt_1_1.safetensors`
- Target path used by XTTS Studio: `ComfyUI_windows_portable/ComfyUI/models/checkpoints/svd_xt.safetensors`

Safe installer command:

```cmd
xtts_api\install_svd_xt_model.cmd
```

The installer downloads `svd_xt_1_1.safetensors` from the Stability AI repository and saves it as the stable XTTS Studio alias `svd_xt.safetensors`. You can override the direct URL with `SVD_XT_MODEL_URL` if the upstream filename changes:

```cmd
set SVD_XT_MODEL_URL=https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1/resolve/main/svd_xt_1_1.safetensors
xtts_api\install_svd_xt_model.cmd
```

Hugging Face may require logging in and accepting the Stability AI model terms before the direct URL works. If needed, open the model page in a browser first, accept the terms, then set `HF_TOKEN` or `HUGGINGFACE_TOKEN` before running the installer.

4. In XTTS Studio Advanced ComfyUI, SVD/SVD-XT image-to-video is enabled by default when using current settings. Choose a universal SVD quality preset:

- `fast`: `14` frames, `6` fps, `12` steps, lower motion bucket; useful for quick previews.
- `balanced`: `25` frames, `6` fps, `20` steps; current recommended default and now less zoom-prone than older balanced values.
- `quality`: `49` frames, `8` fps, `30` steps; slower, slightly smoother/longer loops.

XTTS Studio also has `video_i2v_target_duration_sec` (default `20`, safe range `2`-`60`) for fast longer loop files. This does **not** ask SVD/SVD-XT to sample hundreds of frames. The backend keeps the selected `fast` / `balanced` / `quality` sampled frame count and asks VideoHelperSuite `VHS_VideoCombine` to extend the MP4 with ping-pong/repeated output frames, lowering only the output FPS if an extreme custom frame/FPS combination would otherwise require too many repeats. For example, the `fast` preset still samples only `14` frames and `12` steps, then writes an approximately 20-second loop file for one-minute groups. Increasing target duration therefore has little extra generation cost, but it repeats/ping-pongs existing motion and does not add extra unique motion.

`video_i2v_preview_playback_rate` (default `1.0`, safe range `0.25`-`2.0`) controls only browser preview playback speed for the main preview and group detail video elements. It is useful for checking loops slower or faster in XTTS Studio, but it does not change the generated MP4 duration, frame count, encoding FPS, or SVD sampling cost.

The preset slider fills the numeric SVD fields and the backend applies the selected preset consistently. A separate SVD motion style then deterministically lowers or caps motion-related values (`video_i2v_motion_bucket_id`, `video_i2v_augmentation_level`, `video_i2v_cfg`, and for some styles `frames`, `fps`, or `steps`) while preserving the quality preset's speed/quality intent:

- `still_life`: very low motion and minimal camera drift.
- `ambient_nature`: default; subtle grass, leaves, water, smoke, clouds, or dust motion with low camera movement.
- `human_subtle`: very subtle face/body drift for people, avoiding large camera motion.
- `cinematic_slow`: slightly more motion, but still controlled.

These styles reduce the chance of zoom/drift, but vanilla SVD/SVD-XT is still image-conditioned and cannot guarantee perfectly locked cameras or prompt-specific object motion. Use Grok's per-group `video_motion_intensity` and `video_loop_notes` as human guidance only unless you switch to a custom SVD workflow that supports text conditioning.

Generated SVD/SVD-XT clips are intended as looping scene assets. XTTS Studio enables VideoHelperSuite `pingpong` mode by default (`video_i2v_pingpong=true`) so the rendered MP4 plays forward then backward for a smoother seam when the installed `VHS_VideoCombine` node supports it. The studio preview also keeps the selected group's video element muted, inline, and browser-looped while the timeline playhead remains inside that group's start/end range; when the playhead enters another group, preview switches to that group's video if available, otherwise its image.

Core settings for the balanced preset:

```text
video_i2v_enabled=true
video_i2v_quality_preset=balanced
video_i2v_motion_style=ambient_nature
video_i2v_workflow_mode=generated_svd
video_i2v_model_checkpoint=svd_xt.safetensors
video_i2v_frames=25
video_i2v_fps=6
video_i2v_motion_bucket_id=72
video_i2v_augmentation_level=0.005
video_i2v_cfg=2.0
video_i2v_steps=20
video_i2v_sampler=euler
video_i2v_scheduler=normal
video_i2v_pingpong=true
video_i2v_target_duration_sec=20
video_i2v_preview_playback_rate=1.0
```

Generate order per group:

1. Generate the RealVisXL group image.
2. Use `Generate SVD video` on the group card.

The backend serves completed files through `/api/video` and stores them under the project output `videos` folder.

## Optional xAI Grok Imagine Video backend

XTTS Studio also exposes `generated_grok_imagine_video` as a separate hosted image-to-video backend. It uses the existing Grok/xAI secret handling: save a project xAI key in Studio settings or set `XAI_API_KEY` in the environment. Keys are stored in the per-project secrets file and are not written into `project.json` or returned by diagnostics.

Official docs used for this integration:

- `https://docs.x.ai/developers/model-capabilities/video/generation`
- `https://docs.x.ai/developers/model-capabilities/video/image-to-video`

The current implementation uses the documented REST path:

```text
POST https://api.x.ai/v1/videos/generations
GET  https://api.x.ai/v1/videos/{request_id}
```

For image-to-video, XTTS Studio sends the group source image as a base64 data URI in the documented `image: {"url": "data:image/...;base64,..."}` field, then polls until `status=done`, downloads the temporary xAI video URL, and persists it under the same project `outputs/videos` folder used by SVD/SVD-XT.

Settings:

```text
video_i2v_workflow_mode=generated_grok_imagine_video
video_i2v_grok_model=grok-imagine-video
video_i2v_grok_duration_sec=5
video_i2v_grok_resolution=480p
video_i2v_grok_aspect_ratio_mode=auto
```

Quality presets map conservatively to confirmed resolutions:

- `fast`: `480p`
- `balanced`: `720p`
- `quality`: `720p`

The xAI docs/examples confirm `480p` and `720p`. `1080p` is intentionally not exposed until official docs confirm it for this model/API.

Aspect ratio is orientation-aware by default. With `video_i2v_grok_aspect_ratio_mode=auto`, XTTS Studio resolves the source image dimensions the same way the SVD path does and sends `16:9` for landscape or square/unknown images and `9:16` for portrait images. You can force `16:9` or `9:16` from the UI if needed.

Prompt behavior: the backend prefers each group's `animation_positive_prompt`, then `visual_prompt`, then summary/title, and appends loop-oriented locked-camera/object-motion instructions: seamless looping video, perfect loop, first and last frame match naturally, cyclic ambient motion, stable composition, no beginning/end reveal, no cuts/jump cuts/scene transitions, no zoom/pan/shake/sudden camera movement, no object popping, no new/disappearing objects, and only subtle in-frame natural motion. For landscape scenes, prompts explicitly ask leaves, grass, water, and clouds to move in a gentle cyclic pattern.

Diagnostics:

```text
http://127.0.0.1:7870/api/xai/imagine-video/diagnostics
```

The diagnostics endpoint reports key presence, model/defaults, confirmed resolutions, aspect-ratio behavior, docs links, and blockers without exposing secrets.

Cost/rate-limit warning: Grok Imagine Video is a hosted paid xAI video endpoint. Do not bulk queue groups unless you explicitly intend to spend xAI credits and accept provider rate limits. For no-cost/local generation, keep `generated_svd` selected.

## Optional AnimateDiff backend scaffold

XTTS Studio now exposes an experimental `generated_animatediff` value for `video_i2v_workflow_mode`. This does **not** replace SVD/SVD-XT: `generated_svd` remains the default and the stable working path.

The current AnimateDiff option is intentionally guarded. ComfyUI AnimateDiff setups vary by custom-node version, node names, loader inputs, motion module filenames, ControlNet/IPAdapter usage, and video output nodes. Because of that, XTTS Studio does not invent a fragile generated AnimateDiff graph that would fail on most local installs. When `generated_animatediff` is selected, the backend verifies that the group image exists, prepares the same group prompt/settings inputs, then returns an actionable missing-dependency/workflow message until a validated AnimateDiff workflow is wired in.

Quality expectation: the currently wired AnimateDiff path is SD1.5-based (`mm_sd_v15_v2.ckpt` plus an SD1.5 checkpoint such as DreamShaper 8), while the source still image is commonly generated with the SDXL RealVisXL checkpoint. That SDXL-to-SD1.5 mismatch can reduce fidelity, soften or reinterpret details, and produce weaker animation than expected. This is normal for this path and is not a sign that RealVisXL is bad. Keep SVD-XT as the stable mass-production choice when preserving the RealVisXL source image matters; use SD1.5 AnimateDiff mainly for experiments where text/object-motion behavior is more important than exact SDXL image preservation.

An SDXL AnimateDiff-style route could be better for RealVisXL fidelity, but only if the local ComfyUI install has an SDXL-compatible motion module/workflow (for example AnimateDiff SDXL/Beta-style modules or HotshotXL-style workflows), matching node schemas visible in `/object_info`, and enough VRAM. XTTS Studio should treat that as a separate verified integration step rather than automatically downloading large models or guessing a fragile graph. Practical alternatives today are: SVD-XT with locked-camera prompts/settings for quality-preserving loops, or a separate depth/parallax/RIFE-style workflow for mass background animation when the goal is subtle motion rather than prompt-driven object action.

Recommended ComfyUI setup to try AnimateDiff safely:

1. Install custom nodes:
   - `ComfyUI-AnimateDiff-Evolved`
   - `ComfyUI-VideoHelperSuite`
   - Optional but strongly recommended for preserving the source image and object placement: IPAdapter nodes, ControlNet nodes, and matching models.

   Safe installer command for the required nodes plus one starter motion module:

   ```cmd
   xtts_api\install_animatediff_deps.cmd
   ```

   The installer targets the configured portable folder shape used by XTTS Studio by default:

   ```text
   ComfyUI_windows_portable\ComfyUI\
   ```

   It checks that `ComfyUI_windows_portable\ComfyUI\main.py` exists, creates only missing folders, and never overwrites existing custom nodes or motion model files. If your ComfyUI portable folder is elsewhere, set `COMFYUI_PORTABLE_ROOT` before running it:

   ```cmd
   set COMFYUI_PORTABLE_ROOT=D:\AI\ComfyUI_windows_portable
   xtts_api\install_animatediff_deps.cmd
   ```

   The installer clones missing custom nodes to:

   ```text
   ComfyUI_windows_portable\ComfyUI\custom_nodes\ComfyUI-AnimateDiff-Evolved\
   ComfyUI_windows_portable\ComfyUI\custom_nodes\ComfyUI-VideoHelperSuite\
   ```

   If Git is unavailable, install manually from:

   ```text
   https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved
   https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
   ```

2. Put AnimateDiff motion modules under:

   ```text
   ComfyUI_windows_portable\ComfyUI\models\animatediff_models\
   ```

   The safe installer downloads this common starter SD1.5 motion module by default:

   ```text
   https://huggingface.co/guoyww/animatediff/resolve/main/mm_sd_v15_v2.ckpt
   ```

   Target path:

   ```text
   ComfyUI_windows_portable\ComfyUI\models\animatediff_models\mm_sd_v15_v2.ckpt
   ```

   Common starting motion modules include `mm_sd_v15_v2.ckpt` for SD1.5 AnimateDiff workflows or `temporaldiff-v1-animatediff.ckpt` where that workflow expects it. Use the exact filename required by the ComfyUI workflow you validate. If the default Hugging Face URL changes or is blocked, download the file manually from the model page and save it to the target folder above, or override the URL and filename:

   ```cmd
   set ANIMATEDIFF_MOTION_MODEL_URL=https://huggingface.co/guoyww/animatediff/resolve/main/mm_sd_v15_v2.ckpt
   set ANIMATEDIFF_MOTION_MODEL_FILENAME=mm_sd_v15_v2.ckpt
   xtts_api\install_animatediff_deps.cmd
   ```

   If Hugging Face requires authentication, accept any model terms in your browser and set `HF_TOKEN` or `HUGGINGFACE_TOKEN` before running the installer.
3. Install a full SD1.5 checkpoint for the `mm_sd_v15_v2.ckpt` motion module. SDXL and SVD/SVD-XT checkpoints are not compatible with that motion module.

   Safe installer command:

   ```cmd
   xtts_api\install_animatediff_sd15_checkpoint.cmd
   ```

   Default target path:

   ```text
   ComfyUI_windows_portable\ComfyUI\models\checkpoints\DreamShaper_8_pruned.safetensors
   ```

   If direct download is blocked, manually download a full SD1.5 checkpoint such as DreamShaper 8, Realistic Vision 5.1, Deliberate, epiCRealism, or official Stable Diffusion v1-5 pruned and save it to `ComfyUI_windows_portable\ComfyUI\models\checkpoints\` without overwriting existing files.
4. Restart ComfyUI and XTTS Studio, then confirm the AnimateDiff nodes and the SD1.5 checkpoint appear in diagnostics:

   ```text
   http://127.0.0.1:7870/api/comfyui/animatediff/diagnostics
   ```
5. Build and test a minimal AnimateDiff workflow directly in ComfyUI first. Use a short test such as `16` frames, `8` fps, `12`-`20` steps, and a small resolution that fits VRAM.
6. Only after the workflow works in ComfyUI, wire it into XTTS Studio as a future template/generated workflow. The prompts XTTS Studio already stores per group are intended for this:
   - `visual_prompt` / `negative_prompt` for source image meaning.
   - `animation_positive_prompt` / `animation_negative_prompt` for motion guidance.

After installation, restart ComfyUI, open XTTS Studio, and select `generated_animatediff` only for dependency/workflow testing. Keep prompts object-locked: ask for `locked camera`, `static camera`, `no camera movement`, and specific in-frame object or environment motion. The current XTTS Studio backend still guards generated AnimateDiff output until a validated real AnimateDiff graph is wired in.

Suggested object-motion positive prompt modifier:

```text
locked camera, static camera, no camera movement, original composition stays fixed, objects move naturally inside the frame, leaves swaying, grass moving in a light breeze, water ripples, smoke drifting slowly, candle or fire flicker, dust motes drifting, subtle fabric movement
```

Suggested low-camera-motion negative prompt terms:

```text
camera movement, camera pan, camera zoom, camera orbit, dolly, trucking shot, handheld camera, camera shake, drifting frame, whole image moving, scene change, cuts, morphing, warping, new objects appearing, fast action
```

Important limitation: AnimateDiff can be better than vanilla SVD/SVD-XT for prompt-guided/object-like motion, but it still cannot guarantee that only selected objects move from a single still image. Reliable isolated object motion usually needs masks, segmentation, ControlNet, IPAdapter/reference conditioning, or a hand-authored workflow per scene type. For the current XTTS Studio pipeline, use the new `Object motion — locked camera` motion style plus explicit animation prompts as the safest first pass.
