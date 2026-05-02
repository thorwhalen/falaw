"""Core types: ToolSpec and ModelRecord.

These dataclasses are the single source of truth from which every external
surface (Claude skill, MCP server, HTTP service, UI) is derived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

JSONSchema = Mapping[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolSpec:
    """Single source of truth for a tool exposed by falai.

    A ToolSpec is what the registry stores. Bridges read it to produce
    Claude-skill instructions, MCP tool descriptors, HTTP endpoints, etc.
    """

    name: str
    description: str
    func: Callable[..., Any]
    input_schema: JSONSchema = field(default_factory=dict)
    output_schema: JSONSchema = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    examples: tuple[Mapping[str, Any], ...] = ()
    version: str = "0.0.1"


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelRecord:
    """One entry in the fal model catalog."""

    id: str
    category: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    quality_tier: str = ""  # "fast" | "balanced" | "high" | "ultra"
    cost_hint: str = ""  # free-form for now
    docs_url: str = ""
