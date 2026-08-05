"""Regression guards for falaw#14 — identify media by *what it is*, not *where*.

Two defects, one confusion:

* **D3** — ``Artifact.asset_id`` was ``sha256(url)``, so two byte-identical
  renders got different ids and ``lacing.Artifact``'s content-hash contract was
  false for every media artifact falaw produced.
* **D1** — the upstream *URL* went into the downstream cache key, so a
  byte-identical upstream regeneration missed downstream and re-billed a
  $0.35–$1.50 clip for work that had not changed.

fal's own docs are the primary source for why a URL cannot carry identity:
"Each upload produces a unique URL with no shared namespace" and "Expired files
are permanently deleted and cannot be recovered."

The load-bearing tests here are:

* :func:`test_same_bytes_at_a_new_url_hits_the_downstream_cache` — D1's fix.
* :func:`test_changed_upstream_bytes_miss_the_downstream_cache` — the other
  half: a key change must still *happen* when the input really changed, or the
  fix would trade a wasteful miss for a wrong hit.
* :func:`test_the_wire_gets_the_url_and_the_key_gets_the_content_hash` — the
  split that makes both possible without sending a content hash to fal.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import types

import pytest


IMG_A = b"\x89PNG-pretend-image-A" * 4
IMG_B = b"\x89PNG-pretend-image-B" * 4


# --- helpers ---------------------------------------------------------------


class FakeFal:
    """A fal_client stub whose asset URLs the test controls."""

    def __init__(self):
        self.calls: list[dict] = []
        self.next_image_url = "http://cdn/img-1.png"
        self.next_video_url = "http://cdn/clip-1.mp4"

    def subscribe(self, application, *, arguments, with_logs, on_queue_update):
        self.calls.append({"application": application, "arguments": dict(arguments)})
        if "svd" in application or "image-to-video" in application:
            return {
                "video": {
                    "url": self.next_video_url,
                    "duration": 3.0,
                    "content_type": "video/mp4",
                }
            }
        return {"images": [{"url": self.next_image_url, "content_type": "image/png"}]}

    @property
    def applications(self) -> list[str]:
        return [c["application"] for c in self.calls]


@pytest.fixture
def fal(monkeypatch):
    stub = FakeFal()
    monkeypatch.setitem(
        sys.modules,
        "fal_client",
        types.SimpleNamespace(
            InProgress=type("IP", (), {"__init__": lambda s, logs: None}),
            subscribe=stub.subscribe,
        ),
    )
    return stub


def _image_plan():
    from falaw import CallPlan, Plan

    return Plan(
        calls=(
            CallPlan(
                tool="generate_image",
                application="fal-ai/flux/dev",
                arguments={"prompt": "a tiger"},
                output_kind="image",
                estimated_cost_usd=0.02,
            ),
        )
    )


def _two_step_plan():
    from falaw import CallPlan, Plan

    return Plan(
        calls=(
            CallPlan(
                tool="generate_image",
                application="fal-ai/flux/dev",
                arguments={"prompt": "a tiger"},
                output_kind="image",
                estimated_cost_usd=0.02,
            ),
            CallPlan(
                tool="image_to_video",
                application="fal-ai/svd",
                arguments={"image_url": "<from 0>", "duration": 3},
                output_kind="video",
                estimated_cost_usd=0.50,
            ),
        )
    )


def _evict(call):
    """Drop one call's cache entry — the "another machine / after eviction" case."""
    from falaw.cache import _entry_dir, _key

    shutil.rmtree(
        _entry_dir(_key(call.application, call.arguments)), ignore_errors=True
    )


def _manifests() -> list[dict]:
    from falaw.cache import _cache_dir

    out = []
    for dirpath, _dirs, files in os.walk(_cache_dir()):
        for f in files:
            if f == "manifest.json":
                with open(os.path.join(dirpath, f)) as fh:
                    out.append(json.load(fh))
    return out


def _manifest_for(application: str) -> dict:
    matches = [m for m in _manifests() if m["application"] == application]
    assert len(matches) == 1, f"expected one manifest for {application}, got {matches}"
    return matches[0]


# --- D3: asset_id is the SHA-256 of the bytes ------------------------------


def test_asset_id_is_the_sha256_of_the_bytes(fal, fake_assets):
    from lacing import hash_bytes

    from falaw import execute_plan

    fal.next_image_url = "http://cdn/whatever.png"
    fake_assets.serve("http://cdn/whatever.png", IMG_A)

    (art,) = execute_plan(_image_plan())

    assert art.asset_id == hash_bytes(IMG_A)
    assert art.bytes_size == len(IMG_A)
    assert art.url == "http://cdn/whatever.png"  # kept as a hint
    # ... and NOT the hash of the URL (the defect).
    assert art.asset_id != hash_bytes(b"http://cdn/whatever.png")


