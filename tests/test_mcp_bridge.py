"""Tests for the MCP bridge (substrate gate F2).

The bridge is a thin adapter over ``falaw.registry.list_tools()`` — every
registered falaw tool becomes an MCP tool. ``fastmcp`` is a test dependency.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from falaw import CallPlan, Plan
from falaw.bridges.mcp import _jsonable, _jsonable_tool, build_mcp_server, register_tools
from falaw.registry import list_tools

fastmcp = pytest.importorskip("fastmcp")


def _tool_names(server) -> set[str]:
    tools = asyncio.run(server.list_tools())
    return {t.name for t in tools}


# --- server construction ---------------------------------------------------


def test_build_mcp_server_registers_every_falaw_tool():
    server = build_mcp_server()
    registry_names = {t.name for t in list_tools()}
    assert _tool_names(server) == registry_names
    assert len(registry_names) > 0  # the registry is not empty


def test_register_tools_returns_the_registered_names():
    server = fastmcp.FastMCP(name="t")
    registered = register_tools(server)
    assert set(registered) == {t.name for t in list_tools()}
    assert _tool_names(server) == set(registered)


def test_register_tools_prefix_namespaces_the_tools():
    server = fastmcp.FastMCP(name="t")
    registered = register_tools(server, prefix="falaw_")
    assert all(name.startswith("falaw_") for name in registered)
    assert _tool_names(server) == set(registered)


def test_register_tools_subset():
    server = fastmcp.FastMCP(name="t")
    subset = list_tools()[:3]
    registered = register_tools(server, tools=subset)
    assert set(registered) == {t.name for t in subset}


def test_tool_descriptions_are_carried_over():
    server = build_mcp_server()
    by_name = {t.name: t for t in asyncio.run(server.list_tools())}
    for spec in list_tools():
        assert by_name[spec.name].description == spec.description.strip()


# --- the jsonable coercion -------------------------------------------------


def test_jsonable_coerces_a_dataclass_recursively():
    plan = Plan(
        calls=(
            CallPlan(
                tool="generate_image",
                application="fal-ai/flux/dev",
                arguments={"prompt": "x"},
                output_kind="image",
            ),
        )
    )
    out = _jsonable(plan)
    assert isinstance(out, dict)
    assert isinstance(out["calls"], list)
    assert out["calls"][0]["tool"] == "generate_image"


def test_jsonable_passes_through_plain_values():
    assert _jsonable({"a": 1, "b": [1, 2]}) == {"a": 1, "b": [1, 2]}
    assert _jsonable("hello") == "hello"


def test_jsonable_tool_preserves_signature_and_coerces_return():
    def make_plan(n: int) -> Plan:
        return Plan(calls=())

    wrapped = _jsonable_tool(make_plan)
    # signature preserved so fastmcp can still derive the input schema
    assert list(inspect.signature(wrapped).parameters) == ["n"]
    # return value coerced to a plain dict
    assert wrapped(3) == {"calls": []}
