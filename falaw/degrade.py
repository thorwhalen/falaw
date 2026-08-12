"""Where falaw sends "I carried on, but you should know" — one collection point.

falaw deliberately degrades rather than failing in several places: a failed
asset fetch becomes a URL-only artifact instead of discarding a render fal has
already billed, and an unreadable origin falls back to bytes already in the
store instead of losing the artifact. Every one of those is a decision the
caller would want to hear about, and none of them should stop the run.

``warnings.warn`` alone is the wrong channel for two reasons, both learned:

* **It deduplicates.** Python's default filter shows a given message once per
  location per process, so on a long-lived server the second and every
  subsequent stale serve of the same URL is *silent*.
* **It cannot be collected.** Under ``execute_plan(concurrency=N)`` a
  speculative probe's complaint interleaves with real ones, and
  ``warnings.catch_warnings`` is documented as not thread-safe — it mutates
  process-global filter state, so one call suppressing its own noise would
  suppress another call's genuine warning at random.

Hence a :class:`~contextvars.ContextVar` sink. Set inside a unit of work it is
visible only to that unit (each pool task runs in its own context copy), and
when nothing has set one the message falls through to ``warnings.warn``.

This lives in its own module, below both :mod:`falaw.plan` and
:mod:`falaw.content`, because **both** produce degradations and neither may
import the other at module scope.
"""

from __future__ import annotations

import warnings
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional


__all__ = ["deferred_degrade_warnings", "emit_degradation"]


DEGRADE_WARNING_SINK: "ContextVar[Optional[list]]" = ContextVar(
    "falaw_degrade_warning_sink", default=None
)
"""The list collecting degradation messages, or ``None`` to warn directly."""


@contextmanager
def deferred_degrade_warnings() -> Iterator[list]:
    """Collect degradation messages into a list instead of warning."""
    sink: list = []
    token = DEGRADE_WARNING_SINK.set(sink)
    try:
        yield sink
    finally:
        DEGRADE_WARNING_SINK.reset(token)


def emit_degradation(message: str, *, stacklevel: int = 3) -> None:
    """Report that falaw degraded rather than failed.

    Into the active sink if there is one, else straight to ``warnings.warn``.
    Every degradation in falaw goes through here so that none of them can be
    the one that escapes collection — the more severe the degradation, the
    worse it is for it to be the escapee.
    """
    sink = DEGRADE_WARNING_SINK.get()
    if sink is None:
        warnings.warn(message, UserWarning, stacklevel=stacklevel)
    else:
        sink.append(message)