def test_the_bytes_are_stored_and_reachable_from_the_artifact(fal, fake_assets):
    from falaw import execute_plan

    fal.next_image_url = "http://cdn/a.png"
    fake_assets.serve("http://cdn/a.png", IMG_A)

    (art,) = execute_plan(_image_plan())

    assert art.path is not None, "the artifact must point at the stored bytes"
    assert open(art.path, "rb").read() == IMG_A


def test_same_bytes_at_two_urls_are_one_artifact_identity(fal, fake_assets):
    from falaw import execute_plan

    fal.next_image_url = "http://cdn/first.png"
    fake_assets.serve("http://cdn/first.png", IMG_A)
    (first,) = execute_plan(_image_plan())

    _evict(_image_plan().calls[0])
    fal.next_image_url = "http://cdn/second.png"
    fake_assets.serve("http://cdn/second.png", IMG_A)
    (second,) = execute_plan(_image_plan())

    assert first.url != second.url
    assert first.asset_id == second.asset_id


def test_two_distinct_assets_get_distinct_asset_ids(fake_assets):
    """Different bytes ⇒ different ids; identical bytes ⇒ one shared id."""
    from lacing import ArtifactStore

    from falaw.content import content_ref_for_url

    store = ArtifactStore.in_memory()
    fake_assets.serve("http://cdn/x1", IMG_A)
    fake_assets.serve("http://cdn/x2", IMG_B)
    fake_assets.serve("http://cdn/x3", IMG_A)

    r1 = content_ref_for_url("http://cdn/x1", store=store)
    r2 = content_ref_for_url("http://cdn/x2", store=store)
    r3 = content_ref_for_url("http://cdn/x3", store=store)

    assert r1.content_hash != r2.content_hash
    assert r1.content_hash == r3.content_hash
    assert len(store.blobs) == 2, "identical bytes must dedup to one blob"


# --- D1: the downstream cache key is over content, not location -------------


def test_same_bytes_at_a_new_url_hits_the_downstream_cache(fal, fake_assets):
    """The money test.

    Run 1 caches both calls. Then the *upstream* entry is evicted (a second
    machine, a ``refresh``, a GC) so the upstream genuinely re-executes and fal
    mints a **new URL** for the **same bytes**. The expensive downstream clip
    must be served from cache — under the old URL-in-the-key behaviour it was
    re-rendered and re-billed.
    """
    from falaw import execute_plan

    plan = _two_step_plan()

    fal.next_image_url = "http://cdn/img-run1.png"
    fake_assets.serve("http://cdn/img-run1.png", IMG_A)
    fake_assets.serve("http://cdn/clip-1.mp4", b"clip-bytes")
    first = execute_plan(plan)
    assert fal.applications == ["fal-ai/flux/dev", "fal-ai/svd"]

    _evict(plan.calls[0])
    fal.calls.clear()
    fal.next_image_url = "http://cdn/img-run2.png"  # different location...
    fake_assets.serve("http://cdn/img-run2.png", IMG_A)  # ...identical bytes

    second = execute_plan(plan)

    assert fal.applications == ["fal-ai/flux/dev"], (
        "only the upstream should have re-executed; the downstream clip must "
        "hit the cache because its input bytes did not change"
    )
    assert second[0].asset_id == first[0].asset_id
    assert second[1].asset_id == first[1].asset_id


def test_changed_upstream_bytes_miss_the_downstream_cache(fal, fake_assets):
    """The safety half: a genuinely different input must NOT hit."""
    from falaw import execute_plan

    plan = _two_step_plan()

    fal.next_image_url = "http://cdn/img-run1.png"
    fake_assets.serve("http://cdn/img-run1.png", IMG_A)
    fake_assets.serve("http://cdn/clip-1.mp4", b"clip-bytes-1")
    execute_plan(plan)

    _evict(plan.calls[0])
    fal.calls.clear()
    fal.next_image_url = "http://cdn/img-run2.png"
    fake_assets.serve("http://cdn/img-run2.png", IMG_B)  # DIFFERENT bytes
    fal.next_video_url = "http://cdn/clip-2.mp4"
    fake_assets.serve("http://cdn/clip-2.mp4", b"clip-bytes-2")

    execute_plan(plan)

    assert fal.applications == ["fal-ai/flux/dev", "fal-ai/svd"], (
        "a changed upstream input must change the downstream key"
    )


