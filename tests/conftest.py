"""Shared fixtures for the falaw test suite.

Two things nearly every offline test needs, and none should have to repeat:

1. **An isolated cache root.** falaw's cache, content store and url-index all
   hang off ``$FALAW_CACHE_DIR``. Without this fixture a test run writes into
   the developer's real ``~/.config/falaw/cache`` and leaks state between runs.

2. **A fake asset transport.** falaw content-addresses every media result, so
   it reads the bytes behind a fal URL (see :mod:`falaw.content` — a URL is
   neither unique-per-content nor durable, so it cannot be an identity).
   Offline tests serve stubbed fal responses carrying made-up URLs, so the
   HTTP fetcher is replaced by an in-memory map:

   - an unregistered URL yields deterministic synthetic bytes derived from the
     URL, so two different stub URLs behave like two genuinely different
     renders;
   - ``fake_assets.serve(url, data)`` pins explicit bytes — which is how a test
     makes two *different* URLs serve the *same* bytes, the case content
     addressing exists for;
   - ``fake_assets.fail(url)`` makes the URL 404, as an expired fal asset does.

A test marked ``live_api`` gets the real transport (and is skipped by default
via ``-m "not live_api"``).
"""

from __future__ import annotations

import urllib.error
from typing import Iterator, Optional

import pytest


def _synthetic_bytes(url: str) -> bytes:
    """Deterministic stand-in bytes for an unregistered URL."""
    return f"falaw-test-asset::{url}".encode("utf-8")


class FakeAssets:
    """An in-memory ``url -> bytes`` transport standing in for the network."""

    def __init__(self) -> None:
        self.by_url: dict[str, Optional[bytes]] = {}
        self.fetched: list[str] = []

    @staticmethod
    def synthetic(url: str) -> bytes:
        """The bytes an unregistered ``url`` serves."""
        return _synthetic_bytes(url)

    def serve(self, url: str, data: bytes) -> bytes:
        """Make ``url`` serve exactly ``data``."""
        self.by_url[url] = data
        return data

    def fail(self, url: str) -> None:
        """Make ``url`` 404, the way an expired fal asset does."""
        self.by_url[url] = None

    def chunks(self, url: str, *, chunk_size: int = 1 << 16) -> Iterator[bytes]:
        self.fetched.append(url)
        data = self.by_url.get(url, _synthetic_bytes(url))
        if data is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]
        for offset in range(0, len(data), chunk_size):
            yield data[offset : offset + chunk_size]


@pytest.fixture(autouse=True)
def _isolated_falaw_cache(tmp_path, monkeypatch):
    """Point every falaw on-disk store at a throwaway directory."""
    monkeypatch.setenv("FALAW_DATA_DIR", str(tmp_path / "falaw-data"))
    monkeypatch.setenv("FALAW_CACHE_DIR", str(tmp_path / "falaw-cache"))
    yield


@pytest.fixture(autouse=True)
def fake_assets(request, monkeypatch):
    """Replace :func:`falaw.content._http_chunks` with an in-memory transport."""
    if request.node.get_closest_marker("live_api") is not None:
        yield None
        return
    assets = FakeAssets()
    monkeypatch.setattr("falaw.content._http_chunks", assets.chunks)
    yield assets
