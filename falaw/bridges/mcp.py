"""MCP bridge: expose every falaw tool as an MCP tool.

Like ``bridges/skill.py``, this is a thin adapter over
``falaw.registry.list_tools()`` — adding a new falaw tool automatically adds
an MCP tool, no edit here. Built on ``fastmcp`` (the federation's MCP library;
see ``lookbook/mcp.py`` for the canonical pattern).

Two entry points:

- :func:`register_tools` — add falaw's tools to an *existing* ``FastMCP``
  server. This is what an **aggregating** server (reelee's MCP server, which
  composes falaw + nw + artful + lacing) calls.
- :func:`build_mcp_server` — build a *standalone* ``FastMCP`` server exposing
  just falaw. :func:`serve` runs it over stdio.

``fastmcp`` is an optional dependency: ``pip install falaw[mcp]``.
"""

from __future__ import annotations

import functools
from dataclasses import fields, is_dataclass
from typing import Any, Iterable, Optional

from ..base import ToolSpec
from ..registry import list_tools

_INSTRUCTIONS = (
    "falaw generates and manages AI media (images, video, audio) via fal.ai. "
    "Every tool is content-addressed and cached, so re-running an unchanged "
    "call is free. Use the plan_* tools to inspect cost before spending."
)


def register_tools(
    server: Any,
    *,
    tools: Optional[Iterable[ToolSpec]] = None,
    prefix: str = "",
) -> list[str]:
    """Register every falaw :class:`ToolSpec` on ``server`` (a ``FastMCP``).

    Args:
        server: A ``fastmcp.FastMCP`` instance (or anything with a compatible
            ``.tool(fn, *, name, description, tags)`` method).
        tools: The tools to register; defaults to the whole falaw registry.
        prefix: Optional name prefix (e.g. ``"falaw_"``) so an aggregating
            server can namespace falaw's tools away from another package's.

    Returns:
        The MCP tool names registered (in registry order).
    """
    tools = list(tools if tools is not None else list_tools())
    registered: list[str] = []
    for spec in tools:
        name = f"{prefix}{spec.name}"
        server.tool(
            _jsonable_tool(spec.func),
            name=name,
            description=spec.description.strip(),
            tags=set(spec.tags),
        )
        registered.append(name)
    return registered


def build_mcp_server(
    *,
    name: str = "falaw",
    tools: Optional[Iterable[ToolSpec]] = None,
):
    """Build a standalone ``FastMCP`` server exposing every falaw tool.

    Raises ``ImportError`` with an install hint if ``fastmcp`` is missing.
    """
    try:
        from fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "The MCP bridge needs `fastmcp` — `pip install falaw[mcp]` "
            "(or `pip install fastmcp`)."
        ) from e

    server = FastMCP(name=name, instructions=_INSTRUCTIONS)
    register_tools(server, tools=tools)
    return server


def serve(*, transport: str = "stdio", **kwargs) -> None:
    """Run the standalone falaw MCP server.

    stdio is the default transport — what Claude Desktop and the Anthropic SDK
    expect when launching an MCP server as a subprocess.
    """
    build_mcp_server().run(transport=transport, **kwargs)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _jsonable_tool(func):
    """Wrap a falaw tool so its return value is JSON-friendly for MCP.

    falaw tools return rich objects (``Artifact``, ``Result``, ``Scene`` …).
    MCP needs JSON-able results, so the wrapper coerces dataclasses and
    pydantic models to plain dicts. ``functools.wraps`` preserves the
    signature so ``fastmcp`` still derives the input schema from it.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return _jsonable(func(*args, **kwargs))

    return wrapper


def _jsonable(value: Any) -> Any:
    """Best-effort coercion of a value to a JSON-serializable shape.

    Recurses uniformly so nested dataclasses become dicts and tuples become
    lists (JSON has no tuple type) — the result is predictable for a consumer
    regardless of how deep falaw's return objects nest.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonable(getattr(value, f.name)) for f in fields(value)}
    if hasattr(value, "model_dump"):  # pydantic v2 model
        return _jsonable(value.model_dump())
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value
