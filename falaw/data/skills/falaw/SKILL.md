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


### `falaw.refresh_models_from_corpus`

Parse `misc/docs/llms-full.txt` and merge any newly-discovered models into `falaw/data/models.json`. Hand-curated entries are preserved; only previously-unknown ids are added. Pass `write=True` to persist; otherwise returns a dry-run summary.


### `falaw.text_to_speech`

Synthesize speech from text. Picks a TTS model by quality tier; pass `voice` and `extra` for model-specific knobs. Returns a falaw.Result whose .first asset is the audio URL.

Examples:
  - `falaw.text_to_speech(**{'text': 'Hello world', 'quality': 'balanced'})`
  - `falaw.text_to_speech(**{'text': 'Bonjour le monde', 'quality': 'high', 'voice': 'fr-FR-female-1'})`


### `falaw.voice_clone`

Synthesize speech in a cloned voice. Provide a `reference_audio_url` (a few seconds of the target voice) and the text to speak. Returns a falaw.Result whose .first asset is the cloned-voice audio URL.

Examples:
  - `falaw.voice_clone(**{'reference_audio_url': 'https://example.com/me.wav', 'text': 'Hello, this is in my voice.'})`


### `falaw.lipsync`

Generate a lip-synced talking-head video from a face image and an audio track. Returns a falaw.Result whose .first asset is the synced video URL.

Examples:
  - `falaw.lipsync(**{'image_url': 'https://...', 'audio_url': 'https://...'})`


### `falaw.talking_avatar_from_text`

Composer: text + face image → lip-synced talking video. Internally runs `text_to_speech(text)` then `lipsync(image_url, audio_url)`. Returns the lipsync Result. Use this when you have text and a portrait but no pre-recorded audio.

Examples:
  - `falaw.talking_avatar_from_text(**{'text': 'Welcome to the demo.', 'image_url': 'https://example.com/host.jpg'})`


### `falaw.generate_image`

Generate an image from a text prompt. Picks a sensible FLUX model based on the requested quality tier ('fast', 'balanced', 'high', 'ultra'). Returns a falaw.Result whose .first asset has a URL you can .download(to=...).

Examples:
  - `falaw.generate_image(**{'prompt': 'A red panda eating bamboo', 'quality': 'fast'})`
  - `falaw.generate_image(**{'prompt': 'Cinematic portrait, 35mm film', 'quality': 'ultra'})`


### `falaw.edit_image`

Edit an image using a natural-language instruction. Picks a FLUX Kontext / SeedEdit model by quality tier. Returns a falaw.Result with the edited image.

Examples:
  - `falaw.edit_image(**{'image_url': 'https://...', 'prompt': 'make the sky orange'})`
  - `falaw.edit_image(**{'image_url': 'https://...', 'prompt': 'remove the person on the left', 'quality': 'ultra'})`


### `falaw.upscale_image`

Upscale an image to higher resolution while preserving fidelity. Defaults to clarity-upscaler. Returns a falaw.Result with the upscaled image.

Examples:
  - `falaw.upscale_image(**{'image_url': 'https://...', 'scale': 2.0})`
  - `falaw.upscale_image(**{'image_url': 'https://...', 'scale': 4.0, 'extra': {'creativity': 0.35}})`


### `falaw.remove_background`

Remove the background from an image, returning a transparent PNG. Defaults to BiRefNet v2 (quality='high') or Bria (quality='balanced'). Returns a falaw.Result.

Examples:
  - `falaw.remove_background(**{'image_url': 'https://example.com/photo.jpg'})`


### `falaw.text_to_video`

Generate a video from a text prompt. Picks a tier-appropriate model (Veo 3 for ultra, Seedance Pro for high). Use `extra` to pass through model-specific knobs like duration, aspect_ratio, negative_prompt.

Examples:
  - `falaw.text_to_video(**{'prompt': 'A drone shot over a misty pine forest at dawn'})`
  - `falaw.text_to_video(**{'prompt': 'Macro: a single dewdrop on a spider web', 'quality': 'ultra'})`


### `falaw.image_to_video`

Animate a still image into a short video. Optional prompt steers the motion. Picks a tier-appropriate i2v model (Kling Master for ultra, Seedance for high, Hailuo for balanced).

