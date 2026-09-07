"""Tests for the third cache mode — ``refresh=True``: skip the read, keep the write.

The defect these pin down (falaw#49, observed downstream as thorwhalen/reelee#384):
``use_cache`` was one flag doing two jobs, so a caller who reached for
``use_cache=False`` to mean *"ignore any cached answer"* also got *"and discard
the fresh one"*. That turns "re-verify this plan" into a guaranteed double
charge, because the next consumer re-bills the result the forced run already
paid for and threw away.

Every fal call here goes through a **counting** fake ``fal_client``, so the
assertions are on vendor-call counts — the unit the defect is measured in — not
on cache internals. Nothing reaches a paid API; the suite's autouse offline
fixtures (``tests/conftest.py``) cover the asset transport and the on-disk
stores.
"""

from __future__ import annotations

import sys
import types

import pytest

from falaw.plan import CallPlan, Plan, execute, execute_isolated

IMAGE_APPLICATION = "fal-ai/flux/dev"
VIDEO_APPLICATION = "fal-ai/hailuo/image-to-video"


def _install_counting_fal(monkeypatch) -> list[str]:
    """Install a fake ``fal_client`` that records one entry per vendor call.

    Returns the (live) list of applications called, in order. Its ``len`` is
    the spend: every entry is a call falaw would have been billed for.
    """
    called: list[str] = []

    def subscribe(application, *, arguments, with_logs, on_queue_update):
        called.append(application)
        if "image-to-video" in application:
            return {
                "video": {
                    "url": f"https://fal.media/v{len(called)}.mp4",
                    "content_type": "video/mp4",
                }
            }
        return {
            "images": [
                {
                    "url": f"https://fal.media/i{len(called)}.png",
                    "content_type": "image/png",
                }
            ]
        }

    fake = types.SimpleNamespace(
        InProgress=type("InProgress", (), {"__init__": lambda self, logs: None}),
        subscribe=subscribe,
    )
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    return called


def _image_plan(prompt: str = "a red panda") -> Plan:
    return Plan(
        calls=(
            CallPlan(
                tool="generate_image",
                application=IMAGE_APPLICATION,
                arguments={"prompt": prompt},
                output_kind="image",
                estimated_cost_usd=0.025,
            ),
        )
    )


def _chained_plan(prompt: str = "a red panda") -> Plan:
    """An image feeding an image-to-video — the shape with no caller workaround.

    Pre-dropping cache entries before an ordinary ``use_cache=True`` run is the
    workaround reelee considered and rejected: a chained call's *key* arguments
    hold ``"<from 0>"``, which cannot be resolved until call 0 has executed, so
    there is no key to drop ahead of time.
    """
    return Plan(
        calls=(
            CallPlan(
                tool="generate_image",
                application=IMAGE_APPLICATION,
                arguments={"prompt": prompt},
                output_kind="image",
                estimated_cost_usd=0.025,
            ),
            CallPlan(
                tool="image_to_video",
                application=VIDEO_APPLICATION,
                arguments={"image_url": "<from 0>"},
                output_kind="video",
                estimated_cost_usd=0.50,
            ),
        )
    )


# --- the regression: a forced re-run must not be a double spend --------------


def test_refresh_run_leaves_its_paid_result_in_the_cache(monkeypatch):
    """The reelee#384 sequence, in vendor calls: forced replay, then a consumer.

    Cold cache. The forced run re-executes (1 call) and **keeps** what it paid
    for, so the ordinary follow-up run — the ``run_stage`` in reelee's trace —
    is served from the cache and bills nothing. Total: 1.

    This is the assertion that fails if ``refresh=True`` is collapsed back into
    ``use_cache=False``: that mode never reaches ``cached_call_fal``, so it
    writes nothing, the follow-up re-bills, and the total is 2.
    """
    called = _install_counting_fal(monkeypatch)
    plan = _image_plan()

    execute(plan, use_cache=True, refresh=True)
    assert len(called) == 1, "the forced run itself executes exactly once"

    execute(plan)

    assert len(called) == 1, (
        "the forced run's paid result must be reusable — a follow-up run that "
        "re-bills means the re-run discarded what it bought (falaw#49)"
    )


