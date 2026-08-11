"""falaw#17 — key composition must fail loudly, never guess.

`json.dumps(..., default=str)` inside a key-composition function fails in both
directions at once: values whose `str()` coincide **collide** (a silent wrong
HIT — the caller gets someone else's artifact, billed as a saving), and
objects without a stable `str()` mint a fresh key per instance (a permanent
MISS plus unbounded cache growth). These tests pin the replacement rule — a
non-canonicalisable argument is a typed refusal at the boundary, while every
JSON-native argument keeps the exact digest it had before, so the existing
cache survives.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest

from falaw import CallPlan, FalNonCanonicalArgument, Plan
from falaw.cache import _entry_dir, _key, cache_put, cached_call_fal
from falaw.plan import _synthetic_artifact, make_call_plan, plan_hash


# --- the two silent failure modes now refuse ---------------------------------


class _SameStr:
    """Two distinct instances, one str() — the wrong-HIT shape."""

    def __str__(self) -> str:
        return "the-same-text"


def test_two_objects_with_equal_str_raise_instead_of_colliding():
    with pytest.raises(FalNonCanonicalArgument) as e1:
        _key("fal-ai/flux/dev", {"ref": _SameStr()})
    with pytest.raises(FalNonCanonicalArgument):
        _key("fal-ai/flux/dev", {"ref": _SameStr()})
    # The error is diagnosable: it names the offending path and type.
    assert "ref" in str(e1.value)
    assert "_SameStr" in str(e1.value)
    assert e1.value.path.endswith(".ref")


@pytest.mark.parametrize(
    "impostor",
    [Decimal("0.5"), Path("/a/b")],
    ids=["decimal-vs-its-string", "path-vs-its-string"],
)
def test_a_value_and_its_str_never_share_a_key(impostor):
    """Under `default=str` these pairs produced the SAME key — reproduced in
    the issue. Now the non-JSON side raises, so a collision is impossible."""
    stringly = _key("fal-ai/flux/dev", {"x": str(impostor)})
    assert stringly  # the honest string form still keys fine
    with pytest.raises(FalNonCanonicalArgument):
        _key("fal-ai/flux/dev", {"x": impostor})


def test_a_non_string_mapping_key_raises():
    """`{1: ...}` and `{"1": ...}` dump to identical bytes — JSON key coercion
    is a collision, not a convenience (lacing refuses it too)."""
    with pytest.raises(FalNonCanonicalArgument) as e:
        _key("fal-ai/flux/dev", {"extra": {1: "x"}})
    assert "extra" in e.value.path


# --- NaN: refused in arguments, never written to disk ------------------------


def test_nan_in_arguments_raises_at_plan_time():
    with pytest.raises(FalNonCanonicalArgument) as e:
        make_call_plan(
            tool="generate_image",
            application="fal-ai/flux/dev",
            arguments={"strength": float("nan")},
            output_kind="image",
        )
    assert "strength" in str(e.value)


def test_cache_put_never_writes_a_manifest_containing_bare_nan():
    """Python's json happily writes a bare `NaN` — valid to itself, invalid
    JSON to every strict parser. The manifest must never carry one."""
    args = {"prompt": "ok"}
    with pytest.raises(ValueError):
        cache_put("fal-ai/flux/dev", args, {"score": float("nan")})
    entry = _entry_dir(_key("fal-ai/flux/dev", args))
    assert os.listdir(entry) == []  # no manifest, and no .part left behind


# --- the refusal is free: it happens before any network call ------------------


def test_make_call_plan_refuses_before_the_cache_peek_can_swallow_it():
    """The peek's `except Exception -> "unknown"` is best-effort by design;
    the refusal must not be laundered through it into a silent "unknown"."""
    with pytest.raises(FalNonCanonicalArgument):
        make_call_plan(
            tool="generate_image",
            application="fal-ai/flux/dev",
            arguments={"extra_ref": _SameStr()},
            output_kind="image",
            consult_cache=True,
        )


def test_cached_call_fal_refuses_junk_key_arguments_before_spending(monkeypatch):
    """On `refresh=True` the first key computation used to happen in
    `cache_put` — after the paid call. The refusal must precede the spend."""
    calls: list[str] = []
    monkeypatch.setattr(
        "falaw.cache.call_fal",
        lambda app, args, **kw: calls.append(app) or {"images": []},
    )
    with pytest.raises(FalNonCanonicalArgument):
        cached_call_fal(
            "fal-ai/flux/dev",
            {"prompt": "fine"},
            key_arguments={"ref": _SameStr()},
            refresh=True,
        )
    assert calls == []  # nothing was billed on the way to the refusal


def test_plan_hash_fails_loudly_for_a_hand_built_call_plan():
    """`make_call_plan` is the boundary, but a CallPlan can be constructed
    directly — the hash itself must still refuse rather than guess."""
    junk = CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"ref": _SameStr()},
        output_kind="image",
    )
    with pytest.raises(FalNonCanonicalArgument):
        plan_hash(Plan(calls=(junk,)))
    with pytest.raises(FalNonCanonicalArgument):
        _synthetic_artifact(junk)


# --- and the existing cache survives: JSON-native digests are unchanged -------

# Literals computed on main before this change (falaw 0.0.29). If any of these
# move, previously-written cache entries silently stop hitting and nw.jobs'
# plan-hash dedup forgets every in-flight plan — so a move must be a decision,
# not a side effect.

_KEY_BEFORE = "4bce4feadc533ca588905c71bdee28827656004071a8430affc06a8d5f08d68b"
_PLAN_HASH_BEFORE = "60327a7d2400d3c5de60f836763c8a7603cbb7f3b9dfa2addc44e16f6b303b1c"
_SYNTHETIC_BEFORE = "5a106d8daa3a0dc61918e432fbc08236dea4d177a8dc609eac3c5acaff71f3db"


def _native_plan() -> Plan:
    a = CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"prompt": "a tiger"},
        output_kind="image",
    )
    b = CallPlan(
        tool="image_to_video",
        application="fal-ai/svd",
        arguments={"image_url": "<from 0>"},
        output_kind="video",
    )
    return Plan(calls=(a, b))


def test_json_native_cache_keys_are_byte_identical_to_before():
    assert (
        _key(
            "fal-ai/flux/dev",
            {
                "prompt": "a tiger",
                "steps": 28,
                "guidance": 3.5,
                "seed": None,
                "safe": True,
            },
        )
        == _KEY_BEFORE
    )


def test_json_native_plan_hash_and_synthetic_id_are_byte_identical_to_before():
    plan = _native_plan()
    assert plan_hash(plan) == _PLAN_HASH_BEFORE
    assert _synthetic_artifact(plan.calls[0]).asset_id == _SYNTHETIC_BEFORE
