"""falaw#15 — `CallPlan.backend` dispatches through a real registry.

Nothing above `falaw.Plan` may know a specific backend exists (video_gen's
architectural prime directive): a `CallPlan(backend=...)` must always be
priceable, cacheable, dry-runnable and artifact-converting — never a "Do
whatever this Transform does" escape hatch that returns `$0.00` on a real
spend. These tests exercise a *second*, fake backend end-to-end through
`execute_plan`/`execute_plan_isolated` to prove the registry, not just the
default "fal" path, actually works.
"""

from __future__ import annotations

import pytest

from falaw import CallPlan, Plan, execute_plan, execute_plan_isolated
from falaw.backends import backends, get_backend_executor


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("FALAW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FALAW_CACHE_DIR", str(tmp_path / "cache"))


@pytest.fixture
def fake_backend():
    """Register a throwaway 'fake' backend for one test, then unregister it.

    A minimal, non-fal executor: it never imports `fal_client`, so a test
    using only this backend proves the dispatch reaches *something other
    than* the hardcoded fal path — the exact gap the registry closes.
    """
    calls: list[dict] = []

    def _executor(application, arguments, *, on_event=None):
        calls.append({"application": application, "arguments": dict(arguments)})
        return {"images": [{"url": "http://fake-backend/out.png"}]}

    backends.register("fake", _executor)
    try:
        yield calls
    finally:
        del backends["fake"]


def _fake_plan() -> Plan:
    return Plan(
        calls=(
            CallPlan(
                tool="generate_image",
                application="model://fake/whatever",
                backend="fake",
                arguments={"prompt": "a tiger"},
                output_kind="image",
                estimated_cost_usd=0.01,
            ),
        )
    )


def test_get_backend_executor_knows_fal_by_default():
    from falaw.core import call_fal

    assert get_backend_executor("fal") is not call_fal  # a wrapper, not identity
    assert callable(get_backend_executor("fal"))


def test_get_backend_executor_raises_with_the_known_names_for_an_unknown_backend():
    with pytest.raises(KeyError) as e:
        get_backend_executor("comfyui-does-not-exist")
    assert "comfyui-does-not-exist" in str(e.value)
    assert "'fal'" in str(e.value)  # the known-names list names what IS there


def test_execute_plan_dispatches_a_registered_non_fal_backend(fake_backend):
    """The gap this issue exists to close: a backend reachable only by
    hand-rolling execution used to bypass the cache, the cost accounting and
    the artifact converter entirely. Here it goes through all three."""
    artifacts = execute_plan(_fake_plan(), use_cache=False)
    assert len(fake_backend) == 1
    assert fake_backend[0]["application"] == "model://fake/whatever"
    assert len(artifacts) == 1
    assert artifacts[0].kind == "image"
    assert artifacts[0].url == "http://fake-backend/out.png"


def test_execute_plan_caches_a_non_fal_backend_call_too(fake_backend):
    """Priceable, cacheable, artifact-converting — the four-point spec.
    A second execute of the same fake-backend plan must not re-call it."""
    execute_plan(_fake_plan())
    fake_backend.clear()
    execute_plan(_fake_plan())
    assert fake_backend == [], "second execute should hit the cache"


def test_dry_run_never_reaches_any_backend_executor(fake_backend):
    """dry_run=True must not call fal — or any other backend — under any
    circumstance, regardless of which one the plan names."""
    artifacts = execute_plan(_fake_plan(), dry_run=True)
    assert fake_backend == []
    assert len(artifacts) == 1
    assert artifacts[0].url is None  # synthetic


def test_a_backend_named_by_a_call_but_never_registered_fails_that_call_only(
    fake_backend,
):
    """execute_isolated's per-call failure isolation must cover a bad
    `backend` string exactly like any other per-call failure — one call's
    typo does not discard the rest of a fan-out."""
    good = CallPlan(
        tool="generate_image",
        application="model://fake/whatever",
        backend="fake",
        arguments={"prompt": "a tiger"},
        output_kind="image",
    )
    typo = CallPlan(
        tool="generate_image",
        application="model://fake/whatever",
        backend="fkae",  # typo
        arguments={"prompt": "a cat"},
        output_kind="image",
    )
    report = execute_plan_isolated(Plan(calls=(good, typo)), use_cache=False)
    assert report.outcomes[0].status == "succeeded"
    assert report.outcomes[1].status == "failed"
    assert isinstance(report.outcomes[1].error, KeyError)
    assert "fkae" in str(report.outcomes[1].error)


@pytest.mark.parametrize("use_cache", [False, True], ids=["uncached", "cached"])
def test_a_bad_backend_is_isolated_under_a_real_thread_pool_too(
    fake_backend, use_cache
):
    """Adversarial review of falaw#15: the shipped isolation test above only
    ran at concurrency=1 (`_InlineExecutor`) — the module's own docstring
    warns that sequential and concurrent paths can diverge and only one is
    ever covered by a given test. `concurrency=2` here forces the real
    `ThreadPoolExecutor` for both the uncached branch (bad backend raises in
    `get_backend_executor` directly) and the cached branch (raises inside
    `cached_call_fal` after a miss) — one bad call must not hang the pool,
    corrupt a sibling's outcome, or escape per-call isolation.
    """
    good = CallPlan(
        tool="generate_image",
        application="model://fake/whatever",
        backend="fake",
        arguments={"prompt": "a tiger"},
        output_kind="image",
    )
    typo = CallPlan(
        tool="generate_image",
        application="model://fake/whatever",
        backend="fkae",  # typo — independent of `good`, so both run concurrently
        arguments={"prompt": "a cat"},
        output_kind="image",
    )
    report = execute_plan_isolated(
        Plan(calls=(good, typo)), use_cache=use_cache, concurrency=2
    )
    assert report.outcomes[0].status == "succeeded"
    assert report.outcomes[0].artifact.url == "http://fake-backend/out.png"
    assert report.outcomes[1].status == "failed"
    assert isinstance(report.outcomes[1].error, KeyError)
    assert "fkae" in str(report.outcomes[1].error)
    assert len(fake_backend) == 1  # only the good call ever reached the executor


def test_registering_a_backend_under_an_existing_name_raises():
    """`on_conflict="error"` — a misconfigured plugin must fail loudly rather
    than silently shadow the built-in fal executor."""
    from xdol.registry import RegistryConflict

    with pytest.raises(RegistryConflict):
        backends.register("fal", lambda *a, **k: {})
