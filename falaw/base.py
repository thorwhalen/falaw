"""Core types: ToolSpec and ModelRecord.

These dataclasses are the single source of truth from which every external
surface (Claude skill, MCP server, HTTP service, UI) is derived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping, Optional

JSONSchema = Mapping[str, Any]


CostKind = Literal["per_call", "per_image", "per_second", "per_token", "per_megapixel"]


@dataclass(frozen=True, slots=True, kw_only=True)
class CostEstimate:
    """Quantitative cost of one fal call against this model.

    Attributes:
        kind: How the price scales. ``per_call`` is the simplest:
            constant per invocation regardless of size. ``per_second``
            applies to video / TTS where output length matters.
            ``per_image`` covers batch image gen. ``per_megapixel``
            covers high-res image generation. ``per_token`` covers
            LLM-style endpoints.
        amount: USD (or ``currency``) per unit defined by ``kind``.
        currency: ISO 4217 code. ``"USD"`` is the only supported value
            today; the field exists so we can extend without a schema
            migration.
        notes: Free-form caveats — "rounded up to next second", etc.
        source: How the estimate was obtained — ``"docs"``,
            ``"empirical"``, ``"approximate"``. Lets us flag stale or
            unverified entries in audits.
    """

    kind: CostKind
    amount: float
    currency: str = "USD"
    notes: str = ""
    source: str = "approximate"


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolSpec:
    """Single source of truth for a tool exposed by falaw.

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
    cost_hint: str = ""  # legacy free-form text; kept for back-compat
    cost_estimate: Optional[CostEstimate] = None  # quantitative; preferred
    docs_url: str = ""
