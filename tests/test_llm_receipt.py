"""Tests for falaw#50 option B — the eager LLM path finally keeps a record.

What these pin:

* the receipt reports measured chars, best-effort tokens (OpenAI and
  Anthropic usage shapes; None — never zero — when the response carries no
  usage block);
* a cache hit is a $0.00 receipt with ``cost_source="cache_hit"``; a fresh
  call carries the registry estimate with its kind named;
* ``llm_complete`` delegates to the receipt variant — one
  argument-construction site, so the two spellings share one cache entry
  (proved by a cross-spelling cache hit);
* the receipt variant is library surface only, NOT a registered tool.
"""

from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("FALAW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FALAW_CACHE_DIR", str(tmp_path / "cache"))
    from falaw.events import clear_subscribers
    from falaw.journal import _default_journal

    _default_journal.cache_clear()
    clear_subscribers()
    yield
    clear_subscribers()
    _default_journal.cache_clear()


def _install_fake_fal(monkeypatch, *, response):
    captured: list[dict] = []

    def subscribe(application, *, arguments, with_logs, on_queue_update):
        captured.append({"application": application, "arguments": dict(arguments)})
        return response

    fake = types.SimpleNamespace(
        InProgress=type("InProgress", (), {"__init__": lambda self, logs: None}),
        subscribe=subscribe,
    )
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    return captured


OPENAI_SHAPED = {
    "choices": [{"message": {"content": "A terse summary."}}],
    "usage": {"prompt_tokens": 42, "completion_tokens": 7},
}

ANTHROPIC_SHAPED = {
    "output": "Another answer.",
    "usage": {"input_tokens": 10, "output_tokens": 3},
}

NO_USAGE = {"output": "Bare answer."}


def test_receipt_measures_chars_and_reads_openai_usage(monkeypatch):
    _install_fake_fal(monkeypatch, response=OPENAI_SHAPED)
    from falaw import llm_complete_with_receipt

    text, r = llm_complete_with_receipt("Summarize.", system="Be terse.")
    assert text == "A terse summary."
    assert r.chars_in == len("Summarize.") + len("Be terse.")
    assert r.chars_out == len(text)
    assert (r.tokens_in, r.tokens_out) == (42, 7)
    assert r.cache_hit is False
    assert r.application == "fal-ai/any-llm"
    assert r.model.startswith("anthropic/")  # the default routed model


def test_receipt_reads_anthropic_usage_shape(monkeypatch):
    _install_fake_fal(monkeypatch, response=ANTHROPIC_SHAPED)
    from falaw import llm_complete_with_receipt

    _, r = llm_complete_with_receipt("q")
    assert (r.tokens_in, r.tokens_out) == (10, 3)


def test_receipt_reports_none_tokens_when_unrecorded(monkeypatch):
    """None means the provider recorded nothing — never invent a zero."""
    _install_fake_fal(monkeypatch, response=NO_USAGE)
    from falaw import llm_complete_with_receipt

    _, r = llm_complete_with_receipt("q")
    assert (r.tokens_in, r.tokens_out) == (None, None)


def test_fresh_call_carries_the_registry_estimate(monkeypatch):
    _install_fake_fal(monkeypatch, response=NO_USAGE)
    from falaw import llm_complete_with_receipt
    from falaw.registry import get_model

    _, r = llm_complete_with_receipt("q")
    record = get_model("fal-ai/any-llm")
    assert record.cost_estimate is not None  # the premise of this pin
    assert r.estimated_cost_usd == pytest.approx(record.cost_estimate.amount)
    assert r.cost_source == f"registry:{record.cost_estimate.kind}"


def test_cache_hit_is_a_zero_dollar_receipt(monkeypatch):
    _install_fake_fal(monkeypatch, response=NO_USAGE)
    from falaw import llm_complete_with_receipt

    _, first = llm_complete_with_receipt("same question")
    assert first.cache_hit is False
    _, second = llm_complete_with_receipt("same question")
    assert second.cache_hit is True
    assert second.estimated_cost_usd == 0.0
    assert second.cost_source == "cache_hit"


def test_llm_complete_and_receipt_variant_share_one_cache_entry(monkeypatch):
    """The delegation is what guarantees one argument-construction site:
    a plain llm_complete call must HIT the cache entry the receipt variant
    wrote, and vice versa — two spellings, one call identity."""
    captured = _install_fake_fal(monkeypatch, response=NO_USAGE)
    from falaw import llm_complete, llm_complete_with_receipt

    llm_complete_with_receipt("shared", system="s")
    assert len(captured) == 1
    out = llm_complete("shared", system="s")
    assert out == "Bare answer."
    assert len(captured) == 1, "the plain spelling hit the receipt call's entry"


def test_receipt_variant_is_not_a_registered_tool():
    """Library surface only — the tool surface keeps the one
    string-returning llm_complete (no CONTRACT 7 / snapshot movement)."""
    import falaw.operations.llm  # noqa: F401 — ensure registration ran
    from falaw.registry import list_tools

    names = {t.name for t in list_tools()}
    assert "llm_complete" in names
    assert "llm_complete_with_receipt" not in names
