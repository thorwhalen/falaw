"""Wrapper over `fal_client.subscribe` with progress logging and auto-journaling.

Operations should call `call_fal` rather than `fal_client.subscribe` directly,
so we get one place to:

* attach progress callbacks,
* auto-journal failures (so the next agent learns from them),
* layer retries / backoff later without changing call sites.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Optional

from .journal import _default_journal


def call_fal(
    application: str,
    arguments: Mapping[str, Any],
    *,
    on_log: Optional[Callable[[str], None]] = None,
    with_logs: bool = True,
    journal_errors: bool = True,
) -> dict:
    """Call a fal model via fal_client.subscribe.

    Args:
        application: fal model id (e.g. ``"fal-ai/flux/dev"``).
        arguments: Input arguments. Keys depend on the model.
        on_log: Progress callback. Defaults to ``print``.
        with_logs: Pass through to fal_client; when True the model streams logs.
        journal_errors: When True, exceptions are recorded as journal issues
            before being re-raised. The journal entry includes the application
            id and arguments so future agents can recognize the same trap.

    Returns:
        The raw response dict from the model.
    """
    import fal_client  # lazy: keep import out of `from pyfal import ...`

    log = on_log if on_log is not None else print

    def _on_queue_update(update):
        if isinstance(update, fal_client.InProgress):
            for entry in update.logs or ():
                msg = entry.get("message") if isinstance(entry, dict) else None
                if msg:
                    log(msg)

    started = time.time()
    try:
        return fal_client.subscribe(
            application,
            arguments=dict(arguments),
            with_logs=with_logs,
            on_queue_update=_on_queue_update,
        )
    except Exception as exc:
        if journal_errors:
            _default_journal().append(
                kind="issue",
                text=f"call_fal({application!r}) failed: {exc!r}",
                tags=("call_fal", "error"),
                context={
                    "application": application,
                    "arguments": dict(arguments),
                    "duration_s": time.time() - started,
                },
            )
        raise
