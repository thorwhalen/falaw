"""Tests for :func:`falaw.plan_hash` — the plan-scoped structural idempotency key.

The contract: an identical structural plan re-hashes to the same value (stable),
while any structural difference (call ``app`` / ``args`` / ``tool``, or call
order) produces a different hash. This is what lets a job manager dedup
double-submits and replay a resumed render for free.
"""

import falaw
from falaw import CallPlan, Plan, plan_hash


def _image_call(prompt="a tiger"):
    return CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"prompt": prompt, "image_size": "landscape_4_3"},
        output_kind="image",
        estimated_cost_usd=0.025,
        cache_status="miss",
    )


def _video_call(image_ref="<from 0>"):
    return CallPlan(
        tool="image_to_video",
        application="fal-ai/minimax/hailuo-02/pro/image-to-video",
        arguments={"image_url": image_ref},
        output_kind="video",
        estimated_cost_usd=0.50,
        cache_status="miss",
    )


def test_exported_from_package_root():
    assert falaw.plan_hash is plan_hash


def test_identical_structural_plan_rehashes_stably():
    plan_a = Plan(calls=(_image_call(), _video_call()))
    plan_b = Plan(calls=(_image_call(), _video_call()))
    # Distinct objects, identical structure → identical hash.
    assert plan_a is not plan_b
    assert plan_hash(plan_a) == plan_hash(plan_b)
    # And it's a stable sha256 hex digest.
    h = plan_hash(plan_a)
    assert isinstance(h, str) and len(h) == 64
    assert plan_hash(plan_a) == h  # deterministic across calls


def test_argument_key_order_does_not_matter():
    """sort_keys canonicalization → argument insertion order is irrelevant."""
    c1 = CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"prompt": "a tiger", "seed": 7},
        output_kind="image",
    )
    c2 = CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"seed": 7, "prompt": "a tiger"},
        output_kind="image",
    )
    assert plan_hash(Plan(calls=(c1,))) == plan_hash(Plan(calls=(c2,)))


def test_different_args_differ():
    p1 = Plan(calls=(_image_call(prompt="a tiger"),))
    p2 = Plan(calls=(_image_call(prompt="a lion"),))
    assert plan_hash(p1) != plan_hash(p2)


def test_different_application_differs():
    base = _image_call()
    other = CallPlan(
        tool=base.tool,
        application="fal-ai/flux/schnell",  # different model
        arguments=dict(base.arguments),
        output_kind=base.output_kind,
    )
    assert plan_hash(Plan(calls=(base,))) != plan_hash(Plan(calls=(other,)))


def test_different_tool_differs():
    base = _image_call()
    other = CallPlan(
        tool="edit_image",  # different tool, same app + args
        application=base.application,
        arguments=dict(base.arguments),
        output_kind=base.output_kind,
    )
    assert plan_hash(Plan(calls=(base,))) != plan_hash(Plan(calls=(other,)))


def test_call_order_matters():
    img, vid = _image_call(), _video_call()
    assert plan_hash(Plan(calls=(img, vid))) != plan_hash(Plan(calls=(vid, img)))


def test_cost_and_cache_status_do_not_change_the_hash():
    """The idempotency key is structural — only {app, args, tool} — so a plan
    re-priced or re-cache-checked (same structural request) dedups to the same
    job."""
    cheap = CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"prompt": "a tiger"},
        output_kind="image",
        estimated_cost_usd=0.01,
        cache_status="miss",
    )
    repriced = CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"prompt": "a tiger"},
        output_kind="image",
        estimated_cost_usd=0.99,  # re-priced
        cache_status="hit",  # re-cache-checked
    )
    assert plan_hash(Plan(calls=(cheap,))) == plan_hash(Plan(calls=(repriced,)))


def test_empty_plan_is_stable():
    assert plan_hash(Plan(calls=())) == plan_hash(Plan())


def test_backend_changes_the_hash_but_only_when_non_default():
    """falaw#15: `backend` must join `plan_hash` — a plan for a second
    backend must never dedup against the structurally-identical fal plan, or
    a job manager replays the wrong backend's cached result as if it were
    this plan's own. But it must join it the SAFE way: only when non-default,
    so every plan made of today's (implicitly-"fal") calls keeps its exact
    pre-#15 hash — sibling of test_cost_and_cache_status_do_not_change_the_hash.
    """
    fal_call = _image_call()
    explicit_fal = CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"prompt": "a tiger", "image_size": "landscape_4_3"},
        output_kind="image",
        backend="fal",  # explicit, not omitted — must hash identically
    )
    comfy_call = CallPlan(
        tool="generate_image",
        application="fal-ai/flux/dev",
        arguments={"prompt": "a tiger", "image_size": "landscape_4_3"},
        output_kind="image",
        backend="comfyui",
    )
    assert plan_hash(Plan(calls=(fal_call,))) == plan_hash(Plan(calls=(explicit_fal,)))
    assert plan_hash(Plan(calls=(fal_call,))) != plan_hash(Plan(calls=(comfy_call,)))


def test_backend_changes_the_per_call_cache_key_the_same_way():
    """The other half of the same invariant, at the cache-key layer — if only
    `plan_hash` changed, two backends running the 'same' nominal operation
    would share a cache entry and one would return the other's artifact."""
    from falaw.cache import _key

    fal_key = _key("fal-ai/flux/dev", {"prompt": "a tiger"})
    assert fal_key == _key("fal-ai/flux/dev", {"prompt": "a tiger"}, backend="fal")
    assert fal_key != _key("fal-ai/flux/dev", {"prompt": "a tiger"}, backend="comfyui")
