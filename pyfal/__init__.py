"""pyfal: agent-friendly Python facade over fal.ai for AI media generation.

Quick start:

    >>> from pyfal import generate_image  # doctest: +SKIP
    >>> r = generate_image("a tiger eye, macro, 35mm", quality="fast")
    >>> r.first.download(to="./tiger.png")

Browse the catalog:

    >>> from pyfal import list_models, list_tools  # doctest: +SKIP
    >>> [m.id for m in list_models(category="video")]

Leave notes for future sessions:

    >>> from pyfal import journal  # doctest: +SKIP
    >>> journal.note("Schnell tier defaults to 1024x1024")
"""

from . import journal, operations  # noqa: F401  (operations registers tools)
from . import refresh as _refresh  # noqa: F401  (refresh registers tools too)
from .base import ModelRecord, ToolSpec
from .core import call_fal
from .operations import generate_image, text_to_speech
from .refresh import refresh_full_docs, refresh_llms, refresh_state
from .registry import (
    get_model,
    get_tool,
    list_models,
    list_tools,
    pick_model,
    register_tool,
)
from .results import Asset, Result, parse_response
from .session import Session

__all__ = [
    "Asset",
    "ModelRecord",
    "Result",
    "Session",
    "ToolSpec",
    "call_fal",
    "generate_image",
    "get_model",
    "get_tool",
    "journal",
    "list_models",
    "list_tools",
    "parse_response",
    "pick_model",
    "refresh_full_docs",
    "refresh_llms",
    "refresh_state",
    "register_tool",
    "text_to_speech",
]
