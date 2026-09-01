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

The server's ``instructions`` reach the model before any tool call, so they are
behaviour-driving text and are guarded like code:
:func:`unresolved_tool_references` reports every tool name or ``name_*`` family
a piece of prose names that the registry does not hold. An aggregating server
should run it over its own composed preamble too.

``fastmcp`` is an optional dependency: ``pip install falaw[mcp]``.
"""

from __future__ import annotations

import functools
import re
from dataclasses import fields, is_dataclass
from fnmatch import fnmatch
from typing import Any, Iterable, Optional

from ..base import ToolSpec
from ..registry import list_tools

#: Tag marking a tool that makes **no** vendor call — docs/registry upkeep only.
#: Everything else reaches fal.ai or an LLM and therefore spends money.
FREE_TAG = "maintenance"


def costed_tools() -> tuple[str, ...]:
    """Names of the falaw tools that spend money — the metering SSOT.

    Every genre package in the federation exposes this so an aggregating
    connector can gate spend from one source of truth per package
    (``braidio.mcp.COSTED_TOOLS``, ``muvid.mcp.COSTED_TOOLS``). falaw had
    none, so its 24 money-spending tools — the *raw* fal.ai operations,
    including ``text_to_video`` and ``render_scene`` — reached an aggregating
    connector completely unmetered (thorwhalen/reelee#265).

    **Derived from the registry, not hand-listed**, matching this module's
    existing contract that adding a falaw tool needs no edit here. The
    consequence is the safe one: a newly-registered tool is **costed by
    default** and must be explicitly tagged :data:`FREE_TAG` to be exempt.
    Forgetting the tag over-meters a free tool (annoying); the inverse would
    let a new money-spender through a credit cap (a billing hole).
    """
    return tuple(sorted(t.name for t in list_tools() if FREE_TAG not in t.tags))


#: Snapshot of :func:`costed_tools` for consumers that want a constant. Prefer
#: the function when tools may be registered after import.
COSTED_TOOLS = costed_tools()


_INSTRUCTIONS = (
    "falaw generates and manages AI media (images, video, audio) via fal.ai. "
    "Assume every tool spends money; the exceptions are the `refresh_*` "
    "maintenance tools, which read docs and vendor prices and make no billed "
    "call. There is no free cost preview here — no tool quotes a call before "
    "it runs — so the first run of a generating tool is where you commit to "
    "its price: confirm with the user before it. What is free is repetition: "
    "calls are content-addressed and cached, so re-running one with identical "
    "arguments returns the cached result at no charge, while changing any "
    "argument makes it a new paid call."
)

#: A tool name or ``name_*`` family as it appears in prose. Two shapes: a glob
#: family (``refresh_*``) and an exact snake_case name (``generate_image``).
#: Ordinary English never spells either, so scanning free text is safe.
_TOOL_REFERENCE = re.compile(
    r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*_\*"  # a family: refresh_*, plan_*
    r"|[a-z][a-z0-9]*(?:_[a-z0-9]+)+"  # an exact name: generate_image
)


def unresolved_tool_references(
    text: str, *, tool_names: Optional[Iterable[str]] = None
) -> tuple[str, ...]:
    """Tool names and ``name_*`` families named in ``text`` that do not exist.

    Behaviour-driving prose — the server ``instructions``, a tool description,
    an aggregating connector's composed preamble — names tools, and a call-site
    sweep cannot see prose. Nothing derives one from the other, so nothing
    failed when :data:`_INSTRUCTIONS` spent months telling every model to
    "use the ``plan_*`` tools to inspect cost before spending" while the
    registry held no such tool (thorwhalen/falaw#47). This is the check that
    now fails instead.

    Args:
        text: The prose to scan.
        tool_names: The names that count as existing; defaults to the falaw
            registry. An aggregating server that registered falaw under a
            prefix should pass what :func:`register_tools` returned, so
            ``falaw_generate_image`` resolves.

    Returns:
        The unresolved references, deduplicated, in order of first appearance.

    >>> unresolved_tool_references("Use the refresh_* tools.")
    ()
    >>> unresolved_tool_references("Use the plan_* tools to inspect cost.")
    ('plan_*',)
    """
    names = list(
        tool_names if tool_names is not None else (t.name for t in list_tools())
    )
    unresolved: list[str] = []
    for ref in _TOOL_REFERENCE.findall(text):
        if ref in unresolved:
            continue
        matched = (
            any(fnmatch(name, ref) for name in names)
            if ref.endswith("*")
            else ref in names
        )
        if not matched:
            unresolved.append(ref)
    return tuple(unresolved)


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
