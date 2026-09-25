"""The committed ``schema/`` directory is a fresh export.

``ts/`` (the npm package ``falaw``) is generated from and tested against
``schema/``. If a dataclass, the catalogue, a cost rule, the response parser or
the canonical byte-form changes without ``python -m falaw export-schema`` being
re-run, the TypeScript side keeps building against the old contract and nothing
on that side can notice. So the drift guard lives here, on the side that changed.
"""

from __future__ import annotations

import json
from pathlib import Path

import falaw.__main__ as cli
from falaw.registry import models_table_version
from falaw.schema_export import export_schema

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "schema"


def _files(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*.json"))
    }


def test_committed_schema_is_up_to_date(tmp_path):
    export_schema(tmp_path / "schema")
    fresh = _files(tmp_path / "schema")
    committed = _files(SCHEMA_DIR)
    stale = sorted(n for n in fresh | committed if fresh.get(n) != committed.get(n))
    assert not stale, (
        f"schema/ is stale for {stale}; run `python -m falaw export-schema` and commit."
    )


def test_export_is_deterministic(tmp_path):
    export_schema(tmp_path / "a")
    export_schema(tmp_path / "b")
    assert _files(tmp_path / "a") == _files(tmp_path / "b")


def test_the_copied_catalogue_carries_the_same_table_version():
    """``CostBasis.table_version`` is a digest of the bytes; the copy must match."""
    import hashlib

    from falaw.base import TABLE_VERSION_CHARS

    digest = hashlib.sha256((SCHEMA_DIR / "models.json").read_bytes()).hexdigest()
    assert digest[:TABLE_VERSION_CHARS] == models_table_version()
    constants = json.loads((SCHEMA_DIR / "constants.json").read_text())
    assert constants["models_table_version"] == models_table_version()


def test_every_plan_fixture_prices_from_the_catalogue():
    """A fixture whose basis names another table would pin the wrong pricer."""
    plans = json.loads((SCHEMA_DIR / "fixtures" / "plans.json").read_text())
    for case in plans["calls"]:
        basis = case["expected"]["cost_basis"]
        assert basis["pricer"] == "model_catalogue"
        assert basis["table_version"] == models_table_version()
        assert case["expected"]["cache_status"] == "unknown"  # a browser peeks no cache


def test_cli_export_schema_writes_the_directory(tmp_path, capsys):
    assert cli.main(["export-schema", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "call-plan.schema.json").exists()
    assert "constants.json" in capsys.readouterr().out
