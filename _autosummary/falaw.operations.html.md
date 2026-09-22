# falaw.operations

Task-level verbs: stable, agent-friendly entry points.

Each submodule registers its functions via the `register_tool` decorator,
so importing this package populates the ToolRegistry as a side effect.

### Modules

| [`audio`](falaw.operations.audio.html.md#module-falaw.operations.audio)                 | Audio operations: text-to-speech and friends.                         |
|------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`avatar`](falaw.operations.avatar.html.md#module-falaw.operations.avatar)               | Avatar / lip-sync operations and composers.                           |
| [`images`](falaw.operations.images.html.md#module-falaw.operations.images)               | Image-generation and image-manipulation operations.                   |
| [`llm`](falaw.operations.llm.html.md#module-falaw.operations.llm)                     | LLM-driven tools: text completion, screenplay → Scene IR, IR editing. |
| [`preproduction`](falaw.operations.preproduction.html.md#module-falaw.operations.preproduction) | Pre-production: produce reusable identity anchors for a Scene.        |
| [`render`](falaw.operations.render.html.md#module-falaw.operations.render)               | Beat / shot / scene rendering with caching.                           |
| [`video`](falaw.operations.video.html.md#module-falaw.operations.video)                 | Video-generation operations: text-to-video and image-to-video.        |
