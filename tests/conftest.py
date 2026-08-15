"""Shared fixtures for the falaw test suite.

falaw ships its own offline fixtures as :mod:`falaw.testing` — the module that
three repos' worth of hand-rolled copies became (thorwhalen/falaw#27) — so this
file re-exports them rather than defining a fourth. Deliberate dogfooding: if
the one-line re-export the README promises consumers ever stops working, it
breaks here first.

- ``isolated_falaw_cache`` — every falaw on-disk store under ``tmp_path``.
- ``fake_assets`` — falaw's asset transport served from memory.
- ``no_outbound_network`` — refuses *and records* any non-loopback connection.

All three are autouse and all three step aside for a test marked ``live_api``,
which is *gated* below rather than merely conventional: the CI command is a
bare ``pytest``, so a marker nobody enforces is a paid API call one commit
away from running on every push.
"""

from __future__ import annotations

import os

import pytest

from falaw.testing import (  # noqa: F401  (autouse fixtures — imported for effect)
    FakeAssets,
    fake_assets,
    isolated_falaw_cache,
    no_outbound_network,
)

# ``pytester`` runs a nested pytest session, which is the only way to observe a
# fixture that fails at *teardown* — see ``test_the_fixture_fails_the_test_at
# _teardown``, the guard on the reporting half of the network backstop.
pytest_plugins = ["pytester"]


def pytest_configure(config):
    """Register the marker that opts a test out of the offline fixtures."""
    config.addinivalue_line(
        "markers",
        "live_api: test calls the real fal.ai API. Gets the real asset "
        "transport and no network guard; runs ONLY with FALAW_LIVE_API=1 "
        "(and FAL_KEY) set, never in CI.",
    )


def _live_api_skip_reason() -> str | None:
    """Why ``live_api`` tests should not run here, or ``None`` to run them.

    Opt-IN by polarity, not opt-out: a developer shell with FAL_KEY exported
    and no CI variable is indistinguishable from an environment that never
    intended to spend, so "key present" must not be the switch. The gate the
    fleet converged on after a real near-spend (reelee#260's family): a
    bare ``pytest`` is always offline; ``FALAW_LIVE_API=1`` is the explicit
    "yes, bill me" signal. The absent-variable case is the safe case.
    """
    if os.environ.get("CI"):
        return "live_api tests never run in CI (would risk real spend)"
    if os.environ.get("FALAW_LIVE_API") != "1":
        return (
            "live_api tests are opt-in: set FALAW_LIVE_API=1 (and FAL_KEY) "
            "to run them — a bare pytest must never be able to spend"
        )
    if not os.environ.get("FAL_KEY"):
        return "live_api tests need FAL_KEY in the environment"
    return None


def pytest_collection_modifyitems(config, items):
    """Skip ``live_api`` tests unless this machine is allowed to spend."""
    reason = _live_api_skip_reason()
    if reason is None:
        return
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if "live_api" in item.keywords:
            item.add_marker(skip)
