"""Smoke tests for operations: monkeypatch fal_client.subscribe so no API key is needed."""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolated_journal(tmp_path, monkeypatch):
    # Re-route the journal so failures during operation tests don't pollute
    # the user's real journal.
    monkeypatch.setenv("FALAW_DATA_DIR", str(tmp_path))
    # Reset the lru_cache that holds the default journal.
    from falaw.journal import _default_journal

    _default_journal.cache_clear()
    yield
    _default_journal.cache_clear()


def test_generate_image_calls_fal(monkeypatch):
    import fal_client

    captured = {}

    def fake_subscribe(application, *, arguments, **_kw):
        captured["application"] = application
        captured["arguments"] = arguments
        return {
            "images": [
                {
                    "url": "http://x/i.png",
                    "width": 1024,
                    "height": 1024,
                    "content_type": "image/png",
                }
            ]
        }

    monkeypatch.setattr(fal_client, "subscribe", fake_subscribe)
    from falaw import generate_image

    r = generate_image("a fox", quality="balanced")
    assert captured["application"] == "fal-ai/flux/dev"
    assert captured["arguments"]["prompt"] == "a fox"
    assert r.first.url == "http://x/i.png"


def test_generate_image_journals_on_error(monkeypatch, tmp_path):
    import fal_client

    def boom(application, *, arguments, **_kw):
        raise RuntimeError("simulated fal failure")

    monkeypatch.setattr(fal_client, "subscribe", boom)
    from falaw import generate_image, journal

    with pytest.raises(RuntimeError):
        generate_image("anything", quality="fast")
    entries = journal.recent(50)
    assert any(e.kind == "issue" and "call_fal" in e.tags for e in entries), (
        "expected call_fal failure to be journaled, got: " + repr(entries)
    )
