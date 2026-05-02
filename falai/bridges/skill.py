"""Render a Claude SKILL.md (and references) from the falai tool registry.

The skill is the entry point that teaches Claude Code how to use falai. It
is generated --- never hand-edited at the install location --- so adding a
new tool automatically updates the skill the next time we run
`write_skill_files()`.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

from ..base import ToolSpec
from ..registry import list_models, list_tools

_HEADER = """---
name: falai
description: >-
  Generate and manage AI media (images, video, audio) via fal.ai. Use this
  skill whenever the user wants to generate, edit, upscale, or compose media,
  or asks about fal.ai or fal-client. The skill exposes Python tools that
  wrap fal-client with smart model selection, result handling, and a journal
  for self-improvement across sessions.
---

# falai

Use the `falai` Python package as your primary interface to fal.ai.

## Read the journal first

Before doing anything novel, glance at recent journal entries --- past
sessions may have left notes, gotchas, or suggestions that save you time:

```python
from falai import journal
for e in journal.recent(20):
    print(e.kind, '-', e.text[:120])
```

## Leave a journal entry when something surprises you

Whenever a model behaved oddly, an error was confusing, or you had to work
around something, leave a note. This is how the next session learns:

```python
from falai import journal
journal.issue("FLUX dev returned NSFW=True for a benign prompt",
              suggestion="Document an example that triggers it",
              tags=("flux", "safety"))
journal.improvement("Add an `upscale_image` tool that wraps clarity-upscaler",
                    tags=("backlog",))
journal.note("schnell quality=fast returns 1024x1024 by default")
```

## Pick a model without memorizing IDs

```python
from falai import list_models, pick_model
[m.id for m in list_models(category='video')]
pick_model(category='image', quality_tier='ultra').id
```

## Tools

The functions below are also registered tools; bridges (MCP server, HTTP
service, UI) derive their surfaces from the same registry.
"""

_FOOTER_TEMPLATE = """
## Models known to falai

The model registry lives at `falai/data/models.json`. Refresh it from
`misc/docs/fal_ai_docs_full.md` when fal ships new models. Quick view:

```
{model_lines}
```

## When you can't find what you need

* Check `falai/misc/docs/llms-full.txt` for a structured fal.ai overview.
* Check `falai/misc/docs/fal_ai_docs_full.md` for the full corpus (~3MB).
* Drop into `falai.call_fal(application, arguments)` for any model not
  yet wrapped --- this is the escape hatch. Then leave a `journal.improvement`
  asking for a proper tool wrapper.
"""


def build_skill_md(tools: Optional[Iterable[ToolSpec]] = None) -> str:
    """Render the SKILL.md content from the tool registry."""
    tools = list(tools if tools is not None else list_tools())
    parts = [_HEADER]
    for t in tools:
        parts.append(f"\n### `falai.{t.name}`\n")
        parts.append(t.description.strip())
        parts.append("")
        if t.examples:
            parts.append("Examples:")
            for ex in t.examples:
                parts.append(f"  - `falai.{t.name}(**{dict(ex)!r})`")
            parts.append("")
    model_lines = "\n".join(
        f"  {m.category:20s} {m.quality_tier:10s} {m.id}"
        for m in sorted(list_models(), key=lambda x: (x.category, x.quality_tier))
    )
    parts.append(_FOOTER_TEMPLATE.format(model_lines=model_lines))
    return "\n".join(parts)


def write_skill_files(target_dir: str) -> str:
    """Write SKILL.md (and a small references/ folder) under `target_dir`.

    Returns the path written.
    """
    os.makedirs(os.path.join(target_dir, "references"), exist_ok=True)
    skill_path = os.path.join(target_dir, "SKILL.md")
    with open(skill_path, "w") as f:
        f.write(build_skill_md())
    return skill_path
