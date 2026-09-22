# falaw.scene

Scene IR: the editable structure that survives all the way to the pixels.

Design thesis (from the Directa Labs one-pager): a film stays in \*editable
structure\* from idea to final cut. The creator authors a Scene as data.
A directorial note becomes a single IR edit. The renderer picks it up
and re-renders only what changed.

All entities are frozen dataclasses with content-derived ids so:

* equality and hashing are structural — two beats with identical content
  share an id, and the cache can short-circuit re-rendering;
* edits create new entities (immutable); diffs against the previous
  version are obvious and surgical;
* serialization to JSON/YAML is mechanical (asdict).

The renderer (`falaw.operations.render`) consumes Scene; LLM tools
(`falaw.operations.llm`) produce or edit it.

### Functions

| [`beat_content_hash`](#falaw.scene.beat_content_hash)(beat, \*[, character])    | Hash everything that affects how the beat *renders*.      |
|----------------------------------------------------------------------------------------------|-----------------------------------------------------------|
| [`beat_id`](#falaw.scene.beat_id)(\*, speaker, line[, action, index]) | Deterministic, human-readable-ish beat id.                |
| `load_scene`(path)                                                                           |                                                           |
| `make_beat`(speaker[, line, action, emotion, ...])                                           |                                                           |
| `make_shot`(description, \*[, framing, ...])                                                 |                                                           |
| `save_scene`(scene, path)                                                                    |                                                           |
| [`scene_from_dict`](#falaw.scene.scene_from_dict)(d)                          | Inverse of asdict: reconstruct a Scene from a plain dict. |
| `scene_to_dict`(scene)                                                                       |                                                           |
| `shot_content_hash`(shot, \*[, environment])                                                 |                                                           |
| `shot_id`(\*, description[, framing, index])                                                 |                                                           |

### Classes

| [`Beat`](#falaw.scene.Beat)(\*, id[, speaker, line, action, ...])   | The atomic unit of a scene: who, says what, with what intent.   |
|-----------------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| [`Character`](#falaw.scene.Character)(\*, name[, description, ...])      | A reusable character: stable face, stable voice, stable style.  |
| [`Environment`](#falaw.scene.Environment)(\*, name[, description, ...])    | A reusable location/setting.                                    |
| [`Scene`](#falaw.scene.Scene)(\*, title[, style, characters, ...])   | The whole editable structure: cast, locations, shots, beats.    |
| [`Shot`](#falaw.scene.Shot)(\*, id[, description, framing, ...])    | A visual frame: framing + environment + characters in view.     |
| [`Voice`](#falaw.scene.Voice)(\*, name[, voice_id, ...])             | A character's voice spec.                                       |

### *class* falaw.scene.Beat(, id, speaker='', line='', action='', emotion='', shot_id='', duration_s=None, notes='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The atomic unit of a scene: who, says what, with what intent.

A Beat that has only `action` (no `line`) is a non-verbal beat.

### *class* falaw.scene.Character(, name, description='', reference_image_url='', voice=None, style_notes='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A reusable character: stable face, stable voice, stable style.

### *class* falaw.scene.Environment(, name, description='', reference_image_url='', time_of_day='', lighting='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A reusable location/setting.

### *class* falaw.scene.Scene(, title, style='', characters=(), environments=(), shots=(), beats=(), notes='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The whole editable structure: cast, locations, shots, beats.

#### with_beat(beat)

Return a new Scene with `beat` replacing any existing beat with the same id.

* **Return type:**
  [`Scene`](#falaw.scene.Scene)

### *class* falaw.scene.Shot(, id, description='', framing='medium', environment='', characters=(), camera='', notes='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A visual frame: framing + environment + characters in view.

Beats anchor to a Shot via `shot_id`. The Shot itself has its own
rendered output (still or short clip used as the anchor for beat
lipsync renders).

### *class* falaw.scene.Voice(, name, voice_id='', reference_audio_url='', model_id='', style_notes='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A character’s voice spec.

Three modes, choose any:

* `voice_id` — model-side voice id (e.g. ElevenLabs voice).
* `reference_audio_url` — a few seconds of audio to clone.
* `model_id` — override the default TTS model for this voice.

Always provide `name` for stable, human-readable referencing.

### falaw.scene.beat_content_hash(beat, , character=None)

Hash everything that affects how the beat *renders*.

Includes the beat’s content + the character’s identity anchors
(face image, voice spec). Style/emotion changes invalidate the
cache; pure id renames do not.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### falaw.scene.beat_id(, speaker, line, action='', index=None)

Deterministic, human-readable-ish beat id.

Pattern: `{index?}-{speaker_slug}-{content_hash}`. Index makes
chronological sort cheap; the hash makes the id stable when content
is unchanged.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### falaw.scene.scene_from_dict(d)

Inverse of asdict: reconstruct a Scene from a plain dict.

* **Return type:**
  [`Scene`](#falaw.scene.Scene)