def test_the_wire_gets_the_url_and_the_key_gets_the_content_hash(fal, fake_assets):
    """The split. Sending a content hash to fal would break every chained call."""
    from lacing import hash_bytes

    from falaw import execute_plan
    from falaw.plan import CONTENT_REF_PREFIX

    plan = _two_step_plan()
    fal.next_image_url = "http://cdn/img.png"
    fake_assets.serve("http://cdn/img.png", IMG_A)
    fake_assets.serve("http://cdn/clip-1.mp4", b"clip-bytes")

    execute_plan(plan)

    wire = fal.calls[1]["arguments"]
    assert wire["image_url"] == "http://cdn/img.png"
    assert not wire["image_url"].startswith(CONTENT_REF_PREFIX)

    manifest = _manifest_for("fal-ai/svd")
    assert manifest["arguments"]["image_url"] == (
        f"{CONTENT_REF_PREFIX}{hash_bytes(IMG_A)}"
    )
    assert manifest["wire_arguments"]["image_url"] == "http://cdn/img.png"


def test_unchained_calls_record_no_separate_wire_arguments(fal, fake_assets):
    """No placeholders ⇒ wire and key arguments are the same object."""
    from falaw import execute_plan

    fal.next_image_url = "http://cdn/a.png"
    execute_plan(_image_plan())

    assert "wire_arguments" not in _manifest_for("fal-ai/flux/dev")


def test_key_ref_prefers_content_and_falls_back_to_url():
    """Unit-level statement of the key-resolution rule."""
    from lacing import Artifact

    from falaw.plan import CONTENT_REF_PREFIX, _key_ref

    with_bytes = Artifact.from_bytes(
        IMG_A, kind="image", was_generated_by="agent:t", was_attributed_to="user:t"
    ).model_copy(update={"url": "http://cdn/a.png"})
    assert _key_ref(with_bytes, 0, "<from 0>") == (
        f"{CONTENT_REF_PREFIX}{with_bytes.asset_id}"
    )

    without_bytes = with_bytes.model_copy(update={"bytes_size": 0})
    assert _key_ref(without_bytes, 0, "<from 0>") == "http://cdn/a.png"

    nothing = without_bytes.model_copy(update={"url": None})
    with pytest.raises(ValueError):
        _key_ref(nothing, 0, "<from 0>")


# --- durability: fal deletes URLs -------------------------------------------


def test_stored_bytes_survive_an_expired_url(fal, fake_assets):
    """A months-old cache hit must still yield a usable artifact."""
    from falaw import execute_plan

    fal.next_image_url = "http://cdn/ephemeral.png"
    fake_assets.serve("http://cdn/ephemeral.png", IMG_A)
    (first,) = execute_plan(_image_plan())

    fake_assets.fail("http://cdn/ephemeral.png")  # fal deleted it
    fake_assets.fetched.clear()

    (again,) = execute_plan(_image_plan())

    assert fake_assets.fetched == [], "the bytes are already stored; do not refetch"
    assert again.asset_id == first.asset_id
    assert again.bytes_size == len(IMG_A)


def test_a_cached_response_whose_url_is_gone_raises(fal, fake_assets):
    """Never silently return an artifact we cannot back with bytes."""
    from falaw import execute_plan
    from falaw.cache import _cache_dir
    from falaw.content import CONTENT_STORE_DIRNAME, URL_INDEX_DIRNAME
    from falaw.errors import FalAssetFetchError

    fal.next_image_url = "http://cdn/ephemeral.png"
    fake_assets.serve("http://cdn/ephemeral.png", IMG_A)
    execute_plan(_image_plan())

    # The fal response stays cached, but the bytes are gone from this machine
    # and fal has deleted the URL.
    shutil.rmtree(os.path.join(_cache_dir(), CONTENT_STORE_DIRNAME))
    shutil.rmtree(os.path.join(_cache_dir(), URL_INDEX_DIRNAME))
    fake_assets.fail("http://cdn/ephemeral.png")

    with pytest.raises(FalAssetFetchError) as exc:
        execute_plan(_image_plan())
    assert exc.value.url == "http://cdn/ephemeral.png"


def test_a_remembered_hash_without_its_blob_is_refetched(fal, fake_assets):
    """The url→hash index is a *hint*, never a substitute for the bytes.

    Trusting it without checking the blob is present would hand out an
    ``asset_id`` backed by nothing — a content address that addresses no
    content — the moment a blob is GC'd or the store moves.
    """
    from falaw import execute_plan
    from falaw.cache import _cache_dir
    from falaw.content import CONTENT_STORE_DIRNAME

    fal.next_image_url = "http://cdn/x.png"
    fake_assets.serve("http://cdn/x.png", IMG_A)
    (first,) = execute_plan(_image_plan())

    # Blobs gone (GC / different machine); the url-index hint survives.
    shutil.rmtree(os.path.join(_cache_dir(), CONTENT_STORE_DIRNAME))
    fake_assets.fetched.clear()

    (again,) = execute_plan(_image_plan())

    assert fake_assets.fetched == ["http://cdn/x.png"]
    assert again.asset_id == first.asset_id
    assert open(again.path, "rb").read() == IMG_A


