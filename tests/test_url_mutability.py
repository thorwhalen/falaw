"""Tests for falaw#23 — when falaw may trust the ``url -> content hash`` index.

The index is only sound for URLs that cannot re-point at different bytes. The
defect was that ``materialize_asset`` is public and reached with arbitrary
caller-supplied URLs, so a mutable one kept resolving to the old hash — a
changed input producing an unchanged content address, silently, with the stale
hash flowing into ``Artifact.asset_id`` and every downstream cache key.

What these pin, in order of how much they would cost to get wrong:

* a **changed** mutable URL yields new bytes and a new address;
* an **unknown** answer (no validators, or a transport that cannot revalidate)
  makes falaw re-fetch — never trust;
* an **unreachable** origin falls back to stored bytes rather than failing,
  which is falaw#14's guarantee and does not conflict: staleness is only a lie
  when the truth was available and falaw did not look;
* a **fal** URL still costs nothing, which is what keeps a 200-shot re-run free.
"""

from __future__ import annotations

import os
import warnings

import pytest

from falaw import materialize_asset
from falaw.content import (
    IMMUTABLE_URL_HOSTS,
    ContentRef,
    Validators,
    content_ref_for_url,
    is_immutable_url,
    remembered_ref,
)


IMG_A = b"\x89PNG-pretend-image-A" * 4
IMG_B = b"\x89PNG-pretend-image-B" * 8


# --- which URLs may be trusted ----------------------------------------------


@pytest.mark.parametrize(
    "url,immutable",
    [
        ("https://fal.media/files/x.png", True),
        ("https://v3b.fal.media/files/x.png", True),
        ("https://v3.fal.media/files/x.png", True),
        ("https://fal.run/x", True),
        ("https://example.com/reference.png", False),
        ("http://cdn/clip.mp4", False),
        ("file:///tmp/render.mp4", False),
        ("", False),
        # A host merely *containing* a trusted name is not that host.
        ("https://fal.media.attacker.example/x.png", False),
        ("https://notfal.media/x.png", False),
    ],
)
def test_is_immutable_url(url, immutable):
    assert is_immutable_url(url) is immutable


def test_a_deployment_can_declare_its_own_immutable_host(fake_assets, monkeypatch):
    """Open-closed: an immutable-by-construction CDN should not pay per asset."""
    url = "https://cdn.example.com/sha256-abc.png"
    fake_assets.serve(url, IMG_A)
    materialize_asset(url)
    fake_assets.fetched.clear()

    monkeypatch.setattr(
        "falaw.content.IMMUTABLE_URL_HOSTS", IMMUTABLE_URL_HOSTS | {"cdn.example.com"}
    )
    materialize_asset(url)

    assert fake_assets.fetched == []


# --- the defect itself ------------------------------------------------------


def test_a_changed_mutable_url_produces_a_new_content_hash(fake_assets):
    """The issue's reproduction. Used to return the old hash with no network."""
    url = "https://example.com/reference.png"
    fake_assets.serve(url, IMG_A)
    before = content_ref_for_url(url)

    fake_assets.serve(url, IMG_B)
    after = content_ref_for_url(url)

    assert after.content_hash != before.content_hash
    assert after.bytes_size == len(IMG_B)


def test_an_unchanged_mutable_url_is_confirmed_without_transferring_the_body(
    fake_assets,
):
    url = "https://example.com/reference.png"
    fake_assets.serve(url, IMG_A)
    first = content_ref_for_url(url)
    fake_assets.fetched.clear()

    again = content_ref_for_url(url)

    assert again == first
    assert fake_assets.fetched == []


def test_validators_are_recorded_on_the_very_first_read(fake_assets):
    """Otherwise nothing can ever be revalidated and every read re-downloads.

    The plain ``UrlFetcher`` seam yields bytes, not a response, so a first fetch
    routed only through it can never learn an ETag.
    """
    from falaw.content import _remembered_record

    url = "https://example.com/reference.png"
    fake_assets.serve(url, IMG_A)
    content_ref_for_url(url)

    record = _remembered_record(url)
    assert record is not None
    assert record.validators, "no validators recorded on first read"


# --- what falaw does when it cannot check -----------------------------------


def test_a_transport_that_cannot_revalidate_forces_a_refetch(fake_assets):
    """An unverifiable hint is not evidence. Re-fetch, never trust."""
    url = "https://example.com/reference.png"
    calls = []

    def bytes_only_fetcher(u):
        """A plain UrlFetcher: no ``conditional_fetch`` capability."""
        calls.append(u)
        yield IMG_A if len(calls) == 1 else IMG_B

    first = content_ref_for_url(url, fetcher=bytes_only_fetcher)
    second = content_ref_for_url(url, fetcher=bytes_only_fetcher)

    assert len(calls) == 2, "a hint it cannot verify must not be trusted"
    assert second.content_hash != first.content_hash


def test_an_index_record_written_before_validators_existed_is_refetched(fake_assets):
    """Old records read back with empty validators, which already means re-fetch.

    Deliberately no migration: the pre-falaw#23 record degrades into the correct
    behaviour rather than into a special case.
    """
    import json

    from falaw.content import _url_index_path

    url = "https://example.com/reference.png"
    fake_assets.serve(url, IMG_A)
    ref = content_ref_for_url(url)

    # Rewrite the index entry in the old shape — no etag, no last_modified.
    with open(_url_index_path(url), "w") as f:
        json.dump(
            {"url": url, "content_hash": ref.content_hash, "bytes_size": ref.bytes_size},
            f,
        )
    assert remembered_ref(url) == ContentRef(ref.content_hash, ref.bytes_size)
    fake_assets.serve(url, IMG_B)
    fake_assets.fetched.clear()

    again = content_ref_for_url(url)

    assert fake_assets.fetched == [url]
    assert again.content_hash != ref.content_hash


