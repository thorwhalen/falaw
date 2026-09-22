# falaw.operations.avatar

Avatar / lip-sync operations and composers.

Two distinct primitives, often confused:

* `animate_face` — image + audio → talking video. The face is a still;
  the model animates lips/expressions over the audio. Backed by ai-avatar
  / omnihuman (“avatar” registry category).
* `lipsync` — video + audio → re-synced video. The body and motion
  come from an existing video; only the mouth is replaced to match new
  audio. Backed by sync-lipsync / kling-lipsync (“lipsync” category).

Use `animate_face` when you only have a portrait. Use `lipsync` when
you already have a video clip.

The composer `talking_avatar_from_text` chains TTS → `animate_face`.

### Functions

| [`animate_face`](#falaw.operations.avatar.animate_face)(image_url, audio_url, \*[, ...])     | Animate a still face from audio.                                |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| [`lipsync`](#falaw.operations.avatar.lipsync)(video_url, audio_url, \*[, quality, ...]) | Re-sync mouth motion in an existing video to a new audio track. |
| [`talking_avatar_from_text`](#falaw.operations.avatar.talking_avatar_from_text)(text, image_url, \*)     | text + face image → talking video.                              |

### falaw.operations.avatar.animate_face(image_url, audio_url, , prompt='', quality='balanced', model_id=None, extra=None)

Animate a still face from audio. Image + audio → talking video.

* **Return type:**
  [`Result`](falaw.results.html.md#falaw.results.Result)

### falaw.operations.avatar.lipsync(video_url, audio_url, , quality='high', model_id=None, extra=None)

Re-sync mouth motion in an existing video to a new audio track.

* **Return type:**
  [`Result`](falaw.results.html.md#falaw.results.Result)

### falaw.operations.avatar.talking_avatar_from_text(text, image_url, , voice=None, prompt='', tts_quality='balanced', avatar_quality='balanced')

text + face image → talking video. Two fal calls, one Result.

* **Return type:**
  [`Result`](falaw.results.html.md#falaw.results.Result)
