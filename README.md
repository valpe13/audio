# Local XTTS Studio + optional audio APIs/ComfyUI bridges

## Fresh Windows setup for the current XTTS workflow

The active workflow is the standalone XTTS Studio in [`xtts_api/`](xtts_api/). It is launched by [`run_audio_stack.cmd`](run_audio_stack.cmd) and does **not** require [`ComfyUI_windows_portable/`](ComfyUI_windows_portable/) for normal XTTS generation. The ComfyUI folders in this repository are optional bridges for older/alternate workflows.

### One-file installer for end users

Give a fresh Windows user only [`audio_xtts_universal_installer.cmd`](audio_xtts_universal_installer.cmd). They can put it into an empty folder and run it. The installer will:

- install [`Python 3.10.11`](README.md) for the current user if [`py -3.10`](README.md) is not available;
- download this repository from [`https://github.com/valpe13/audio`](https://github.com/valpe13/audio) into [`audio/`](audio/);
- download [`xtts_assets_v1.zip`](https://github.com/valpe13/audio/releases/download/xtts-assets-v1/xtts_assets_v1.zip) from GitHub Releases;
- verify the release asset SHA256 checksum;
- extract the XTTS v2 model into the normal Coqui cache at [`%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2`](README.md);
- extract the default Natalia Shtin reference into [`xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.wav`](xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.wav);
- run [`install_models.cmd --no-pause`](install_models.cmd) to create [`xtts_api/.venv/`](xtts_api/.venv/) and install Python libraries.

After it finishes, start [`audio/run_audio_stack.cmd`](audio/run_audio_stack.cmd) and choose option `1`.

From a fresh clone on Windows:

```bat
git clone https://github.com/valpe13/audio.git
cd audio
install_models.cmd
run_audio_stack.cmd
```

For unattended setup/CI checks, run [`install_models.cmd --no-pause`](install_models.cmd) to skip the final keypress prompt.

Choose option `1` in [`run_audio_stack.cmd`](run_audio_stack.cmd) to open XTTS Studio at [`http://127.0.0.1:7870/studio/`](README.md).

[`install_models.cmd`](install_models.cmd) prepares only the required XTTS path:

- creates/reuses the Python 3.10 virtual environment at [`xtts_api/.venv/`](xtts_api/.venv/);
- installs [`xtts_api/requirements.txt`](xtts_api/requirements.txt) with the CUDA 12.1 PyTorch wheel index and keeps [`setuptools`](README.md) below `81` because the Coqui/librosa stack still imports [`pkg_resources`](README.md);
- downloads/builds the default Natalia Shtin reference WAV at [`xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.wav`](xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.wav) using [`xtts_api/prepare_natalia_shtin_reference.py`](xtts_api/prepare_natalia_shtin_reference.py);
- preloads Coqui model [`tts_models/multilingual/multi-dataset/xtts_v2`](README.md) into the normal per-user Coqui cache, typically [`%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2`](README.md).

If you specifically need ComfyUI later, install or unpack it separately into [`ComfyUI_windows_portable/`](ComfyUI_windows_portable/) and use launcher options `4` or `5`. The current XTTS Studio server in [`xtts_api/studio_server.py`](xtts_api/studio_server.py) runs directly through Coqui [`TTS`](xtts_api/requirements.txt:1), not through ComfyUI or custom nodes.

This workspace contains a complete local long-form audio pipeline:

```text
Russian text → text cleaner → sentence/paragraph/micro-pause chunker → Fish Speech backend adapter
→ seed-based realism planner → breath/room-tone/pitch/loudness processor → concat → mastering → WAV/MP3 export
```

The backend currently defaults to a safe placeholder in [`fish_speech_api/fish_backend.py`](fish_speech_api/fish_backend.py). It produces a shaped synthetic tone instead of speech so the whole workflow, API contract, file export, and ComfyUI bridge can be tested without downloading large ML models or installing unstable CUDA dependencies.

## Layout

- [`fish_speech_api/`](fish_speech_api/) — local HTTP API wrapper, backend adapter, long-form workflow, sample Russian text, and test generation script.
- [`fish_speech_api/audio_workflow.py`](fish_speech_api/audio_workflow.py) — cleaner, chunker, seed-based pause/prosody planner, safe realism layer, room tone, concat, mastering, WAV export, optional MP3 export through [`ffmpeg`](https://ffmpeg.org/).
- [`fish_speech_api/sample_russian_sleep_lecture.txt`](fish_speech_api/sample_russian_sleep_lecture.txt) — short Russian sleep-lecture sample.
- [`comfyui_fish_speech_bridge/`](comfyui_fish_speech_bridge/) — optional ComfyUI custom node.
- [`silero_tts_api/`](silero_tts_api/) — local Silero TTS/RU torch.hub backend, FastAPI wrapper, 30-second Russian test script, and validation manifests.
- [`comfyui_silero_tts_bridge/`](comfyui_silero_tts_bridge/) — ComfyUI custom node that calls the local Silero RU API.
- [`xtts_api/`](xtts_api/) — isolated XTTS v2 smoke-test environment and Russian generation helper, kept separate from ComfyUI portable Python.

## XTTS v2 through ComfyUI-XTTS

The ComfyUI portable bundle was inspected only at targeted paths. Its embedded Python is `3.13.9` and reports CUDA-enabled `torch 2.9.1+cu130`. The upstream [`AIFSH/ComfyUI-XTTS`](https://github.com/AIFSH/ComfyUI-XTTS) custom node is cloned into [`ComfyUI_windows_portable/ComfyUI/custom_nodes/ComfyUI-XTTS/`](ComfyUI_windows_portable/ComfyUI/custom_nodes/ComfyUI-XTTS/). The originally requested [`ZHO-ZHO-ZHO/ComfyUI-XTTS`](https://github.com/ZHO-ZHO-ZHO/ComfyUI-XTTS) URL returned `Repository not found`; GitHub search shows the public ComfyUI-XTTS repository as [`AIFSH/ComfyUI-XTTS`](https://github.com/AIFSH/ComfyUI-XTTS).

Do not install the ComfyUI-XTTS requirements into [`ComfyUI_windows_portable/python_embeded/`](ComfyUI_windows_portable/python_embeded/) yet: Coqui [`TTS==0.22.0`](xtts_api/requirements.txt:1) is a Python 3.10-era stack, while this portable ComfyUI uses Python 3.13. Installing the node's full requirements there would risk downgrading/replacing core ComfyUI packages. For the UI node, keep the cloned node in place and restart ComfyUI; if the node fails to import, use a Python 3.10 ComfyUI portable/build for XTTS or run XTTS through the isolated helper below.

The direct XTTS v2 smoke test is installed in an isolated environment at [`xtts_api/.venv/`](xtts_api/.venv/) using system Python 3.10, not system Python 3.14 and not ComfyUI's embedded Python. Recreate it with:

```bat
py -3.10 -m venv xtts_api\.venv
xtts_api\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
xtts_api\.venv\Scripts\python.exe -m pip install TTS==0.22.0 soundfile
xtts_api\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cu121 --upgrade torch==2.5.1 torchaudio==2.5.1
xtts_api\.venv\Scripts\python.exe -m pip install "transformers==4.40.2" "tokenizers<0.20,>=0.19"
```

Run the Russian XTTS v2 test:

```bat
xtts_api\generate_xtts_v2_ru.cmd
```

or directly:

```bat
set PYTHONUTF8=1&& xtts_api\.venv\Scripts\python.exe xtts_api\generate_xtts_v2_ru.py
```

The helper [`xtts_api/generate_xtts_v2_ru.py`](xtts_api/generate_xtts_v2_ru.py) uses [`fish_speech_api/reference_audio/female_ja_pozzhe_napishu.wav`](fish_speech_api/reference_audio/female_ja_pozzhe_napishu.wav) as a short female reference voice, `language="ru"`, and model [`tts_models/multilingual/multi-dataset/xtts_v2`](README.md). The first run downloads the CPML-licensed XTTS v2 model into the local Coqui cache under the user's profile without a Hugging Face token. The tested output is [`xtts_api/outputs/xtts_v2_ru_30s_test.wav`](xtts_api/outputs/xtts_v2_ru_30s_test.wav): mono, 24 kHz, `527664` frames, `21.986` seconds. Generation used CUDA on `NVIDIA GeForce RTX 3080 Ti Laptop GPU`, with processing time about `10.61` seconds and real-time factor about `0.44`.

### XTTS merged female voice-message reference and smoother joins

The reference-prep helper [`xtts_api/prepare_girl_voice_reference.py`](xtts_api/prepare_girl_voice_reference.py) downloads public MP3 media URLs from `https://zvukipro.com/razgovori/2410-zvuki-golosovogo-soobschenija-ot-devushki.html`, stores the page copy at [`xtts_api/reference_downloads_page.html`](xtts_api/reference_downloads_page.html), converts selected neutral female voice-message clips to 24 kHz mono WAV, trims only clip-edge silence, lightly peak-normalizes, and joins clips with short crossfades. It produced [`xtts_api/reference_audio/girl_voice_messages_merged.wav`](xtts_api/reference_audio/girl_voice_messages_merged.wav): mono, 24 kHz, `60.000` seconds, from `15` selected clips. Source URLs and processed clip paths are recorded in [`xtts_api/reference_audio/girl_voice_messages_merged.manifest.json`](xtts_api/reference_audio/girl_voice_messages_merged.manifest.json).

Run/refetch the reference build:

```bat
set PYTHONUTF8=1&& xtts_api\.venv\Scripts\python.exe xtts_api\prepare_girl_voice_reference.py
```

The smoother XTTS helper [`xtts_api/generate_xtts_v2_ru_merged_ref.py`](xtts_api/generate_xtts_v2_ru_merged_ref.py) uses the merged reference by default, sends the test text as one continuous block, disables Coqui sentence splitting when the installed API supports `split_sentences`, trims only leading/trailing output silence, shortens only excessive internal silent gaps over `0.45` seconds, and applies tiny edge fades plus peak normalization to reduce clicks/provалы between phrases.

Run the merged-reference smooth test:

```bat
xtts_api\generate_xtts_v2_ru_merged_ref.cmd
```

Current validated output is [`xtts_api/outputs/xtts_v2_ru_merged_ref_smooth_test.wav`](xtts_api/outputs/xtts_v2_ru_merged_ref_smooth_test.wav): mono, 24 kHz, `568192` frames, `23.675` seconds. XTTS warned that the default Russian text exceeds its `182`-character language limit; the file was still generated as one XTTS call. For production, keep each direct XTTS request near `20`-`30` seconds and avoid external per-phrase generation unless you add controlled crossfades/room tone after concatenation.

### XTTS v2 slow sleep-lecture tuning

The slow sleep-lecture helper [`xtts_api/generate_xtts_v2_ru_sleep_slow.py`](xtts_api/generate_xtts_v2_ru_sleep_slow.py) keeps XTTS v2 and the same merged reference, but avoids a single overlong request. It renders `4` medium chunks of `91`-`112` Russian characters, then stitches them with short crossfades and quiet synthetic room tone pauses. This is safer than putting SSML-like tags into the text because the installed Coqui XTTS path exposes sampling controls, `language`, `speaker_wav`, `split_sentences`, and `speed`, but no reliable SSML/tag/emotional-prompt parser for XTTS v2. Coqui's generic `emotion`/`speed` API docs are primarily for Coqui Studio models; the local XTTS v2 model accepts `speed` through model kwargs, while `emotion` is not a dependable XTTS v2 prosody control.

Run the slow sleep test:

```bat
xtts_api\generate_xtts_v2_ru_sleep_slow.cmd
```

Current validated output is [`xtts_api/outputs/xtts_v2_ru_sleep_slow_merged_ref_test.wav`](xtts_api/outputs/xtts_v2_ru_sleep_slow_merged_ref_test.wav): mono, 24 kHz, `842672` frames, `35.111` seconds. Generation settings were `language="ru"`, `split_sentences=false` per chunk, `temperature=0.62`, `top_p=0.78`, `top_k=35`, `repetition_penalty=7.0`, `length_penalty=1.0`, `speed=0.88`, `pause_sec=0.92`, and `crossfade_sec=0.045`. These settings aim for calmer, less random speech and longer sleep-lecture pauses. The helper also removes combining accent marks and XML/SSML-looking tags from input, prefers normal Russian punctuation and `ё`, trims only chunk-edge silence, avoids the previous aggressive internal silence compression, applies gentle fades, peak-normalizes to about `0.76`, and prints a simple adjacent-window repetition probe.

Recommended XTTS v2 Russian sleep settings: keep chunks below the warning range (roughly under `180` Russian characters per call), prefer punctuation/short sentences over literal tags, use `ё` where pronunciation matters, avoid combining stress marks unless you manually listen for artifacts, use `temperature` around `0.55`-`0.70`, `top_p` around `0.75`-`0.85`, `top_k` around `30`-`50`, `repetition_penalty` around `5`-`8`, `speed` around `0.85`-`0.95`, and add planned pauses externally. XTTS v2 can still make Russian stress errors and occasional short repetitions; these cannot be fully fixed without a different model or manual regeneration/editing of bad chunks.

Rights warning: use these downloaded voice references only when you have rights/permission for the voice and recordings, especially for publishing, distribution, or monetization.

### XTTS Natalia Shtin reference test

The user stated they have permission to use and process Natalia Shtin's voice for TTS/voice cloning. Based on that permission, the helper [`xtts_api/prepare_natalia_shtin_reference.py`](xtts_api/prepare_natalia_shtin_reference.py) downloads the public demo MP3 files from `https://audio-production.ru/baza-diktorov/top-woman-voices/nalia-shtin/`, converts them to 24 kHz mono WAV, trims clip-edge silence, applies conservative normalization/fades, and concatenates them with short crossfades.

Prepare or refresh this reference:

```bat
set PYTHONUTF8=1&& xtts_api\.venv\Scripts\python.exe xtts_api\prepare_natalia_shtin_reference.py
```

Generated reference:

- [`xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.wav`](xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.wav): mono, 24 kHz, `90.000` seconds.
- [`xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.manifest.json`](xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.manifest.json): source URLs, processed clip paths, and processing notes.

Generate the XTTS v2 sleep-slow test with this reference:

```bat
xtts_api\generate_xtts_v2_ru_natalia_shtin.cmd
```

Equivalent direct command:

```bat
set PYTHONUTF8=1&& xtts_api\.venv\Scripts\python.exe xtts_api\generate_xtts_v2_ru_sleep_slow.py --reference xtts_api\reference_audio\natalia_shtin\natalia_shtin_clean_reference.wav --output xtts_api\outputs\xtts_v2_ru_natalia_shtin_sleep_slow_test.wav --temperature 0.58 --top-p 0.74 --top-k 30 --repetition-penalty 6.5 --speed 0.88 --pause 0.95 --crossfade 0.055
```

Validated output:

- [`xtts_api/outputs/xtts_v2_ru_natalia_shtin_sleep_slow_test.wav`](xtts_api/outputs/xtts_v2_ru_natalia_shtin_sleep_slow_test.wav): mono, 24 kHz, `835712` frames, `34.821` seconds.
- Per-chunk WAV files are written to [`xtts_api/outputs/_sleep_slow_chunks/`](xtts_api/outputs/_sleep_slow_chunks/).
- Settings: `temperature=0.58`, `top_p=0.74`, `top_k=30`, `repetition_penalty=6.5`, `speed=0.88`, `pause_sec=0.95`, `crossfade_sec=0.055`.

The script does not perform aggressive music separation. It uses conservative trimming/normalization because heavy source-separation artifacts can make XTTS voice conditioning worse. If the demo contains audible music under the voice, the best next step is to obtain a clean dry recording from the rights holder; otherwise use an external stem-separation tool manually and listen for artifacts before using the result as a reference.

### XTTS Studio local browser UI

[`xtts_api/studio_server.py`](xtts_api/studio_server.py) implements a minimal local-only FastAPI browser app for the XTTS chunk workflow. It stores the single default project in [`xtts_api/studio_projects/default_project.json`](xtts_api/studio_projects/default_project.json), serves the plain frontend from [`xtts_api/studio_static/index.html`](xtts_api/studio_static/index.html), and writes generated chunks/final exports under [`xtts_api/studio_projects/outputs/`](xtts_api/studio_projects/outputs/). The default reference is [`xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.wav`](xtts_api/reference_audio/natalia_shtin/natalia_shtin_clean_reference.wav).

Install/refresh the extra server dependencies in the existing XTTS environment if needed:

```bat
xtts_api\.venv\Scripts\python.exe -m pip install fastapi==0.115.6 uvicorn[standard]==0.34.0 python-multipart==0.0.20
```

Launch the studio:

```bat
xtts_api\run_xtts_studio.cmd
```

Open [`http://127.0.0.1:7870/studio/`](README.md). The server binds only to `127.0.0.1` and does not touch Silero, Fish Speech, or ComfyUI.

Current UI/API capabilities:

- full-text textarea and `Split into chunks` with paragraph/sentence chunking around `190` characters by default;
- chunk list/timeline with editable chunk text, per-chunk generate/regenerate, audio preview, duration, start time, `pause_before`, `pause_after`, and up/down reordering;
- simple draggable timeline blocks: horizontal drag changes `pause_before` for that chunk;
- reference WAV path field, defaulting to the Natalia Shtin clean reference;
- optional music path or upload, separate voice/music volume sliders;
- lazy singleton XTTS v2 model loading on the first generation request, then reused in memory while the server is running;
- final WAV export with chunk pauses/room tone/crossfades, optional background music mix, clipping-safe normalization, and browser download link.

Useful endpoints exposed by [`xtts_api/studio_server.py`](xtts_api/studio_server.py): [`GET /api/health`](xtts_api/studio_server.py:456), [`GET /api/project`](xtts_api/studio_server.py:462), [`POST /api/chunks/split`](xtts_api/studio_server.py:489), [`POST /api/chunks/{chunk_id}/generate`](xtts_api/studio_server.py:561), [`POST /api/chunks/generate-all`](xtts_api/studio_server.py:581), and [`POST /api/export`](xtts_api/studio_server.py:593).

Smoke tests performed: Python syntax compilation for [`xtts_api/studio_server.py`](xtts_api/studio_server.py), FastAPI `TestClient` health/static/split checks, and export using the existing generated file [`xtts_api/outputs/xtts_v2_ru_natalia_shtin_sleep_slow_test.wav`](xtts_api/outputs/xtts_v2_ru_natalia_shtin_sleep_slow_test.wav) as a chunk source. A fresh XTTS generation from the UI will load the model on first use and can take a while.

For ComfyUI usage after restart, add the `AIFSH_XTTS` nodes from ComfyUI-XTTS, load a reference WAV through the node's audio loader, set language to `ru`, enter Russian text, and preview/save the returned audio path. If using the current Python 3.13 portable, expect import/dependency incompatibility until ComfyUI-XTTS is run under a Python 3.10-compatible ComfyUI environment.

## Silero TTS/RU through ComfyUI

Silero RU is installed in a separate project environment, [` .venv-silero/`](.venv-silero/), so it does not modify the Fish/OpenAudio runtime. It uses official [`torch.hub`](README.md) loading from [`snakers4/silero-models`](https://github.com/snakers4/silero-models) with language `ru` and model `v4_ru`.

Create or refresh the environment from this workspace:

```bat
"C:\Users\valpe\AppData\Local\Programs\Python\Python310\python.exe" -m venv .venv-silero
.venv-silero\Scripts\python.exe -m pip install --upgrade pip
.venv-silero\Scripts\python.exe -m pip install -r silero_tts_api\requirements.txt
```

Generate the quick Russian soft-female test without ComfyUI:

```bat
silero_tts_api\generate_silero_ru_30s.cmd
```

Generate the sleep-safe realistic version with phrase pauses, room tone, subtle chunk loudness changes, fades, and mastering:

```bat
silero_tts_api\generate_silero_ru_realistic_30s.cmd
```

Generate the softer bedtime version with slower Silero pacing, lower peak, softer upper frequencies, very quiet room tone, no breaths, chunk fades, and conservative soft compression:

```bat
silero_tts_api\generate_silero_ru_sleep_soft_30s.cmd
```

Current validated output:

- [`silero_tts_api/outputs/silero_ru_30s_soft_female_test.wav`](silero_tts_api/outputs/silero_ru_30s_soft_female_test.wav)
- [`silero_tts_api/outputs/silero_ru_30s_soft_female_test.manifest.json`](silero_tts_api/outputs/silero_ru_30s_soft_female_test.manifest.json)
- [`silero_tts_api/outputs/silero_ru_30s_realistic_sleep_safe_baya.wav`](silero_tts_api/outputs/silero_ru_30s_realistic_sleep_safe_baya.wav)
- [`silero_tts_api/outputs/silero_ru_30s_realistic_sleep_safe_baya.manifest.json`](silero_tts_api/outputs/silero_ru_30s_realistic_sleep_safe_baya.manifest.json)
- [`silero_tts_api/outputs/silero_ru_30s_sleep_soft_baya.wav`](silero_tts_api/outputs/silero_ru_30s_sleep_soft_baya.wav)
- [`silero_tts_api/outputs/silero_ru_30s_sleep_soft_baya.manifest.json`](silero_tts_api/outputs/silero_ru_30s_sleep_soft_baya.manifest.json)

Validation summary: speaker `baya`, model `v4_ru`, CPU device, 48 kHz mono WAV, duration `29.600` seconds, generation time `2.349` seconds, speed `12.601x`, RMS `0.122754`, peak `0.880005`, file size `2,841,644` bytes. Available Silero RU speakers reported by the model are `aidar`, `baya`, `kseniya`, `xenia`, `eugene`, and `random`; `baya` is used as the default soft female voice.

Realistic sleep-safe validation: speaker `baya`, model `v4_ru`, CPU device, 48 kHz mono WAV, duration `31.735` seconds, generation time `4.535` seconds, speed `6.998x`, RMS `0.134608`, peak `0.859955`, file size `3,046,604` bytes. The manifest records `10` rendered chunks, `9` seeded pause events, `2.610` seconds of pause/room-tone bed, `0` breaths, preset `sleep_safe`, `pause_scale=0.82`, `breath_amount=0.0`, `room_tone=true`, and `loudness_variation_db=0.18`.

Soft sleep validation: speaker `baya`, model `v4_ru`, CPU device, 48 kHz mono WAV, duration `32.087` seconds, generation time `4.657` seconds, speed `6.889x`, RMS `0.114987`, peak `0.593719`, file size `3,080,396` bytes. The manifest records `10` rendered chunks, `9` seeded pause events, `2.962` seconds of pause/very quiet room-tone bed, `0` breaths, preset `sleep_soft`, `speed=0.90`, `pause_scale=0.90`, `breath_amount=0.0`, `room_tone=true`, `room_tone_level=0.62`, `loudness_variation_db=0.11`, `target_peak=0.76`, `soften=true`, `tone_softening=0.34`, `sleep_softness=0.55`, and `chunk_fade_ms=18`.

Start the Silero API for ComfyUI:

```bat
silero_tts_api\run_server.cmd
```

The API runs at [`http://127.0.0.1:7866`](README.md) and exposes:

- [`GET /health`](silero_tts_api/server.py:28)
- [`GET /v1/speakers`](silero_tts_api/server.py:40)
- [`POST /v1/tts`](silero_tts_api/server.py:45)

`POST /v1/tts` remains backward-compatible. Optional Silero realism fields are `realism_enabled`, `preset`, `pause_scale`, `breath_amount`, `room_tone`, `loudness_variation`, `seed`, `speed`, `soften`, `target_peak`, `tone_softening`, and `sleep_softness`. Presets are `sleep_soft`, `sleep_safe`, `natural_lecture`, and `experimental_realism`; `sleep_safe` keeps the previous conservative behavior, while `sleep_soft` is recommended for soothing bedtime speech.

Recommended ComfyUI/API settings for a softer, less neural Silero RU bedtime voice: `realism_enabled=true`, `speaker=baya`, `preset=sleep_soft`, `speed=0.90`, `pause_scale=0.90`, `breath_amount=0.0`, `room_tone=true`, `loudness_variation=0.11`, `soften=true`, `target_peak=0.76`, `tone_softening=0.34`, and `sleep_softness=0.55`. Keep `tone_softening` in the `0.25`-`0.40` range to soften sibilance without making the voice muffled.

Install the ComfyUI custom node without recursively touching the portable bundle:

```bat
mkdir ComfyUI_windows_portable\ComfyUI\custom_nodes\comfyui-silero-tts-api
copy comfyui_silero_tts_bridge\silero_tts_api_node.py ComfyUI_windows_portable\ComfyUI\custom_nodes\comfyui-silero-tts-api\__init__.py
```

The node is already copied to [`ComfyUI_windows_portable/ComfyUI/custom_nodes/comfyui-silero-tts-api/__init__.py`](ComfyUI_windows_portable/ComfyUI/custom_nodes/comfyui-silero-tts-api/__init__.py). Restart ComfyUI and add [`Silero RU TTS API`](comfyui_silero_tts_bridge/silero_tts_api_node.py:9) from category `audio/silero-tts`. The node accepts text, speaker/voice, sample rate, and output path, then calls [`http://127.0.0.1:7866/v1/tts`](README.md). A direct API smoke test produced [`silero_tts_api/outputs/comfyui_bridge_smoke_test.wav`](silero_tts_api/outputs/comfyui_bridge_smoke_test.wav) through the same endpoint the ComfyUI node uses.

## Install API dependencies

From this workspace in [`cmd.exe`](README.md):

```bat
cd fish_speech_api
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy config.example.json config.json
```

The pure-Python placeholder workflow itself uses the standard library. The HTTP API additionally needs [`fastapi`](fish_speech_api/requirements.txt:1), [`uvicorn`](fish_speech_api/requirements.txt:2), [`pydantic`](fish_speech_api/requirements.txt:3), and [`requests`](fish_speech_api/requirements.txt:4).

## Generate the test audio without starting a server

```bat
python fish_speech_api\audio_workflow.py --output fish_speech_api\outputs\russian_sleep_lecture_placeholder_test.wav
```

or:

```bat
fish_speech_api\generate_test_audio.cmd
```

Expected output files:

- [`fish_speech_api/outputs/russian_sleep_lecture_placeholder_test.wav`](fish_speech_api/outputs/russian_sleep_lecture_placeholder_test.wav) — generated placeholder test audio.
- [`fish_speech_api/outputs/russian_sleep_lecture_placeholder_test.manifest.json`](fish_speech_api/outputs/russian_sleep_lecture_placeholder_test.manifest.json) — chunk/prosody manifest.
- [`fish_speech_api/outputs/russian_sleep_lecture_placeholder_test.mp3`](fish_speech_api/outputs/russian_sleep_lecture_placeholder_test.mp3) — created only when [`ffmpeg`](https://ffmpeg.org/) is available in [`PATH`](README.md).

Useful CLI parameters:

```bat
python fish_speech_api\audio_workflow.py --text-file fish_speech_api\sample_russian_sleep_lecture.txt --output fish_speech_api\outputs\custom.wav --seed 123 --max-chars 360 --no-mp3
```

Realism parameters are sleep-safe by default and are intentionally subtle: text-aware micro pauses, low-level room tone, very rare/procedural breaths, per-chunk loudness variation, and smooth pitch drift capped at ±1%.

```bat
python fish_speech_api\audio_workflow.py --config fish_speech_api\config.json --preset natural_lecture --breath-amount 0.08 --pitch-drift 0.45 --loudness-variation 0.65 --room-tone on --output fish_speech_api\outputs\realistic.wav --no-mp3
```

## Start the local API

```bat
fish_speech_api\run_server.cmd
```

or manually:

```bat
cd fish_speech_api
.venv\Scripts\activate
python -m uvicorn server:app --host 127.0.0.1 --port 7865
```

Endpoints:

- [`GET /health`](fish_speech_api/server.py:76)
- [`POST /v1/tts`](fish_speech_api/server.py:85) — existing short synthesis endpoint, kept compatible.
- [`POST /v1/long-form`](fish_speech_api/server.py:125) — long-form cleaner/chunker/concat/mastering endpoint.
- Long-form accepts optional safe realism fields: `preset`, `breath_amount`, `room_tone`, `pitch_drift`, and `loudness_variation`.

## Test API calls

Short endpoint:

```bat
cd fish_speech_api
.venv\Scripts\activate
python client_example.py --text "Пример локального синтеза речи на русском."
```

Long-form endpoint through curl:

```bat
curl -X POST http://127.0.0.1:7865/v1/long-form -H "Content-Type: application/json" -d "{\"text\":\"Добрый вечер. Это тест длинного русского текста. Паузы и фон комнаты будут добавлены автоматически.\",\"language\":\"ru\",\"seed\":42,\"max_chars\":420,\"export_mp3\":true}"
```

Generated files are written to [`fish_speech_api/outputs/`](fish_speech_api/outputs/).

## Connect to ComfyUI

Safe default: keep ComfyUI unchanged and use any generic HTTP/request node to call [`http://127.0.0.1:7865/v1/tts`](README.md) or [`http://127.0.0.1:7865/v1/long-form`](README.md).

Optional custom node:

1. Create [`ComfyUI_windows_portable/ComfyUI/custom_nodes/comfyui-fish-speech-api/`](ComfyUI_windows_portable/ComfyUI/custom_nodes/comfyui-fish-speech-api/).
2. Copy [`comfyui_fish_speech_bridge/fish_speech_api_node.py`](comfyui_fish_speech_bridge/fish_speech_api_node.py) into that folder.
3. Restart ComfyUI.
4. Add [`Fish Speech API TTS`](comfyui_fish_speech_bridge/fish_speech_api_node.py:9).
5. Enable [`long_form`](comfyui_fish_speech_bridge/fish_speech_api_node.py:19) in the node when you want the full workflow instead of one direct segment.
6. For long-form realism, use the node's optional `preset`, `breath_amount`, `room_tone`, `pitch_drift`, `loudness_variation`, and `seed` inputs. These are ignored by the short endpoint to preserve backwards compatibility.

## OpenAudio S1 Mini real runtime status

OpenAudio S1 Mini has a dedicated compatible runtime separate from the earlier test runtime and from ComfyUI:

- Runtime path: `C:\openaudio_s1mini_runtime\Fish-Speech`.
- Runtime revision: upstream Fish Speech commit `9e11f46921ca0b4dbfec1b86dfa3177c5a7f4798` (`Update samples for openaudio-s1-mini (WIP)`). This is after the official OpenAudio S1 support commits `9735644` and `89474bb`.
- Python environment: `C:\openaudio_s1mini_runtime\venv` using [`Python 3.10`](README.md), [`torch==2.5.1+cu121`](README.md), and [`torchaudio==2.5.1+cu121`](README.md).
- Model checkpoint: `C:\openaudio_s1mini_runtime\Fish-Speech\checkpoints\openaudio-s1-mini`, copied from the local [`1/`](1/) snapshot. It contains [`model.pth`](1/model.pth), [`codec.pth`](1/codec.pth), [`config.json`](1/config.json), [`tokenizer.tiktoken`](1/tokenizer.tiktoken), and [`special_tokens.json`](1/special_tokens.json).
- Official inference flow confirmed from `C:\openaudio_s1mini_runtime\Fish-Speech\docs\en\inference.md`: generate semantic codes with `fish_speech/models/text2semantic/inference.py`, then decode [`codes_0.npy`](README.md) with `fish_speech/models/dac/inference.py` using [`modded_dac_vq`](README.md).

The most likely previous failure source was a runtime/model mismatch: the older/current workflow called the text2semantic CLI as if it wrote final WAV directly, and the observed `semantic:0` / `<|im_end|>` collapse produced noise. The compatible revision now generates non-collapsed S1 Mini semantic codes and decodes them through the S1 Mini DAC.

The adapter supports [`backend: fish_speech_cli`](fish_speech_api/config.json:5) and now runs the official two-step S1 Mini CLI from [`FishSpeechBackend._synthesize_with_fish_speech_cli()`](fish_speech_api/fish_backend.py:50). [`fish_speech_api/config.json`](fish_speech_api/config.json) points at the new runtime and disables placeholder fallback.

Short direct validation produced real speech at [`fish_speech_api/outputs/s1mini_official_short_test.wav`](fish_speech_api/outputs/s1mini_official_short_test.wav). The user confirmed it is speech, though quality is low.

Generate the longer S1 Mini Russian test with:

```bat
fish_speech_api\generate_s1mini_1min.cmd
```

or directly:

```bat
C:\openaudio_s1mini_runtime\venv\Scripts\python.exe fish_speech_api\audio_workflow.py --config fish_speech_api\config.json --text-file fish_speech_api\sample_russian_sleep_lecture.txt --output fish_speech_api\outputs\s1mini_russian_1min_real_test.wav --max-chars 220 --no-mp3
```

Current real-generation output: [`fish_speech_api/outputs/s1mini_russian_1min_real_test.wav`](fish_speech_api/outputs/s1mini_russian_1min_real_test.wav), manifest [`fish_speech_api/outputs/s1mini_russian_1min_real_test.manifest.json`](fish_speech_api/outputs/s1mini_russian_1min_real_test.manifest.json), backend `fish_speech_cli`, 12 chunks, duration `122.887` seconds, 24 kHz mono WAV. This is real S1 Mini speech, not placeholder audio.

Generate a more realistic zero-shot S1 Mini test with the sleep-safe realism layer:

```bat
fish_speech_api\generate_s1mini_realistic_1min.cmd
```

Equivalent direct command:

```bat
C:\openaudio_s1mini_runtime\venv\Scripts\python.exe fish_speech_api\audio_workflow.py --config fish_speech_api\config.json --text-file fish_speech_api\sample_russian_sleep_lecture.txt --output fish_speech_api\outputs\s1mini_russian_1min_realistic_zeroshot.wav --max-chars 220 --preset sleep_safe --breath-amount 0.04 --pitch-drift 0.35 --loudness-variation 0.35 --room-tone on --no-mp3
```

Current realistic output: [`fish_speech_api/outputs/s1mini_russian_1min_realistic_zeroshot.wav`](fish_speech_api/outputs/s1mini_russian_1min_realistic_zeroshot.wav), manifest [`fish_speech_api/outputs/s1mini_russian_1min_realistic_zeroshot.manifest.json`](fish_speech_api/outputs/s1mini_russian_1min_realistic_zeroshot.manifest.json), backend `fish_speech_cli`, 15 chunks, duration `123.483` seconds, 24 kHz mono WAV. This run was started before the helper script was switched back to `sleep_safe`, so its manifest records `natural_lecture` with overrides (`breath_amount=0.08`, `pitch_drift_percent=0.45`, `loudness_variation_db=0.65`, `room_tone=true`). The current helper script now uses the more conservative `sleep_safe` settings shown above.

Fast 30-second S1 Mini stabilization test:

```bat
fish_speech_api\generate_s1mini_fast_30s.cmd
```

This uses [`fish_speech_api/short_s1mini_ru_soft_female_30s.txt`](fish_speech_api/short_s1mini_ru_soft_female_30s.txt), targets [`fish_speech_api/outputs/s1mini_russian_30s_soft_female_fast_test.wav`](fish_speech_api/outputs/s1mini_russian_30s_soft_female_fast_test.wav), and is configured for speed/consistency: `--max-chars 900` for 1-3 chunks, `--fixed-chunk-seed`, `temperature=0.55`, `top_p=0.65`, `max_new_tokens=768`, `chunk_length=420`, no MP3, soft room tone, light loudness variation, very light breath layer, and no pitch drift. The test uses downloaded female reference audio [`fish_speech_api/reference_audio/female_ja_pozzhe_napishu.wav`](fish_speech_api/reference_audio/female_ja_pozzhe_napishu.wav) with transcript `Ну, короче, я сейчас немного занята, я позже напишу.`; the source MP3 was converted locally to 24 kHz mono WAV with [`torchaudio`](README.md). The installed OpenAudio S1 Mini CLI accepts `--seed`, `--prompt-text`, `--prompt-audio`, `--prompt-tokens`, `--max-new-tokens`, `--temperature`, `--top-p`, `--compile/--no-compile`, `--half/--no-half`, `--iterative-prompt/--no-iterative-prompt`, and `--chunk-length`; this local revision does not expose a usable `--top-k` option, so the adapter does not pass it. The configured `voice_prompt` is stored in the manifest as style metadata; it is not prepended to spoken text by default because a plain text style instruction can be read aloud.

Current referenced fast output: [`fish_speech_api/outputs/s1mini_russian_30s_soft_female_fast_test.wav`](fish_speech_api/outputs/s1mini_russian_30s_soft_female_fast_test.wav), manifest [`fish_speech_api/outputs/s1mini_russian_30s_soft_female_fast_test.manifest.json`](fish_speech_api/outputs/s1mini_russian_30s_soft_female_fast_test.manifest.json), backend `fish_speech_cli`, 2 chunks, duration `28.742` seconds, 24 kHz mono WAV, reference audio enabled.

For Russian pronunciation, [`clean_russian_text()`](fish_speech_api/audio_workflow.py:96) now expands common Russian abbreviations such as `т.е.`, `т.к.`, `и т.д.`, `и т.п.`, `напр.`, `см.`, `стр.`, handles `№`, verbalizes `%` as `процентов`, and adds stress marks for several words used in the 30-second test (`вы́дох`, `вы́дохом`, `ровне́е`, `пле́чи`, `вече́рний`, `ко́мнату`, `слу́шать`, `напряже́ние`, `сле́дующим`).

Reference audio support is available when both `reference_audio` and `reference_text` are set in [`fish_speech_api/config.json`](fish_speech_api/config.json) or passed on the CLI/API. The inspected S1 Mini text2semantic CLI exposes `--prompt-text` and `--prompt-tokens`; this workflow encodes a supplied reference WAV into prompt tokens through the official DAC CLI, then passes those prompt tokens to text2semantic. Put a real 5-10 second clean reference WAV and its exact transcript in paths you control, then set `fish_speech.reference_audio` and `fish_speech.reference_text`. If either field is absent, generation remains zero-shot. Do not expect studio quality from zero-shot S1 Mini; the realism layer improves pacing/texture but cannot replace a good reference voice.

S2-Pro remains excluded for this target because the official docs recommend at least 24GB VRAM and this machine exposes an NVIDIA GeForce RTX 3080 Ti Laptop GPU with 16GB-class VRAM.

## Wiring real Fish Speech later

Python was previously detected as [`Python 3.14.2`](README.md). Many ML/TTS packages lag behind new Python releases, so real Fish Speech should be installed in a separate [`Python 3.10`](README.md) or [`Python 3.11`](README.md) environment unless the official Fish Speech documentation explicitly supports [`Python 3.14`](README.md).

Recommended next steps:

1. Create a separate Fish Speech environment outside the ComfyUI portable bundle.
2. Follow the official Fish Speech repository instructions for the exact supported Python, PyTorch/CUDA build, and checkpoint download commands.
3. Update [`fish_speech_api/config.json`](fish_speech_api/config.example.json): set [`backend`](fish_speech_api/config.example.json:5) to a real adapter name and fill [`fish_speech.repo_dir`](fish_speech_api/config.example.json:7), [`fish_speech.checkpoint_dir`](fish_speech_api/config.example.json:8), and [`fish_speech.device`](fish_speech_api/config.example.json:9).
4. Replace the adapter internals in [`FishSpeechBackend.synthesize()`](fish_speech_api/fish_backend.py:35) while keeping its input/output contract unchanged.

For long-form Russian TTS, keep Fish Speech as a separate API process. This avoids loading heavy TTS dependencies into ComfyUI and makes failures easier to isolate.

