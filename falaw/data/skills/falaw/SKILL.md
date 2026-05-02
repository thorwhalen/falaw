---
name: falaw
description: >-
  Generate and manage AI media (images, video, audio) via fal.ai. Use this
  skill whenever the user wants to generate, edit, upscale, or compose media,
  or asks about fal.ai or fal-client. The skill exposes Python tools that
  wrap fal-client with smart model selection, result handling, and a journal
  for self-improvement across sessions.
---

# falaw

Use the `falaw` Python package as your primary interface to fal.ai.

## Read the journal first

Before doing anything novel, glance at recent journal entries --- past
sessions may have left notes, gotchas, or suggestions that save you time:

```python
from falaw import journal
for e in journal.recent(20):
    print(e.kind, '-', e.text[:120])
```

## Leave a journal entry when something surprises you

Whenever a model behaved oddly, an error was confusing, or you had to work
around something, leave a note. This is how the next session learns:

```python
from falaw import journal
journal.issue("FLUX dev returned NSFW=True for a benign prompt",
              suggestion="Document an example that triggers it",
              tags=("flux", "safety"))
journal.improvement("Add an `upscale_image` tool that wraps clarity-upscaler",
                    tags=("backlog",))
journal.note("schnell quality=fast returns 1024x1024 by default")
```

## Pick a model without memorizing IDs

```python
from falaw import list_models, pick_model
[m.id for m in list_models(category='video')]
pick_model(category='image', quality_tier='ultra').id
```

## Tools

The functions below are also registered tools; bridges (MCP server, HTTP
service, UI) derive their surfaces from the same registry.


### `falaw.generate_image`

Generate an image from a text prompt. Picks a sensible FLUX model based on the requested quality tier ('fast', 'balanced', 'high', 'ultra'). Returns a falaw.Result whose .first asset has a URL you can .download(to=...).

Examples:
  - `falaw.generate_image(**{'prompt': 'A red panda eating bamboo', 'quality': 'fast'})`
  - `falaw.generate_image(**{'prompt': 'Cinematic portrait, 35mm film', 'quality': 'ultra'})`


### `falaw.text_to_speech`

Synthesize speech from text. Picks a TTS model by quality tier; pass `voice` and `extra` for model-specific knobs. Returns a falaw.Result whose .first asset is the audio URL.

Examples:
  - `falaw.text_to_speech(**{'text': 'Hello world', 'quality': 'balanced'})`
  - `falaw.text_to_speech(**{'text': 'Bonjour le monde', 'quality': 'high', 'voice': 'fr-FR-female-1'})`


### `falaw.refresh_llms`

Refresh `llms.txt` and `llms-full.txt` from fal.ai using conditional GETs (ETag-based). Cheap: returns immediately if nothing changed. On change, snapshots the previous version and journals the diff. Returns a summary dict like {'llms': {'changed': False}, ...}.


### `falaw.refresh_full_docs`

Re-crawl every per-page .md endpoint listed in `fal_ai_docs_index.md` with conditional GETs, then reassemble `fal_ai_docs_full.md`. Heavy. Gated on `is_stale(llms-full)` by default --- pass `force=True` to skip the gate. Pages that 304 are skipped; only changed pages re-download. Logs a single journal entry summarizing the run.


## Models known to falaw

The model registry lives at `falaw/data/models.json`. Refresh it from
`misc/docs/fal_ai_docs_full.md` when fal ships new models. Quick view:

```
  avatar               balanced   fal-ai/ai-avatar
  background_removal   high       fal-ai/birefnet/v2
  image                balanced   fal-ai/flux/dev
  image                fast       fal-ai/flux/schnell
  image                high       fal-ai/flux-pro/v1.1
  image                ultra      fal-ai/flux-pro/v1.1-ultra
  image_edit           ultra      fal-ai/flux-pro/kontext/max
  lipsync              high       fal-ai/sync-lipsync/v2
  llm                  balanced   fal-ai/any-llm
  music                balanced   fal-ai/diffrhythm
  music                high       fal-ai/lyria2
  tts                  balanced   fal-ai/playai/tts/v3
  tts                  high       fal-ai/minimax/speech-02-hd
  tts                  high       fal-ai/elevenlabs/tts/multilingual-v2
  upscale              high       fal-ai/clarity-upscaler
  video                balanced   fal-ai/minimax/hailuo-02/pro/image-to-video
  video                high       fal-ai/kling-video/v2.1/master/image-to-video
  video                ultra      fal-ai/veo3
  voice_clone          high       fal-ai/minimax/voice-clone
```

## When you can't find what you need

* Check `falaw/misc/docs/llms-full.txt` for a structured fal.ai overview.
* Check `falaw/misc/docs/fal_ai_docs_full.md` for the full corpus (~3MB).
* Drop into `falaw.call_fal(application, arguments)` for any model not
  yet wrapped --- this is the escape hatch. Then leave a `journal.improvement`
  asking for a proper tool wrapper.
