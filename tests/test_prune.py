"""Tests for falaw.prune — cache capacity accounting and eviction (falaw#22).

The load-bearing assertions here are not "does it delete files" but:

* a prune is a **dry run** unless asked otherwise, and an unbounded one is
  refused rather than guessed at;
* ``rebillable_entries`` is *correct*, per area — it is the number a human
  reads before deciding to spend money, and each area computes it differently;
* an unprovable age is never treated as evidence of staleness.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from falaw import cache, prune


# --- helpers ----------------------------------------------------------------


def _put_blob(data: bytes, *, age_s: float = 0.0) -> str:
    """Write ``data`` into the default content store; return its content hash."""
    from falaw.content import default_content_store

    store = default_content_store()
    content_hash = store.put_blob(data)
    if age_s:
        path = store.blob_path(content_hash)
        old = time.time() - age_s
        os.utime(path, (old, old))
    return content_hash


def _age_manifest(key_dir: str, age_s: float) -> None:
    """Rewrite an entry's ``stored_at`` to ``age_s`` seconds ago."""
    path = os.path.join(key_dir, "manifest.json")
    with open(path) as f:
        manifest = json.load(f)
    manifest["stored_at"] = time.time() - age_s
    with open(path, "w") as f:
        json.dump(manifest, f)


DAY = 86_400


# --- usage ------------------------------------------------------------------


def test_cache_usage_breaks_the_total_down_by_area():
    cache.cache_put("fal-ai/x", {"p": 1}, {"images": [{"url": "https://f/a.png"}]})
    _put_blob(b"some-blob-bytes")

    usage = prune.cache_usage()

    assert sorted(a.name for a in usage.areas) == [
        "assets",
        "content",
        "manifests",
        "url_index",
    ]
    assert usage.area("manifests").entries == 1
    assert usage.area("content").entries == 1
    assert usage.total_bytes == sum(a.bytes for a in usage.areas)
    assert usage.area("content").bytes >= len(b"some-blob-bytes")


def test_cache_stats_keeps_its_old_keys_and_gains_the_breakdown():
    """The whole point of #22: a total alone cannot tell you what is safe to drop."""
    cache.cache_put("fal-ai/x", {"p": 1}, {"r": 1})

    stats = cache.cache_stats()

    assert stats["manifest_entries"] == 1
    assert stats["size_bytes"] > 0
    assert sorted(stats["areas"]) == ["assets", "content", "manifests", "url_index"]
    assert stats["size_bytes"] == sum(a["bytes"] for a in stats["areas"].values())


def test_cache_usage_area_rejects_an_unknown_name():
    with pytest.raises(KeyError):
        prune.cache_usage().area("nope")


# --- the refusal ------------------------------------------------------------


@pytest.mark.parametrize(
    "fn", [prune.prune_content, prune.prune_manifests, prune.prune_assets]
)
def test_an_unbounded_prune_is_refused_not_guessed(fn):
    """'Everything' and 'nothing' are both plausible readings, and one re-bills the cache."""
    with pytest.raises(ValueError, match="needs a bound"):
        fn()


# --- content ----------------------------------------------------------------


def test_prune_content_dry_run_reports_without_deleting():
    content_hash = _put_blob(b"old-bytes", age_s=100 * DAY)
    from falaw.content import default_content_store

    report = prune.prune_content(older_than=90 * DAY)

    assert report.dry_run is True
    assert [c.key for c in report.candidates] == [content_hash]
    assert report.freed_bytes == len(b"old-bytes")
    # ... and the blob is still there.
    assert default_content_store().has_blob(content_hash)


def test_prune_content_deletes_when_told_to():
    content_hash = _put_blob(b"old-bytes", age_s=100 * DAY)
    from falaw.content import default_content_store

    report = prune.prune_content(older_than=90 * DAY, dry_run=False)

    assert report.dry_run is False
    assert report.errors == ()
    assert not default_content_store().has_blob(content_hash)


