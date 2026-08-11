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


# --- adversarial-review fixes: the walk matches json.dumps exactly ------------


def test_a_nested_non_dict_mapping_is_a_typed_refusal_not_a_typeerror():
    """`MappingProxyType` walks like a dict but json.dumps refuses it — so the
    validator must too, or the untyped TypeError escapes one layer down and
    the boundary check launders it into a silent "unknown" (review finding 1)."""
    from types import MappingProxyType

    proxy_args = {"extra": MappingProxyType({"a": 1})}
    with pytest.raises(FalNonCanonicalArgument) as e:
        _key("fal-ai/flux/dev", proxy_args)
    assert "extra" in e.value.path
    assert "mappingproxy" in str(e.value)
    # And the plan boundary refuses loudly instead of swallowing a TypeError
    # into cache_status="unknown".
    with pytest.raises(FalNonCanonicalArgument):
        make_call_plan(
            tool="generate_image",
            application="fal-ai/flux/dev",
            arguments=proxy_args,
            output_kind="image",
        )


def test_cached_call_fal_refuses_a_nested_mapping_proxy_before_spending(monkeypatch):
    """Review finding 1's worst consequence: the old walk passed the proxy,
    the paid call ran, and cache_put's TypeError then destroyed the billed
    response. The refusal must come first."""
    from types import MappingProxyType

    calls: list[str] = []
    monkeypatch.setattr(
        "falaw.cache.call_fal",
        lambda app, args, **kw: calls.append(app) or {"images": []},
    )
    with pytest.raises(FalNonCanonicalArgument):
        cached_call_fal(
            "fal-ai/flux/dev",
            {"prompt": "fine"},
            key_arguments={"ref": MappingProxyType({"a": 1})},
            refresh=True,
        )
    assert calls == []


def test_a_circular_argument_is_a_typed_refusal():
    """json.dumps would raise its own ValueError('Circular reference'); the
    walk must classify it first — and must not loop or blow the stack."""
    loop: dict = {"a": 1}
    loop["self"] = loop
    with pytest.raises(FalNonCanonicalArgument) as e:
        _key("fal-ai/flux/dev", loop)
    assert "circular" in str(e.value)


def test_a_diamond_shared_subvalue_is_not_a_false_circular_refusal():
    """The same object reached twice non-cyclically is fine — json accepts it,
    so the validator must not cry 'circular'."""
    shared = {"w": 512}
    key = _key("fal-ai/flux/dev", {"a": shared, "b": shared})
    assert key


def test_deep_nesting_validates_as_far_as_json_serializes():
    """Review finding 5: the recursive walk died at ~1000 levels while the C
    serializer handled 3000 — the validator must not have a lower ceiling
    than the thing it guards."""
    deep: dict = {"leaf": 1}
    for _ in range(2000):
        deep = {"n": deep}
    assert _key("fal-ai/flux/dev", {"deep": deep})


# --- adversarial-review fixes: a paid result is never discarded ---------------


def test_a_nan_bearing_response_is_returned_and_warned_not_destroyed(monkeypatch):
    """Review finding 2: fal_client's json.loads accepts bare NaN, and the
    strict manifest write then raised AFTER the billed call — losing the
    response. It must degrade: warn, skip the cache, return the response."""
    from falaw.cache import cache_get

    nan_raw = {"images": [], "score": float("nan")}
    monkeypatch.setattr("falaw.cache.call_fal", lambda app, args, **kw: nan_raw)
    with pytest.warns(UserWarning, match="could not cache"):
        got = cached_call_fal("fal-ai/flux/dev", {"prompt": "p"})
    assert got is nan_raw
    assert cache_get("fal-ai/flux/dev", {"prompt": "p"}) is None


def test_a_failed_refresh_drops_the_stale_entry_instead_of_reserving_it(monkeypatch):
    """The second half of finding 2: on refresh=True a failed re-cache left
    the PRE-refresh entry serving on every later call — the refresh the
    caller explicitly asked for was silently undone."""
    from falaw.cache import cache_get, cache_put

    args = {"prompt": "p"}
    cache_put("fal-ai/flux/dev", args, {"images": ["old"]})
    assert cache_get("fal-ai/flux/dev", args) == {"images": ["old"]}

    monkeypatch.setattr(
        "falaw.cache.call_fal",
        lambda app, a, **kw: {"images": ["new"], "score": float("nan")},
    )
    with pytest.warns(UserWarning, match="could not cache"):
        got = cached_call_fal("fal-ai/flux/dev", args, refresh=True)
    assert got["images"] == ["new"]  # the billed fresh response survives
    assert cache_get("fal-ai/flux/dev", args) is None  # and stale stops serving


# --- adversarial-review fixes: dry-run keeps the isolation contract -----------


def test_dry_run_isolated_reports_a_junk_call_instead_of_raising():
    """Review finding 6: `execute_isolated(dry_run=True)` guarantees one
    outcome per call 'always' — a hand-built junk CallPlan must be that
    call's failed outcome, not the run's exception."""
    from falaw import execute_plan_isolated

    good = CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"prompt": "fine"},
        output_kind="image",
    )
    junk = CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"ref": _SameStr()},
        output_kind="image",
    )
    report = execute_plan_isolated(Plan(calls=(good, junk)), dry_run=True)
    assert len(report.outcomes) == 2
    assert report.outcomes[0].status == "succeeded"
    assert report.outcomes[1].status == "failed"
    assert isinstance(report.outcomes[1].error, FalNonCanonicalArgument)
