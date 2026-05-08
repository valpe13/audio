# ComfyUI Fish Speech bridge

This folder is intentionally outside `ComfyUI_windows_portable/`.

## Option A: manual custom node copy

1. Keep the Fish Speech API running from `fish_speech_api/`.
2. Copy `fish_speech_api_node.py` into a ComfyUI custom-node folder, for example:
   `ComfyUI_windows_portable/ComfyUI/custom_nodes/comfyui-fish-speech-api/`.
3. Restart ComfyUI.
4. Add the node named `Fish Speech API TTS`.
5. Set `long_form` to `true` to call `/v1/long-form`; leave it `false` for the original `/v1/tts` short endpoint.
6. Optional long-form realism inputs are exposed as safe controls: `preset`, `breath_amount`, `room_tone`, `pitch_drift`, `loudness_variation`, and `seed`. The default `sleep_safe` preset keeps breaths rare/subtle and caps pitch drift below ±1%.

Do not copy this automatically unless you are comfortable modifying the portable ComfyUI bundle.

## Option B: generic HTTP node

Use any ComfyUI HTTP/request node to POST JSON to:

```text
http://127.0.0.1:7865/v1/tts
```

Example body:

```json
{
  "text": "Пример длинного русского текста для озвучивания.",
  "language": "ru",
  "temperature": 0.7,
  "top_p": 0.7
}
```

The response contains `audio_path`, which points to the generated WAV file.

For the full long-form workflow, POST to:

```text
http://127.0.0.1:7865/v1/long-form
```

Example body:

```json
{
  "text": "Добрый вечер. Это длинный русский текст для проверки пауз, фона комнаты и мастеринга.",
  "language": "ru",
  "seed": 42,
  "max_chars": 420,
  "preset": "sleep_safe",
  "breath_amount": 0.04,
  "room_tone": true,
  "pitch_drift": 0.35,
  "loudness_variation": 0.35,
  "export_mp3": true
}
```

The long-form response contains `output_wav`, optional `output_mp3`, and a manifest path.

Reference audio can be passed with `reference_audio` and `reference_text` when a clean local WAV and exact transcript are available. If those fields are empty, the API uses zero-shot S1 Mini plus the realism layer only.

