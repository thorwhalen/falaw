"""Guard: falaw's money-spending tools must be declared, and default to costed.

An aggregating MCP connector gates spend per principal by unioning each genre
package's ``COSTED_TOOLS``. falaw exposed none — so its raw fal.ai operations,
which are the *most* directly expensive tools on such a connector
(``text_to_video``, ``render_scene``, ``lipsync``, ``voice_clone``), were
recorded-but-never-denied against a credit cap (thorwhalen/reelee#265).

The set is derived from the registry rather than hand-listed, so the failure
mode is the safe one: a newly-registered tool is costed **by default** and must
be explicitly tagged ``maintenance`` to be exempt. Forgetting the tag
over-meters a free tool; the inverse would let a new money-spender through a
credit cap.
"""

from __future__ import annotations

from falaw.bridges.mcp import COSTED_TOOLS, FREE_TAG, costed_tools
from falaw.registry import list_tools


def test_costed_tools_is_non_empty():
    """An empty set would silently meter nothing — the original defect."""
    assert COSTED_TOOLS, (
        "falaw declares no costed tools. A connector unioning this would gate "
        "nothing, and every fal call would pass a credit cap unmetered."
    )


def test_every_registered_tool_is_costed_unless_explicitly_tagged_free():
    """The default is COSTED. This is the property that must not invert."""
    registered = {t.name for t in list_tools()}
    exempt = {t.name for t in list_tools() if FREE_TAG in t.tags}
    assert set(COSTED_TOOLS) == registered - exempt, (
        "COSTED_TOOLS is no longer 'everything not tagged free'. If a tool was "
        "hand-removed, tag it instead — a hand-maintained exclusion list is how "
        "a money-spender goes unmetered."
    )


def test_the_exempt_tools_really_make_no_vendor_call():
    """Pin the exemptions by name, so widening them is a deliberate act.

    Anything added here must genuinely make no fal / LLM call. Today it is only
    the docs+registry refreshers.
    """
    exempt = {t.name for t in list_tools() if FREE_TAG in t.tags}
    assert exempt == {
        "refresh_full_docs",
        "refresh_llms",
        "refresh_models_from_corpus",
        # Reads fal's authenticated-but-free pricing endpoint (metadata
        # only, nothing billed) and writes models.json — falaw#18.
        "refresh_model_prices",
    }, (
        f"the free-tool exemption changed to {sorted(exempt)}. Each exemption "
        f"removes a tool from every downstream spend gate — justify it here."
    )


def test_the_expensive_operations_are_costed():
    """Spot-check the ones that would hurt most if unmetered."""
    for name in (
        "text_to_video",
        "image_to_video",
        "render_scene",
        "render_shot",
        "render_beat",
        "lipsync",
        "voice_clone",
        "text_to_speech",
        "generate_image",
        "llm_complete",
    ):
        assert name in COSTED_TOOLS, f"{name!r} spends money but is not costed"


def test_costed_tools_constant_matches_the_function():
    """The snapshot must not drift from the live derivation."""
    assert tuple(COSTED_TOOLS) == costed_tools()


def test_costed_tools_is_sorted_and_unique():
    """Stable ordering — a connector may diff these across releases."""
    assert list(COSTED_TOOLS) == sorted(set(COSTED_TOOLS))