Examples:
  - `falaw.image_to_video(**{'image_url': 'https://...', 'prompt': 'the camera slowly zooms in'})`
  - `falaw.image_to_video(**{'image_url': 'https://...', 'quality': 'balanced'})`


### `falaw.refresh_llms`

Refresh `llms.txt` and `llms-full.txt` from fal.ai using conditional GETs (ETag-based). Cheap: returns immediately if nothing changed. On change, snapshots the previous version and journals the diff. Returns a summary dict like {'llms': {'changed': False}, ...}.


### `falaw.refresh_full_docs`

Re-crawl every per-page .md endpoint listed in `fal_ai_docs_index.md` with conditional GETs, then reassemble `fal_ai_docs_full.md`. Heavy. Gated on `is_stale(llms-full)` by default --- pass `force=True` to skip the gate. Pages that 304 are skipped; only changed pages re-download. Logs a single journal entry summarizing the run.


## Models known to falaw

The model registry lives at `falaw/data/models.json`. Refresh it from
`misc/docs/fal_ai_docs_full.md` when fal ships new models. Quick view:

```
  audio                balanced   fal-ai/elevenlabs/audio-isolation
  audio                balanced   fal-ai/playai/inpaint/diffusion
  avatar               balanced   fal-ai/ai-avatar
  background_removal   balanced   fal-ai/bria/background/remove
  background_removal   balanced   fal-ai/ideogram/v3/reframe
  background_removal   high       fal-ai/birefnet/v2
  image                balanced   fal-ai/flux/dev
  image                balanced   fal-ai/ideogram/v3
  image                balanced   fal-ai/recraft/v3/text-to-image
  image                fast       fal-ai/flux/schnell
  image                fast       fal-ai/hidream-i1-fast
  image                fast       fal-ai/sana/sprint
  image                high       fal-ai/flux-pro/v1.1
  image                ultra      fal-ai/flux-pro/v1.1-ultra
  image                ultra      fal-ai/imagen4/preview/ultra
  image_edit           balanced   fal-ai/flux-kontext/dev
  image_edit           balanced   fal-ai/omnigen-v2
  image_edit           high       fal-ai/bytedance/seededit/v3/edit-image
  image_edit           ultra      fal-ai/flux-pro/kontext/max
  image_to_video       balanced   fal-ai/minimax/hailuo-02/pro/image-to-video
  image_to_video       balanced   fal-ai/pixverse/v4.5/image-to-video
  image_to_video       high       fal-ai/bytedance/seedance/v1/pro/image-to-video
  image_to_video       ultra      fal-ai/kling-video/v2.1/master/image-to-video
  lipsync              balanced   fal-ai/ai-avatar/multi
  lipsync              balanced   fal-ai/kling-video/lipsync/audio-to-video
  lipsync              high       fal-ai/sync-lipsync/v2
  llm                  balanced   fal-ai/any-llm
  llm                  balanced   fal-ai/any-llm/vision
  music                balanced   fal-ai/diffrhythm
  music                balanced   fal-ai/mmaudio-v2/text-to-audio
  music                high       fal-ai/lyria2
  text_to_video        high       fal-ai/bytedance/seedance/v1/pro/text-to-video
  text_to_video        ultra      fal-ai/veo3
  training             balanced   fal-ai/flux-lora-portrait-trainer
  training             fast       fal-ai/flux-lora-fast-training
  training             high       fal-ai/flux-pro-trainer
  tts                  balanced   fal-ai/playai/tts/dialog
  tts                  balanced   fal-ai/playai/tts/v3
  tts                  high       fal-ai/elevenlabs/tts/multilingual-v2
  tts                  high       fal-ai/minimax/speech-02-hd
  upscale              high       fal-ai/clarity-upscaler
  voice_clone          high       fal-ai/minimax/voice-clone
```

## When you can't find what you need

* Check `falaw/misc/docs/llms-full.txt` for a structured fal.ai overview.
* Check `falaw/misc/docs/fal_ai_docs_full.md` for the full corpus (~3MB).
* Drop into `falaw.call_fal(application, arguments)` for any model not
  yet wrapped --- this is the escape hatch. Then leave a `journal.improvement`
  asking for a proper tool wrapper.