def test_a_remembered_hash_with_neither_blob_nor_live_url_raises(fal, fake_assets):
    from falaw import execute_plan
    from falaw.cache import _cache_dir
    from falaw.content import CONTENT_STORE_DIRNAME
    from falaw.errors import FalAssetFetchError

    fal.next_image_url = "http://cdn/x.png"
    fake_assets.serve("http://cdn/x.png", IMG_A)
    execute_plan(_image_plan())

    shutil.rmtree(os.path.join(_cache_dir(), CONTENT_STORE_DIRNAME))
    fake_assets.fail("http://cdn/x.png")

    with pytest.raises(FalAssetFetchError):
        execute_plan(_image_plan())


def test_an_empty_asset_is_refused(fal, fake_assets):
    from falaw import execute_plan
    from falaw.errors import FalAssetFetchError

    fal.next_image_url = "http://cdn/empty.png"
    fake_assets.serve("http://cdn/empty.png", b"")

    with pytest.raises(FalAssetFetchError):
        execute_plan(_image_plan())


# --- the documented opt-out -------------------------------------------------


def test_fetch_bytes_false_downloads_nothing_and_forfeits_chained_caching(
    fal, fake_assets
):
    from lacing import hash_bytes

    from falaw import execute_plan
    from falaw.plan import CONTENT_REF_PREFIX

    plan = _two_step_plan()
    fal.next_image_url = "http://cdn/img.png"

    artifacts = execute_plan(plan, fetch_bytes=False)

    assert fake_assets.fetched == []
    assert artifacts[0].bytes_size == 0
    assert artifacts[0].path is None
    # Emphatically not sha256(url) — that was the defect, not the fallback.
    assert artifacts[0].asset_id != hash_bytes(b"http://cdn/img.png")

    manifest = _manifest_for("fal-ai/svd")
    key_ref = manifest["arguments"]["image_url"]
    assert key_ref == "http://cdn/img.png"
    assert not key_ref.startswith(CONTENT_REF_PREFIX)


def test_fetch_bytes_env_var_flips_the_default(fal, fake_assets, monkeypatch):
    from falaw import execute_plan
    from falaw.plan import FETCH_BYTES_ENVVAR

    monkeypatch.setenv(FETCH_BYTES_ENVVAR, "0")
    fal.next_image_url = "http://cdn/img.png"

    (art,) = execute_plan(_image_plan())

    assert fake_assets.fetched == []
    assert art.bytes_size == 0


# --- one addressing scheme: materialize_asset -------------------------------


def test_materialize_asset_is_addressed_by_content(fake_assets):
    from lacing import hash_bytes

    from falaw import materialize_asset

    fake_assets.serve("http://cdn/one.mp4", IMG_A)
    fake_assets.serve("http://cdn/two.mp4", IMG_A)

    p1 = materialize_asset("http://cdn/one.mp4")
    p2 = materialize_asset("http://cdn/two.mp4")

    assert os.path.basename(p1) == f"{hash_bytes(IMG_A)}.mp4"
    assert p1 == p2, "identical bytes at two URLs must resolve to one local file"
    assert open(p1, "rb").read() == IMG_A


def test_materialize_asset_does_not_refetch_stored_bytes(fake_assets):
    from falaw import materialize_asset

    fake_assets.serve("http://cdn/one.mp4", IMG_A)
    materialize_asset("http://cdn/one.mp4")
    fake_assets.fetched.clear()

    materialize_asset("http://cdn/one.mp4")

    assert fake_assets.fetched == []


def test_materialize_asset_keeps_the_key_hint_prefix(fake_assets):
    from lacing import hash_bytes

    from falaw import materialize_asset

    fake_assets.serve("http://cdn/one.png", IMG_A)
    path = materialize_asset("http://cdn/one.png", key_hint="ref")
    assert os.path.basename(path) == f"ref-{hash_bytes(IMG_A)}.png"


# --- the module's own examples must run -------------------------------------


def test_content_module_doctests_pass():
    import doctest

    import falaw.content

    result = doctest.testmod(
        falaw.content,
        optionflags=doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS,
    )
    assert result.failed == 0