def test_refresh_over_a_chained_plan_caches_every_call(monkeypatch):
    """The placeholder case: both entries survive, including the downstream one.

    The downstream call is keyed on the upstream's *content* hash, so this also
    proves the key arguments are still resolved under ``refresh`` — a mode that
    fell back to the wire arguments would key the video on a fal URL that is
    minted fresh per upload, and could never be hit again.
    """
    called = _install_counting_fal(monkeypatch)
    plan = _chained_plan()

    execute(plan, use_cache=True, refresh=True)
    assert len(called) == 2, "two calls in the plan, two vendor calls"

    execute(plan)

    assert len(called) == 2, "both entries — image and video — must be reusable"


def test_refresh_skips_the_read_so_a_warm_cache_still_re_executes(monkeypatch):
    """The other half of the mode: it is a *re-run*, not a no-op on a warm cache."""
    called = _install_counting_fal(monkeypatch)
    plan = _image_plan()

    execute(plan)
    assert len(called) == 1

    execute(plan)
    assert len(called) == 1, "the default mode reads the cache"

    execute(plan, use_cache=True, refresh=True)
    assert len(called) == 2, "refresh must ignore the warm entry and re-execute"


# --- the existing mode keeps its meaning ------------------------------------


def test_use_cache_false_still_writes_nothing(monkeypatch):
    """``use_cache=False`` is unchanged: it touches the cache at neither end.

    Silently redefining it would be worse than the gap this issue closes —
    "do not touch the cache at all" is a legitimate thing to ask for, and it is
    the only mode that provides it.
    """
    called = _install_counting_fal(monkeypatch)
    plan = _image_plan()

    execute(plan, use_cache=False)
    assert len(called) == 1

    execute(plan)

    assert len(called) == 2, (
        "use_cache=False must keep writing nothing — a follow-up run re-bills"
    )


def test_use_cache_false_still_ignores_a_warm_cache(monkeypatch):
    """And it still skips the read, so it remains a genuine re-run."""
    called = _install_counting_fal(monkeypatch)
    plan = _image_plan()

    execute(plan)
    assert len(called) == 1

    execute(plan, use_cache=False)
    assert len(called) == 2


def test_default_mode_reads_and_writes(monkeypatch):
    """The default is unmoved: first run bills, second run does not."""
    called = _install_counting_fal(monkeypatch)
    plan = _image_plan()

    execute(plan)
    execute(plan)

    assert len(called) == 1


# --- the fourth corner has no meaning ----------------------------------------


def test_refresh_with_use_cache_off_raises(monkeypatch):
    """``use_cache=False, refresh=True`` is contradictory, so it is refused.

    There is no key to write under when the cache is off, and picking one of
    the two intents silently would hand the caller a spend policy they did not
    ask for.
    """
    called = _install_counting_fal(monkeypatch)

    with pytest.raises(ValueError, match="refresh=True requires use_cache=True"):
        execute(_image_plan(), use_cache=False, refresh=True)

    assert called == [], "the refusal must happen before anything is billed"


def test_refresh_with_use_cache_off_raises_from_execute_isolated(monkeypatch):
    """The isolated executor refuses it too — this is a run-level configuration
    error, not a per-call failure to be reported as an outcome."""
    _install_counting_fal(monkeypatch)

    with pytest.raises(ValueError, match="refresh=True requires use_cache=True"):
        execute_isolated(_image_plan(), use_cache=False, refresh=True)


# --- the seam is available on both executors ---------------------------------


def test_execute_isolated_honours_refresh(monkeypatch):
    """``execute_plan_isolated`` gets the same three modes as ``execute_plan``."""
    called = _install_counting_fal(monkeypatch)
    plan = _image_plan()

    report = execute_isolated(plan, use_cache=True, refresh=True)
    assert report.is_complete
    assert len(called) == 1

    execute(plan)
    assert len(called) == 1, "the isolated executor writes what it paid for too"


def test_refresh_is_keyword_only():
    """A positional third argument must not silently land on ``refresh``."""
    with pytest.raises(TypeError):
        execute(_image_plan(), None, False, True, True)  # type: ignore[misc]
