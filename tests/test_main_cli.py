"""Tests for the `python -m falaw` CLI dispatch of `refresh-llm-rates` (falaw#56)."""

from __future__ import annotations

import falaw.__main__ as cli


def test_refresh_llm_rates_dispatches_with_write_false_by_default(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "refresh_llm_rates",
        lambda **kwargs: calls.append(kwargs) or {"write": kwargs.get("write", False)},
    )

    exit_code = cli.main(["refresh-llm-rates"])

    assert exit_code == 0
    assert calls == [{"write": False}]
    assert '"write": false' in capsys.readouterr().out


def test_refresh_llm_rates_dashdash_write_passes_write_true(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "refresh_llm_rates",
        lambda **kwargs: calls.append(kwargs) or {"write": kwargs.get("write", False)},
    )

    exit_code = cli.main(["refresh-llm-rates", "--write"])

    assert exit_code == 0
    assert calls == [{"write": True}]
    assert '"write": true' in capsys.readouterr().out
