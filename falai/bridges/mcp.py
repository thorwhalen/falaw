"""MCP bridge (planned): expose falai tools as MCP tools.

The plan: walk `falai.registry.list_tools()` and emit one MCP tool per
ToolSpec, using the input/output schemas already on the spec. Until then,
agents can use the Python tools directly via the Claude skill.
"""

from __future__ import annotations


def build_mcp_server(*args, **kwargs):
    raise NotImplementedError(
        "MCP bridge is not yet implemented. Plan: derive MCP tools from "
        "`falai.registry.list_tools()` --- the same source of truth used by "
        "`bridges/skill.py`. See that module for the working pattern."
    )
