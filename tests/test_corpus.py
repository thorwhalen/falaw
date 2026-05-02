"""Tests for the corpus parser."""

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FALAW_DATA_DIR", str(tmp_path))
    from falaw.journal import _default_journal

    _default_journal.cache_clear()
    yield
    _default_journal.cache_clear()


def _write_corpus(tmp_path, content: str):
    p = tmp_path / "llms-full.txt"
    p.write_text(content)
    return str(p)


def test_extract_models_from_corpus_minimal(tmp_path):
    from falaw.corpus import extract_models_from_corpus

    path = _write_corpus(
        tmp_path,
        "preamble\n\n"
        "## High Quality Image Generation Models\n\n"
        "intro paragraph\n\n"
        "### Some Cool Pro\n"
        "- **Model**: `fal-ai/some/cool/pro`\n"
        "- **Purpose**: Make pretty pictures\n"
        "- **Features**: Detail, contrast\n\n"
        "## Video Generation Models\n\n"
        "### Image-To-Video Master\n"
        "- **Model**: `fal-ai/some/master/image-to-video`\n"
        "- **Purpose**: Animate stills\n\n"
        "### Text-To-Video Ultra\n"
        "- **Model**: `fal-ai/some/ultra/text-to-video`\n"
        "- **Purpose**: Generate videos from prompts\n\n"
        "## Section We Should Skip\n\n"
        "### Random Thing\n"
        "- **Model**: `fal-ai/random`\n",
    )
    records = list(extract_models_from_corpus(path))
    by_id = {r["id"]: r for r in records}
    assert "fal-ai/some/cool/pro" in by_id
    assert by_id["fal-ai/some/cool/pro"]["category"] == "image"
    assert by_id["fal-ai/some/cool/pro"]["quality_tier"] == "high"
    assert by_id["fal-ai/some/master/image-to-video"]["category"] == "image_to_video"
    assert by_id["fal-ai/some/master/image-to-video"]["quality_tier"] == "ultra"
    assert by_id["fal-ai/some/ultra/text-to-video"]["category"] == "text_to_video"
    # Unknown sections do not contribute records.
    assert "fal-ai/random" not in by_id


def test_refresh_models_dry_run_does_not_write(tmp_path, monkeypatch):
    from falaw import corpus as c
    from falaw.registry import _load_models, _models_path

    # Snapshot original models.json content.
    with open(_models_path()) as f:
        original = f.read()

    path = _write_corpus(
        tmp_path,
        "## Image Editing Tools\n\n"
        "### Brand New Edit Pro\n"
        "- **Model**: `fal-ai/brand/new/edit-pro`\n"
        "- **Purpose**: Test edit\n",
    )
    summary = c.refresh_models_from_corpus(path=path, write=False)
    assert summary["added"] >= 1
    assert "fal-ai/brand/new/edit-pro" in summary["added_ids"]

    # File untouched.
    with open(_models_path()) as f:
        assert f.read() == original

    # Cache untouched too --- new model should NOT yet be visible.
    _load_models.cache_clear()
    assert "fal-ai/brand/new/edit-pro" not in _load_models()


def test_refresh_models_with_write(tmp_path):
    from falaw import corpus as c
    from falaw.registry import _load_models, _models_path

    backup_path = tmp_path / "models.json.backup"
    with open(_models_path()) as f:
        original = f.read()
    backup_path.write_text(original)

    path = _write_corpus(
        tmp_path,
        "## Music & Audio Generation\n\n"
        "### Synthwave Pro\n"
        "- **Model**: `fal-ai/synthwave/pro`\n"
        "- **Purpose**: Generate retro tunes\n",
    )
    try:
        summary = c.refresh_models_from_corpus(path=path, write=True)
        assert summary["added"] >= 1
        assert summary["write"] is True
        models = _load_models()
        assert "fal-ai/synthwave/pro" in models
        assert models["fal-ai/synthwave/pro"].category == "music"
    finally:
        # Restore the seed file so other tests see the canonical content.
        with open(_models_path(), "w") as f:
            f.write(original)
        _load_models.cache_clear()
