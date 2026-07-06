# Docker deployment

This runs the deployable audio stack in one Linux container:

- XTTS Studio: http://localhost:7870/studio/
- Silero TTS API: http://localhost:7866/health
- Fish Speech API placeholder: http://localhost:7865/health

The Windows portable ComfyUI bundle is not included. XTTS Studio can still use xAI/Grok features through `XAI_API_KEY`, or an external ComfyUI URL configured in the UI.

Docker defaults to the Silero backend so a fresh machine can generate audio without a private XTTS voice reference. Switch `XTTS_DEFAULT_TTS_BACKEND=xtts` after adding a reference WAV if you want XTTS voice cloning by default.

## Requirements

- Docker Desktop or Docker Engine with Docker Compose v2.
- At least 12 GB free disk space for the image and model caches.
- For GPU acceleration: NVIDIA driver plus NVIDIA Container Toolkit / Docker Desktop GPU support.

## One-click Windows installer

For a fresh Windows machine, use:

```bat
install_docker_stack.cmd
```

You can send only this `.cmd` file after the repository changes are pushed. If `install_docker_stack.ps1` is not next to it, the `.cmd` downloads the PowerShell installer from GitHub first.

It checks Docker Desktop, installs it in per-user WSL 2 mode if missing, starts Docker, downloads this repository if needed, builds the Docker image, starts the stack, warms up the Silero model with Russian text, verifies health checks, and opens XTTS Studio.

If Docker Desktop or WSL requires a Windows reboot, reboot and run the same file again.

Optional GPU run:

```bat
install_docker_stack.cmd -UseGpu
```

Optional XTTS model preload:

```bat
install_docker_stack.cmd -PreloadXtts
```

Optional update of an existing git checkout before starting:

```bat
install_docker_stack.cmd -UpdateProject
```

## First run

```bash
docker compose up --build
```

Open http://localhost:7870/studio/. The first audio generation uses Silero by default and downloads the Silero torch.hub model into `docker-data/models/`.

The first XTTS generation, if enabled in Studio settings, downloads the Coqui XTTS v2 model into `docker-data/models/`. These downloads are reused on later starts.

## Voice reference

XTTS voice cloning needs a reference WAV. Put it at:

```text
docker-data/reference_audio/natalia_shtin/natalia_shtin_clean_reference.wav
```

or set another reference path in the Studio UI after the container starts. The path above maps to the default project setting:

```text
xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.wav
```

## GPU run

```bash
docker compose -f compose.yml -f compose.gpu.yml up --build
```

Without GPU support, use the normal command. `XTTS_DEVICE=auto` falls back to CPU when CUDA is not visible.

## Configuration

Copy `docker.env.example` to `.env` if you want to override ports or service switches:

```bash
cp docker.env.example .env
```

Useful variables:

- `AUDIO_XTTS_PORT`, `AUDIO_SILERO_PORT`, `AUDIO_FISH_PORT`: host ports.
- `XTTS_DEVICE`: `auto`, `cpu`, or `cuda`.
- `SILERO_DEVICE`: `cpu`, `auto`, or `cuda`.
- `XTTS_DEFAULT_TTS_BACKEND`: `silero` for no-reference first run, or `xtts` after adding a voice reference.
- `START_XTTS`, `START_SILERO`, `START_FISH`: set to `0` to disable a service.
- `XAI_API_KEY`: optional key for xAI/Grok image/video/text helpers.

## Persistent data

Docker writes runtime data under `docker-data/`:

- `studio_projects/`: projects, uploads, generated chunks, exports.
- `reference_audio/`: voice references.
- `fish_outputs/` and `silero_outputs/`: direct API outputs.
- `models/`: Coqui, torch.hub, Hugging Face, and other cache data.

## Smoke checks

```bash
curl http://localhost:7870/api/health
curl http://localhost:7866/health
curl http://localhost:7865/health
```

To stop:

```bash
docker compose down
```
