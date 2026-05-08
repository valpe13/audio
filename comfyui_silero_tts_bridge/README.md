# ComfyUI Silero RU TTS bridge

This custom node calls the local Silero RU API at `http://127.0.0.1:7866/v1/tts` and returns the generated WAV path plus JSON metadata.

## Install into ComfyUI

```bat
mkdir ComfyUI_windows_portable\ComfyUI\custom_nodes\comfyui-silero-tts-api
copy comfyui_silero_tts_bridge\silero_tts_api_node.py ComfyUI_windows_portable\ComfyUI\custom_nodes\comfyui-silero-tts-api\__init__.py
```

Restart ComfyUI and add the node `Silero RU TTS API` from `audio/silero-tts`.

## Start the API before using the node

```bat
silero_tts_api\run_server.cmd
```

The soft female default is speaker `baya`. Other RU speakers exposed by the node are `kseniya`, `xenia`, `aidar`, `eugene`, and `random`.

## Realism controls

The node preserves the old direct call when `realism_enabled` is off. Enable `realism_enabled` to ask the API to split text into phrases, render Silero chunks, then add seed-stable pauses, low room tone, subtle per-phrase loudness variation, fades, optional softening, and peak normalization.

Soft sleep starting values for a slower, less neural, more lulling `baya` voice:

- `realism_enabled`: enabled
- `preset`: `sleep_soft`
- `speed`: `0.90`
- `pause_scale`: `0.90`
- `breath_amount`: `0.0`
- `room_tone`: enabled
- `loudness_variation`: `0.11`
- `soften`: enabled
- `target_peak`: `0.76`
- `tone_softening`: `0.34`
- `sleep_softness`: `0.55`
- `seed`: any fixed integer for repeatable pause jitter

Legacy sleep-safe starting values:

- `preset`: `sleep_safe`
- `pause_scale`: `0.82`
- `breath_amount`: `0.0` to `0.03`
- `room_tone`: enabled
- `loudness_variation`: `0.18`
- `seed`: any fixed integer for repeatable pause jitter

Other presets are `natural_lecture` and `experimental_realism`. For bedtime audio, keep breaths near zero and keep `tone_softening` conservative, roughly `0.25`-`0.40`, so the voice becomes softer without sounding muffled.

