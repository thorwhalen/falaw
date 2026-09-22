# falaw.operations.audio

Audio operations: text-to-speech and friends.

### Functions

| [`generate_audio`](#falaw.operations.audio.generate_audio)(prompt, \*[, kind, ...])           | Generate ambient/SFX/music from a prompt.   |
|----------------------------------------------------------------------------------------------------|---------------------------------------------|
| [`text_to_speech`](#falaw.operations.audio.text_to_speech)(text, \*[, quality, voice, ...])   | Synthesize speech.                          |
| [`voice_clone`](#falaw.operations.audio.voice_clone)(reference_audio_url, text, \*[, ...]) | Generate speech in a cloned voice.          |

### falaw.operations.audio.generate_audio(prompt, , kind='ambient', duration_s=None, model_id=None, extra=None)

Generate ambient/SFX/music from a prompt. Argument shape mirrors
[`falaw.plan_generate_audio()`](falaw.md#falaw.plan_generate_audio) exactly, so planned and eager calls
with identical inputs collapse to the same cache entry.

* **Return type:**
  [`Result`](falaw.results.md#falaw.results.Result)

### falaw.operations.audio.text_to_speech(text, , quality='balanced', voice=None, model_id=None, extra=None)

Synthesize speech. `voice` semantics are model-specific.

* **Return type:**
  [`Result`](falaw.results.md#falaw.results.Result)

### falaw.operations.audio.voice_clone(reference_audio_url, text, , model_id=None, extra=None)

Generate speech in a cloned voice.

* **Return type:**
  [`Result`](falaw.results.md#falaw.results.Result)
