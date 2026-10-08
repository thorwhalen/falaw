"""Is a catalogued endpoint still deployed? (falaw#76)

fal retires endpoints without notice (``fal-ai/imagen4/preview/ultra`` answers
``404 Application "imagen4" not found``), and ``pick_model`` would keep
picking them. fal's OpenAPI endpoint answers 404 for a dead id and 200 for a
live one without a billed call or an API key, so one GET per id is a free
liveness probe.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from .registry import list_models

OPENAPI_URL = "https://fal.ai/api/openapi/queue/openapi.json"
"""``?endpoint_id=<id>`` selects the endpoint."""

StatusGetter = Callable[[str], int]
"""``url -> HTTP status``; injectable so tests never touch the network."""


def _http_status(url: str) -> int:
    from .errors import import_httpx

    httpx = import_httpx("checking fal.ai model liveness")
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        return client.get(url).status_code


def check_model_liveness(
    ids: Optional[Iterable[str]] = None,
    *,
    status_of: Optional[StatusGetter] = None,
) -> dict[str, bool]:
    """``{endpoint_id: is_live}`` for ``ids`` (default: every catalogued model).

    Only a 404 means dead; any other non-200 answer (rate limit, fal outage)
    raises rather than report a live model as dead, which would get it deleted.
    """
    get = status_of or _http_status
    ids = list(ids) if ids is not None else [m.id for m in list_models()]
    out: dict[str, bool] = {}
    for endpoint_id in ids:
        status = get(f"{OPENAPI_URL}?endpoint_id={endpoint_id}")
        if status not in (200, 404):
            raise RuntimeError(
                f"Unexpected HTTP {status} probing {endpoint_id}; refusing to "
                "guess whether it is live."
            )
        out[endpoint_id] = status == 200
    return out


def dead_models(
    ids: Optional[Iterable[str]] = None, *, status_of: Optional[StatusGetter] = None
) -> list[str]:
    """The ids from :func:`check_model_liveness` that are no longer deployed."""
    return [
        i
        for i, live in check_model_liveness(ids, status_of=status_of).items()
        if not live
    ]
