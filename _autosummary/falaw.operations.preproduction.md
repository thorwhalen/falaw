# falaw.operations.preproduction

Pre-production: produce reusable identity anchors for a Scene.

The downstream renderer reuses Character.reference_image_url for every
shot featuring that character, and Character.voice for every line they
speak. So the quality of the *anchors* set here propagates everywhere.

Each function returns an updated entity (Character / Environment) you
can feed back into the Scene via `scene.with_character(...)` etc.

### Functions

| [`cast_character`](#falaw.operations.preproduction.cast_character)(name, description, \*[, ...])   | Create a Character with a canonical face (and optional voice).   |
|-------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| [`cast_voice`](#falaw.operations.preproduction.cast_voice)(character, \*[, voice_id, ...])     | Attach or update the Voice on a Character.                       |
| [`establish_environment`](#falaw.operations.preproduction.establish_environment)(name, description, \*)   | Create an Environment with a canonical establishing image.       |
| [`storyboard_shot`](#falaw.operations.preproduction.storyboard_shot)(shot, \*[, environment, ...])  | Render a storyboard still for a Shot.                            |

### falaw.operations.preproduction.cast_character(name, description, , image_url='', style='', quality='high', voice_id='', reference_audio_url='', voice_style='')

Create a Character with a canonical face (and optional voice).

If `image_url` is given, we skip face generation and use that
image directly. Otherwise we run text-to-image with the description
(+ optional `style` suffix), cache the result, and use the URL.

* **Return type:**
  [`Character`](falaw.scene.md#falaw.scene.Character)

### falaw.operations.preproduction.cast_voice(character, , voice_id='', reference_audio_url='', style_notes='', model_id='')

Attach or update the Voice on a Character.

* **Return type:**
  [`Character`](falaw.scene.md#falaw.scene.Character)

### falaw.operations.preproduction.establish_environment(name, description, , time_of_day='', lighting='', image_url='', quality='high')

Create an Environment with a canonical establishing image.

* **Return type:**
  [`Environment`](falaw.scene.md#falaw.scene.Environment)

### falaw.operations.preproduction.storyboard_shot(shot, , environment=None, characters=(), style='', quality='balanced')

Render a storyboard still for a Shot.

* **Return type:**
  [`Result`](falaw.results.md#falaw.results.Result)
