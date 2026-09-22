# falaw.operations.render

Beat / shot / scene rendering with caching.

The directorial workflow only works if a single IR edit causes only the
*affected* parts to re-render. Each renderer here:

1. Computes a content hash from the IR (`beat_content_hash` /
   `shot_content_hash`) plus the relevant identity anchors.
2. Stores the result in `falaw.cache` keyed by that hash.
3. Returns a small dict with `url`, `cache_hit`, and `hash` so the
   scene renderer can build a manifest.

Outputs:

* `render_beat` — TTS (using the speaker’s voice) → lipsync to the
  speaker’s reference image. Returns a video URL.
* `render_shot` — a still or short clip of the visual frame
  (storyboard or i2v depending on quality).
* `render_scene` — orchestrates beats and shots, returns a manifest
  dict that can be persisted next to the Scene file.

### Functions

| [`iter_render_scene`](#falaw.operations.render.iter_render_scene)(scene, \*[, tts_quality, ...])   | Yield `(kind, result)` pairs as each shot/beat finishes.          |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| [`manifest_path_for`](#falaw.operations.render.manifest_path_for)(scene, \*[, dir])                | Return where `render_scene`'s manifest would be saved by default. |
| [`render_beat`](#falaw.operations.render.render_beat)(beat, character, \*[, ...])            | Render one Beat to a lipsynced video.                             |
| [`render_scene`](#falaw.operations.render.render_scene)(scene, \*[, tts_quality, ...])        | Render every shot and beat.                                       |
| [`render_shot`](#falaw.operations.render.render_shot)(shot, \*[, environment, ...])          | Render a Shot as a still (default) or a short clip.               |

### falaw.operations.render.iter_render_scene(scene, , tts_quality='balanced', lipsync_quality='high', shot_quality='balanced', shots_as_video=False, force=False, concurrency=1)

Yield `(kind, result)` pairs as each shot/beat finishes.

`kind` ∈ `{"shot", "beat"}`. With `concurrency=1` results
arrive in submission order (shots before beats). With
`concurrency > 1` they arrive in completion order (use the
`"shot_id"` / `"beat_id"` keys to re-key by identity).

Cache hits are immediate: a fully-cached scene yields all results
in close succession even at `concurrency=1`.

### falaw.operations.render.manifest_path_for(scene, , dir=None)

Return where `render_scene`’s manifest would be saved by default.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### falaw.operations.render.render_beat(beat, character, , tts_quality='balanced', lipsync_quality='high', tts_model_id=None, avatar_model_id=None, force=False)

Render one Beat to a lipsynced video. Returns a small manifest dict.

* **Parameters:**
  * **tts_model_id** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Override the TTS model. When provided, takes precedence
    over the character’s voice.model_id and over `tts_quality`-based
    `pick_model`. Use this to force a specific TTS engine for one
    beat (e.g. eleven-v3 for emotional delivery, multilingual-v2 for
    consistency).
  * **avatar_model_id** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Override the avatar/lipsync model (e.g.
    `"fal-ai/bytedance/omnihuman/v1.5"` to bypass the default
    `ai-avatar` which is known to hang).
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### falaw.operations.render.render_scene(scene, , tts_quality='balanced', lipsync_quality='high', shot_quality='balanced', shots_as_video=False, force=False, concurrency=1)

Render every shot and beat. Returns a manifest dict.

`concurrency` controls how many shots/beats run in parallel
against fal. The work is HTTP-bound, so a thread pool is enough.
Default `1` preserves serial behavior. Use
[`iter_render_scene()`](#falaw.operations.render.iter_render_scene) instead if you want results yielded as
each unit completes (for live UI updates).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### falaw.operations.render.render_shot(shot, , environment=None, characters=(), style='', as_video=False, quality='balanced', image_model_id=None, image_to_video_model_id=None, force=False)

Render a Shot as a still (default) or a short clip.

* **Parameters:**
  * **image_model_id** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Override the image-gen model used for the storyboard
    still (defaults to `pick_model(category="image", …)`).
  * **image_to_video_model_id** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Override the image-to-video model used when
    `as_video=True` (e.g. `"fal-ai/minimax/hailuo-02/pro/image-to-video"`).
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
