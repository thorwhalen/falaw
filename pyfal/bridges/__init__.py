"""Bridges: derive auxiliary surfaces (skill, MCP, HTTP service) from the tool registry.

Each bridge is a thin adapter over `pyfal.registry.list_tools()`. The point
is that adding a new surface (e.g. a CLI, a Slack bot, a TUI) is a new
bridge module --- never a re-implementation of the operations themselves.
"""

from .skill import build_skill_md, write_skill_files  # noqa: F401