def test_prune_content_keeps_what_is_young_enough():
    young = _put_blob(b"young", age_s=1 * DAY)
    old = _put_blob(b"old-bytes", age_s=100 * DAY)

    report = prune.prune_content(older_than=90 * DAY)

    assert [c.key for c in report.candidates] == [old]
    assert report.kept_entries == 1
    assert young not in {c.key for c in report.candidates}


def test_prune_content_counts_the_entries_it_makes_unmaterializable():
    """The money number. An entry whose asset resolves to a dropped blob re-bills."""
    from falaw.content import content_ref_for_url

    url = "https://fal.media/files/doomed.png"
    # Register url -> content hash exactly as a real execute would, then record
    # a cache entry whose response names that URL.
    ref = content_ref_for_url(url, fetcher=lambda _u: [b"doomed-bytes"])
    cache.cache_put("fal-ai/x", {"p": 1}, {"images": [{"url": url}]})
    # A second entry that points at an asset we are NOT dropping.
    other = "https://fal.media/files/safe.png"
    content_ref_for_url(other, fetcher=lambda _u: [b"safe-bytes"])
    cache.cache_put("fal-ai/x", {"p": 2}, {"images": [{"url": other}]})

    from falaw.content import default_content_store

    store = default_content_store()
    os.utime(
        store.blob_path(ref.content_hash),
        (time.time() - 100 * DAY, time.time() - 100 * DAY),
    )

    report = prune.prune_content(older_than=90 * DAY)

    assert [c.key for c in report.candidates] == [ref.content_hash]
    assert report.rebillable_entries == 1, report.summary()


def test_prune_content_does_not_count_entries_that_were_already_broken():
    """An entry with no recoverable asset is not made worse by this prune."""
    cache.cache_put("fal-ai/x", {"p": 1}, {"text": "no asset here"})
    _put_blob(b"unrelated", age_s=100 * DAY)

    report = prune.prune_content(older_than=90 * DAY)

    assert len(report.candidates) == 1
    assert report.rebillable_entries == 0


def test_max_bytes_evicts_oldest_first_and_keeps_the_newest_under_budget():
    old = _put_blob(b"a" * 100, age_s=30 * DAY)
    mid = _put_blob(b"b" * 100, age_s=20 * DAY)
    new = _put_blob(b"c" * 100, age_s=1 * DAY)

    report = prune.prune_content(max_bytes=250)

    dropped = {c.key for c in report.candidates}
    assert dropped == {old}, report.summary()
    assert report.kept_entries == 2
    assert {mid, new} & dropped == set()


def test_max_bytes_of_zero_drops_everything():
    a = _put_blob(b"a" * 10, age_s=DAY)
    b = _put_blob(b"b" * 10, age_s=DAY)

    report = prune.prune_content(max_bytes=0)

    assert {c.key for c in report.candidates} == {a, b}
    assert report.kept_entries == 0


def test_an_unprovable_age_is_never_evidence_of_staleness():
    """A backend with no filesystem path reports no mtime; that is not 'old'."""
    from lacing import ArtifactStore

    store = ArtifactStore.in_memory()
    store.put_blob(b"ageless")

    report = prune.prune_content(older_than=1, store=store)

    assert report.candidates == ()
    assert report.kept_entries == 1


def test_an_unprovable_age_is_evicted_last_under_a_size_bound():
    """Space may force the issue — but only after everything datable is gone."""
    from lacing import ArtifactStore

    store = ArtifactStore.in_memory()
    ageless = store.put_blob(b"x" * 100)

    report = prune.prune_content(max_bytes=100, store=store)

    # It fits, so it survives; nothing datable exists to drop ahead of it.
    assert report.candidates == ()
    assert report.kept_entries == 1

    report = prune.prune_content(max_bytes=0, store=store)
    assert [c.key for c in report.candidates] == [ageless]


# --- manifests --------------------------------------------------------------


def test_prune_manifests_rebills_every_entry_it_drops():
    entry_dir = cache.cache_put("fal-ai/x", {"p": 1}, {"r": 1})
    _age_manifest(entry_dir, 100 * DAY)

    report = prune.prune_manifests(older_than=90 * DAY)

    assert len(report.candidates) == 1
    assert report.rebillable_entries == 1


