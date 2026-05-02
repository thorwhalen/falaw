# falaw

Agent-friendly Python facade over fal.ai for generating and managing AI media (images, video, audio).

```python
from falaw import generate_image, list_models, journal

r = generate_image("a tiger eye, macro, 35mm", quality="fast")
r.first.download(to="./tiger.png")

[m.id for m in list_models(category="video")]
journal.note("schnell at quality='fast' defaults to 1024x1024")
```

## Why

`fal-client` already gives you 100+ models behind a uniform call. What
agents (and humans) still struggle with is *which* model to use, *what*
parameters it takes, and *what to do with* the URL it returns. `falaw`
adds:

- Task-level verbs (`generate_image`, `text_to_speech`, ...) with smart model selection by quality tier.
- A queryable model registry --- no more grepping docs for IDs.
- `Result` / `Asset` objects that download, name, and organize outputs.
- A journal so each session leaves notes for the next one.
- A Claude skill, plus stub bridges for MCP and HTTP services --- all derived from the same tool registry.

## Install

```bash
pip install -e .
export FAL_KEY="your-fal-api-key"
```

## Core surface

| Function | Purpose |
| --- | --- |
| `generate_image(prompt, *, quality, image_size, model_id, extra)` | Text-to-image, picks FLUX by quality tier. |
| `text_to_speech(text, *, quality, voice, model_id, extra)` | TTS, picks a voice model by tier. |
| `list_models(*, category, quality_tier)` | Browse the catalog. |
| `pick_model(*, category, quality_tier)` | Pick a sensible default. |
| `call_fal(application, arguments)` | Escape hatch to any fal model. Auto-journals on error. |
| `journal.note / issue / improvement(...)` | Leave a trace for future sessions. |
| `Session(output_dir=...)` | Optional stateful controller. |

## Architecture

Single source of truth: a `ToolSpec` dataclass per tool. From it we derive every external surface:

```
falaw.registry  ──► bridges/skill.py    ──►  .claude/skills/falaw/SKILL.md
                ──► bridges/mcp.py      ──►  MCP server          (planned)
                ──► bridges/service.py  ──►  qh HTTP service     (planned)
                ──► (UI)                                          (planned)
```

Adding a new surface is a new bridge module, never a re-implementation of the operations.

## Self-improvement loop

Every session can read and write the agent journal at `~/.config/falaw/journal/`. The Claude skill instructs Claude to:

1. Read recent entries before novel work.
2. Write a note / issue / improvement when something surprises it.

`call_fal` auto-journals failures with the application id and arguments, so the next session recognizes the trap.

## Layout

```
falaw/
  base.py            ToolSpec, ModelRecord
  core.py            call_fal: subscribe + auto-journal
  registry.py        register_tool, list/get/pick model
  results.py         Asset, Result, parse_response
  session.py         Session
  journal.py         file-backed journal
  operations/
    images.py        generate_image
    audio.py         text_to_speech
  bridges/
    skill.py         render Claude SKILL.md from registry
    mcp.py           (stub)
    service.py       (stub)
  data/
    models.json      seed catalog
    skills/falaw/    generated skill files (shipped with package)
misc/
  docs/              aggregated fal.ai docs (3MB md, llms.txt, llms-full.txt)
  regenerate_skill.py
tests/
```

## Regenerate the skill after adding a tool

```bash
python misc/regenerate_skill.py
```

Writes `falaw/data/skills/falaw/SKILL.md` and `.claude/skills/falaw/SKILL.md`.

## Status

v0 --- functional core, real Claude skill, stubs for MCP and HTTP service. The bridges share the same registry, so filling in the stubs is additive.
