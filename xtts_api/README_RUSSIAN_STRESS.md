# Russian stress and pronunciation notes

XTTS Studio still uses Coqui XTTS v2 (`tts_models/multilingual/multi-dataset/xtts_v2`) by default, but the Studio chunk generator can now also call the local Silero RU API for stricter stress control. XTTS voice cloning is convenient, but it may ignore Russian acute stress marks. Silero RU is the practical stress-aware path because it accepts Silero-style `+` stress notation.

## What can and cannot fix stress

- Russian word stress is best corrected before synthesis, in text normalization or with a pronunciation dictionary.
- A ComfyUI custom node after audio generation cannot reliably move stress inside an already spoken word. That would require speech recognition, phoneme alignment, editing, and usually re-synthesis.
- General post-processing such as EQ, compression, pauses, room tone, and normalization can improve polish, but it cannot reliably change `за́мок` into `замо́к` after the waveform has been generated.

## Implemented low-risk preprocessing

The project now supports an optional dictionary file:

```text
xtts_api/pronunciation_dictionary.json
```

If the file is absent, generation continues normally. Use `xtts_api/pronunciation_dictionary.example.json` as a starting point and copy it to `xtts_api/pronunciation_dictionary.json`.

Example:

```json
{
  "замок": "за́мок",
  "мука": "му́ка",
  "плечи": "пле́чи"
}
```

You can also type stress directly in chunk text:

```text
за́мок
зам+ок
```

The `+` form is converted before synthesis. For XTTS Studio the default output style is combining acute accent (`́`). XTTS v2 may ignore the mark; it is still safer than passing a literal plus sign that could be spoken as punctuation. When `tts_backend=silero` and `tts_stress_mark_style=auto`, Studio converts acute stress to Silero-style plus notation before the vowel.

## Settings

The new optional project settings are:

```text
tts_pronunciation_preprocess_enabled=true
tts_pronunciation_dictionary_path=xtts_api/pronunciation_dictionary.json
tts_stress_mark_style=acute
tts_backend=xtts
silero_api_url=http://127.0.0.1:7866
silero_speaker=baya
silero_sample_rate=48000
silero_realism_enabled=true
silero_realism_preset=sleep_safe
ai_add_russian_stress_marks=false
ai_stress_model=
ai_stress_batch_chunks=2
ai_stress_max_request_chars=2500
ai_stress_retries=2
```

Use the Studio UI section **TTS backend / Russian stress control** to switch between `xtts` and `silero`. Keep `xtts` for voice-cloned output and existing projects. Choose `silero` when stress accuracy is more important than XTTS voice cloning; start `silero_tts_api/server.py` first so `http://127.0.0.1:7866/v1/tts` is available.

For Silero, use `tts_stress_mark_style=auto` or `plus`. For XTTS, prefer `acute` or `plain`; XTTS may ignore `за́мок`, but passing raw `зам+ок` to XTTS is not recommended. For Fish Speech, the shared dictionary is applied when the higher-level workflow text cleaner runs, but exact stress support depends on the installed Fish Speech model and tokenizer.

## Optional Grok/xAI stress post-processing after chunking

The checkbox **After standard split, use Grok to add Russian stress marks to existing chunks** enables `ai_add_russian_stress_marks`. This is a strict two-phase process in `/api/chunks/split`:

1. Studio runs the standard/default chunk splitter exactly as it does without Grok. This creates the final chunk list, ids, order, boundary types, timing fields, and pauses.
2. Only after that, Studio sends small batches of those already-created chunk ids and texts to Grok/xAI and asks for the same text with combining acute marks on every Russian word where stress is known or can be reasonably inferred.

Grok is never asked to split the source text and never receives authority over chunk boundaries, count, order, ids, pauses, or timing. Its output is accepted per chunk only when removing combining acute marks from the returned text produces the original chunk text. Any rewrite, omission, invented id, merge, split, or reordered coverage is ignored/falls back to the original chunk text.

Example stress-only transformation inside one already-created chunk:

```text
замок на холме → за́мок на холме́
мука на столе → мука́ на столе́
```

The original chunk text remains in `text`. Grok-marked text is stored in both `stressed_text` and `tts_text`, and TTS generation uses `tts_text` when present. This preserves old project compatibility: older chunks with only `text` still generate normally, and manual edits to a chunk clear stale `tts_text`/`stressed_text` so regenerated audio follows the edited text.

Grok stress post-processing is deliberately split into small requests to avoid losing later chunks when the model runs out of output room. By default Studio sends only 2 chunks per request, hard-caps configured batch size to at most 3 chunks, caps each request around 2500 JSON/text characters, asks Grok for a compact JSON array with only `id` and `stressed_text`, and sends long chunks by themselves. If a batch fails or Grok returns only part of the requested ids, Studio retries the missing chunks individually before falling back to originals. `ai_stress_retries=2` means each batch or individual fallback can be attempted up to three times total for transient xAI errors.

Grok stress marking is deliberately fallback-safe:

- default is `false`, so existing chunking behavior is unchanged;
- if no xAI key is configured, chunking continues with original text;
- if Grok fails or omits a chunk, Studio retries smaller/per-chunk requests and then keeps original text for unresolved chunks;
- responses that rewrite content instead of only adding acute marks are rejected per chunk.
- abbreviations, numbers, symbols, foreign words, and genuinely uncertain words may remain unmarked.

After splitting, project status starts with `Standard split into N chunks` and, when enabled, appends Grok post-processing coverage details: marked chunks, total chunks, small-batch count, configured batch/character caps, unchanged/skipped chunks, rejected chunks, how many chunks were retried individually, failed batch count, error count, and the Grok model used. Existing chunks are not automatically reprocessed; resplit the text or rerun stress marking after changing these settings.

Configure the key in the Grok/xAI API key field or with `XAI_API_KEY`. `ai_stress_model` can override the default model; leave it empty to use the same current/default Grok text model resolution as AI grouping (`XAI_MODEL`, otherwise `grok-3-mini`). The server always resolves a non-empty model before sending the optional stress request; a model/config error is reported in project status and chunking keeps the original text instead of failing.

## Recommended workflow

1. Listen for recurring mistakes.
2. Add the word or phrase to `xtts_api/pronunciation_dictionary.json`.
3. Optionally enable Grok stress post-processing before splitting long Russian text; Studio will split normally first, then mark stress on the resulting chunks. Review and edit the resulting stressed chunks.
4. For stricter Russian stress control, switch TTS backend to Silero and use `auto`/`plus` stress style.
5. Regenerate only the affected chunks.
6. If XTTS ignores the stress mark for a specific word, use Silero for that chunk/project, a wording workaround, or test Fish Speech for that sentence.
7. For high-value problematic words, keep manual alternate phrasing in the chunk text.

Remaining limitation: Grok can make stress mistakes, and preprocessing can only give the TTS backend better input. Guaranteed stress correction requires a backend that respects the selected stress notation; in this project, Silero RU plus notation is the safest available path.