def test_prune_manifests_reads_stored_at_not_just_mtime():
    """The manifest records when falaw wrote it; a touched file must not read as new."""
    entry_dir = cache.cache_put("fal-ai/x", {"p": 1}, {"r": 1})
    _age_manifest(entry_dir, 100 * DAY)
    # mtime is *now* (we just rewrote the file), so an mtime-only implementation
    # would keep this entry.
    assert time.time() - os.path.getmtime(os.path.join(entry_dir, "manifest.json")) < 5

    report = prune.prune_manifests(older_than=90 * DAY)

    assert len(report.candidates) == 1


def test_prune_manifests_leaves_blobs_alone():
    """Blobs are shared by content hash across entries — the drop_cache_entry rule."""
    content_hash = _put_blob(b"shared-bytes")
    entry_dir = cache.cache_put("fal-ai/x", {"p": 1}, {"r": 1})
    _age_manifest(entry_dir, 100 * DAY)

    prune.prune_manifests(older_than=90 * DAY, dry_run=False)

    from falaw.content import default_content_store

    assert default_content_store().has_blob(content_hash)
    assert cache.cache_get("fal-ai/x", {"p": 1}) is None


# --- assets -----------------------------------------------------------------


def test_prune_assets_is_free_while_the_blob_survives():
    """The cheapest reclaim in the cache: a copy whose original is still there."""
    from falaw.content import content_ref_for_url

    url = "https://fal.media/files/a.png"
    content_ref_for_url(url, fetcher=lambda _u: [b"asset-bytes"])
    path = cache.materialize_asset(url)
    old = time.time() - 100 * DAY
    os.utime(path, (old, old))

    report = prune.prune_assets(older_than=90 * DAY)

    assert len(report.candidates) == 1
    assert report.rebillable_entries == 0, report.summary()


def test_prune_assets_flags_the_copies_whose_blob_is_gone():
    from falaw.content import content_ref_for_url, default_content_store

    url = "https://fal.media/files/a.png"
    ref = content_ref_for_url(url, fetcher=lambda _u: [b"asset-bytes"])
    path = cache.materialize_asset(url)
    old = time.time() - 100 * DAY
    os.utime(path, (old, old))
    del default_content_store().blobs[ref.content_hash]

    report = prune.prune_assets(older_than=90 * DAY)

    assert report.rebillable_entries == 1, report.summary()


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("a" * 64 + ".png", "a" * 64),
        ("hint-" + "b" * 64 + ".mp4", "b" * 64),
        ("nope.png", None),
        ("z" * 64 + ".png", None),  # not hex
        ("short.bin", None),
    ],
)
def test_content_hash_is_read_back_out_of_the_asset_filename(filename, expected):
    assert prune._content_hash_in_asset_name(filename) == expected


# --- failure handling -------------------------------------------------------


def test_a_failed_deletion_is_reported_not_raised(monkeypatch):
    """A prune that aborts halfway leaves neither the disk nor a report."""
    _put_blob(b"a" * 10, age_s=100 * DAY)
    _put_blob(b"b" * 10, age_s=100 * DAY)

    from falaw.content import default_content_store

    store = default_content_store()
    original = type(store.blobs).__delitem__
    calls = {"n": 0}

    def flaky(self, key):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("device busy")
        return original(self, key)

    monkeypatch.setattr(type(store.blobs), "__delitem__", flaky)

    report = prune.prune_content(older_than=90 * DAY, dry_run=False, store=store)

    assert len(report.errors) == 1
    assert "device busy" in report.errors[0]
    assert calls["n"] == 2, "the sweep must continue past a failure"


def test_summary_says_would_when_it_is_a_dry_run():
    _put_blob(b"a" * 10, age_s=100 * DAY)

    dry = prune.prune_content(older_than=90 * DAY)
    assert "would free" in dry.summary()

    wet = prune.prune_content(older_than=90 * DAY, dry_run=False)
    assert "freed" in wet.summary() and "would free" not in wet.summary()
