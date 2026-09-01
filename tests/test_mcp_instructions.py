"""The MCP server's ``instructions`` may only name tools that exist.

``_INSTRUCTIONS`` reaches the model on every session, before any tool call,
and is what it reasons from when deciding whether it may spend. For months it
told every caller to "use the ``plan_*`` tools to inspect cost before
spending" while no registered tool matched that family — ``plan_*`` is
falaw's *Python* API, which no MCP caller can reach (thorwhalen/falaw#47).
Nothing failed, because the prose and the tool list are not derived from each
other. These tests are that derivation.

Deliberately in its own module: ``test_mcp_bridge.py`` opens with
``pytest.importorskip("fastmcp")``, which removes its tests from *collection*
rather than skipping them. This guard needs no MCP library — only the string
and the registry — so it must not inherit that gate.
"""

from __future__ import annotations

from falaw.bridges.mcp import (
    FREE_TAG,
    _INSTRUCTIONS,
    unresolved_tool_references,
)
from falaw.registry import list_tools

#: The string that shipped until falaw#47. Kept verbatim so the guard is shown
#: catching the real defect rather than a constructed one.
_INSTRUCTIONS_BEFORE_THE_FIX = (
    "falaw generates and manages AI media (images, video, audio) via fal.ai. "
    "Every tool is content-addressed and cached, so re-running an unchanged "
    "call is free. Use the plan_* tools to inspect cost before spending."
)


def test_the_server_instructions_name_only_tools_that_exist():
    """The guard itself. Red on the pre-fix string, green on today's."""
    assert unresolved_tool_references(_INSTRUCTIONS) == ()


def test_the_guard_catches_the_family_that_was_advertised_and_never_existed():
    """Without this, neutering the extractor would leave the guard green."""
    assert unresolved_tool_references(_INSTRUCTIONS_BEFORE_THE_FIX) == ("plan_*",)


def test_the_guard_catches_an_exact_name_that_is_not_an_mcp_tool():
    """``estimate_scene_cost`` is a real falaw *function* and no MCP tool.

    The two surfaces are the trap: prose written from the Python API names
    things a connector caller cannot reach.
    """
    assert unresolved_tool_references("Call estimate_scene_cost first.") == (
        "estimate_scene_cost",
    )
    assert unresolved_tool_references("Then call generate_image.") == ()


def test_a_prefixing_aggregator_can_check_its_own_composed_instructions():
    """reelee's connector registers falaw under a prefix; the seam is ``tool_names``."""
    registered = tuple(f"falaw_{t.name}" for t in list_tools())
    text = "Use falaw_generate_image, then falaw_image_to_video."
    assert unresolved_tool_references(text, tool_names=registered) == ()
    # …and the unprefixed spelling is then the broken one.
    assert unresolved_tool_references("Use generate_image.", tool_names=registered) == (
        "generate_image",
    )


def test_the_refresh_family_the_instructions_call_free_is_actually_free():
    """The instructions name ``refresh_*`` as the exception that spends nothing.

    ``costed_tools()`` derives spend from the absence of :data:`FREE_TAG`, so
    a ``refresh_*`` tool that lost the tag would make the sentence a lie in
    the expensive direction.
    """
    refresh = [t for t in list_tools() if t.name.startswith("refresh_")]
    assert refresh, "the instructions name a family that no longer exists"
    assert [t.name for t in refresh if FREE_TAG not in t.tags] == []
