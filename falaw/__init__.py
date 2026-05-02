"""falaw: agent-friendly Python facade over fal.ai for AI media generation.

Quick start:

    >>> from falaw import generate_image  # doctest: +SKIP
    >>> r = generate_image("a tiger eye, macro, 35mm", quality="fast")
    >>> r.first.download(to="./tiger.png")

Browse the catalog:

    >>> from falaw import list_models, list_tools  # doctest: +SKIP
    >>> [m.id for m in list_models(category="image_to_video")]

Leave notes for future sessions:

    >>> from falaw import journal  # doctest: +SKIP
    >>> journal.note("Schnell tier defaults to 1024x1024")
"""

from . import corpus as _corpus  # noqa: F401  (registers refresh_models_from_corpus)
from . import journal, operations  # noqa: F401  (operations registers tools)
from . import refresh as _refresh  # noqa: F401  (refresh registers tools too)
from .base import ModelRecord, ToolSpec
from .core import call_fal
from .corpus import extract_models_from_corpus, refresh_models_from_corpus
from .operations import (
    edit_image,
    generate_image,
    image_to_video,
    lipsync,
    remove_background,
    talking_avatar_from_text,
    text_to_speech,
    text_to_video,
    upscale_image,
    voice_clone,
)
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
    "edit_image",
    "extract_models_from_corpus",
    "generate_image",
    "get_model",
    "get_tool",
    "image_to_video",
    "journal",
    "lipsync",
    "list_models",
    "list_tools",
    "parse_response",
    "pick_model",
    "refresh_full_docs",
    "refresh_llms",
    "refresh_models_from_corpus",
    "refresh_state",
    "register_tool",
    "remove_background",
    "talking_avatar_from_text",
    "text_to_speech",
    "text_to_video",
    "upscale_image",
    "voice_clone",
]