def test_an_unreachable_origin_falls_back_to_the_stored_bytes(fake_assets):
    """falaw#14's guarantee survives falaw#23, and the two do not conflict."""
    url = "https://example.com/reference.png"
    fake_assets.serve(url, IMG_A)
    first = content_ref_for_url(url)

    fake_assets.fail(url)

    with pytest.warns(UserWarning, match="Could not re-read"):
        again = content_ref_for_url(url)

    assert again == first


def test_an_unreachable_origin_with_no_stored_bytes_still_raises(fake_assets):
    """The fallback is for bytes falaw *has*, not a way to swallow failures."""
    from falaw.errors import FalAssetFetchError

    url = "https://example.com/missing.png"
    fake_assets.fail(url)

    with pytest.raises(FalAssetFetchError):
        content_ref_for_url(url)


# --- file:// is mutable too -------------------------------------------------


def test_a_locally_rendered_file_that_is_rewritten_gets_a_new_hash(tmp_path):
    """Re-rendering a clip to the same path is the textbook mutable URL."""
    render = tmp_path / "render.mp4"
    render.write_bytes(IMG_A)
    url = render.as_uri()

    before = content_ref_for_url(url)
    render.write_bytes(IMG_B)
    after = content_ref_for_url(url)

    assert after.content_hash != before.content_hash
    assert after.bytes_size == len(IMG_B)


def test_an_untouched_local_file_is_not_re_read(tmp_path, monkeypatch):
    """`(mtime, size)` is what a filesystem answers without reading the file.

    Proven by making a body read *fail*: if the second call still succeeds, no
    bytes were read. Asserting the two ``ContentRef``\\ s are equal would not
    show this — an unchanged file hashes the same whether or not falaw re-read
    every byte of it, so that assertion passes with the optimisation removed.
    """
    render = tmp_path / "render.mp4"
    render.write_bytes(IMG_A)
    url = render.as_uri()

    first = content_ref_for_url(url)

    def refuse(*a, **kw):
        raise AssertionError("re-read the file body despite unchanged mtime/size")

    monkeypatch.setattr("falaw.content._http_chunks", refuse)
    # `simplefilter("error")` is load-bearing: without it the stored-bytes
    # fallback catches the refusal, warns, and returns the right answer — so the
    # assertion below would pass with the revalidation removed entirely.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        again = content_ref_for_url(url)

    assert again == first


def test_a_local_file_records_its_mtime_and_size_as_validators(tmp_path):
    """Without these there is nothing to compare, and every read re-hashes."""
    from falaw.content import _remembered_record

    render = tmp_path / "render.mp4"
    render.write_bytes(IMG_A)
    url = render.as_uri()

    content_ref_for_url(url)

    record = _remembered_record(url)
    assert record is not None
    assert record.validators.etag.startswith("file:")
    assert str(len(IMG_A)) in record.validators.etag


# --- the explicit override --------------------------------------------------


def test_assume_immutable_true_restores_unconditional_trust(fake_assets):
    url = "https://example.com/reference.png"
    fake_assets.serve(url, IMG_A)
    first = content_ref_for_url(url)

    fake_assets.serve(url, IMG_B)
    fake_assets.fetched.clear()
    again = content_ref_for_url(url, assume_immutable=True)

    assert again == first
    assert fake_assets.fetched == []


def test_assume_immutable_false_forces_revalidation_even_for_fal(fake_assets):
    url = "https://v3b.fal.media/files/x.png"
    fake_assets.serve(url, IMG_A)
    content_ref_for_url(url)

    fake_assets.serve(url, IMG_B)
    again = content_ref_for_url(url, assume_immutable=False)

    assert again.bytes_size == len(IMG_B)


# --- the fake's own capability ----------------------------------------------


def test_fake_assets_answers_a_revalidation(fake_assets):
    """falaw owns the fake, so downstream suites get the cheap path too."""
    url = "https://example.com/x.png"
    fake_assets.serve(url, IMG_A)
    etag = fake_assets.etag_for(url)

    unchanged = fake_assets.conditional_fetch(url, Validators(etag=etag))
    assert unchanged.not_modified is True
    assert fake_assets.fetched == [], "a 304 transfers no body"

    fake_assets.serve(url, IMG_B)
    changed = fake_assets.conditional_fetch(url, Validators(etag=etag))
    assert changed.not_modified is False
    assert b"".join(changed.chunks) == IMG_B


def test_a_failed_conditional_fetch_is_recorded_as_a_fetch(fake_assets):
    """falaw degrades a failed fetch to a warning, so the fake must record it."""
    import urllib.error

    url = "https://example.com/gone.png"
    fake_assets.fail(url)

    with pytest.raises(urllib.error.HTTPError):
        fake_assets.conditional_fetch(url, Validators(etag='"whatever"'))

    assert fake_assets.fetched == [url]


def test_materialize_asset_returns_the_local_copy_when_the_origin_dies(fake_assets):
    """Circle 1 as a fallback: tried the origin, it is gone, the file is here."""
    url = "https://example.com/reference.png"
    fake_assets.serve(url, IMG_A)
    first = materialize_asset(url)
    fake_assets.fail(url)

    with pytest.warns(UserWarning, match="Could not re-read"):
        again = materialize_asset(url)

    assert again == first
    assert os.path.exists(again)
