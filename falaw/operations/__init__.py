"""Task-level verbs: stable, agent-friendly entry points.

Each submodule registers its functions via the `register_tool` decorator,
so importing this package populates the ToolRegistry as a side effect.
"""

from .images import generate_image  # noqa: F401
from .audio import text_to_speech  # noqa: F401
