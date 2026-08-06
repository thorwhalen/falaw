"""Content addressing for fal-produced media — identify a file by *what it is*.

fal serves generated media from a CDN URL, and fal's own documentation is
explicit that a URL carries neither identity nor durability:

    "Each upload produces a unique URL with no shared namespace."

    "Expired files are permanently deleted and cannot be recovered."

So a URL is the wrong handle for the two jobs falaw needs done:

1. **Naming an artifact.** ``lacing.Artifact.asset_id`` is contractually the
   SHA-256 of the artifact's *bytes* — "two artifacts with the same
   ``asset_id`` are byte-identical regardless of where they live". Hashing the
   URL instead produces a different id for two byte-identical renders and
   silently breaks every consumer that trusts that contract.
2. **Keying a cache.** A byte-identical upstream regeneration must produce a
   downstream cache **hit**. With a URL in the key it produces a miss, and the
   miss re-bills a $0.35–$1.50 clip for work that did not change.

This module is the single place falaw turns a URL into a content hash. It

* streams the bytes into a :class:`lacing.ArtifactStore` blob store — which is
  content-addressed, ``dol``-backed and swappable (in-memory / directory /
  object store) — rather than growing a second blob store of its own;
* remembers ``url -> (content_hash, bytes_size)`` in a small on-disk index, so
  re-executing an already-cached plan does **not** re-download anything. The
  index is a *hint*, never an identity, and it is only **sound for immutable
  URLs**. It is sound for fal's own, because fal guarantees a URL is minted per
  upload and therefore never re-points at different bytes. It is *not* sound
  for an arbitrary caller-supplied URL reached through
  :func:`falaw.cache.materialize_asset` — a mutable ``https://…/reference.png``
  that changes behind our back keeps resolving to the old hash. Pass
  ``refresh=True`` when the URL is not known to be immutable
  (thorwhalen/falaw#23 tracks making that automatic via ETag revalidation);
* serves the bytes from the store after the URL has expired, so a months-old
  cache hit still yields a usable artifact instead of a dead link.

The blob store is **injected**, never constructed inline by callers:
:func:`default_content_store` is the falaw-cache-rooted default, and every
public function here takes a ``store`` keyword so a caller can point falaw at
an S3-backed store without touching any other code.

Examples
--------

>>> from lacing import ArtifactStore
>>> store = ArtifactStore.in_memory()
>>> ref = content_ref_for_url(
...     "https://fal.media/files/one.png",
...     store=store,
...     fetcher=lambda url: [b"pretend-", b"png-bytes"],
... )
>>> ref.bytes_size
17
>>> ref.content_hash == __import__("hashlib").sha256(b"pretend-png-bytes").hexdigest()
True

The same bytes served at a *different* URL yield the same reference — which is
the whole point:

>>> other = content_ref_for_url(
...     "https://fal.media/files/two.png",
...     store=store,
...     fetcher=lambda url: [b"pretend-png-bytes"],
... )
>>> other.content_hash == ref.content_hash
True
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, Optional

from .cache import _cache_dir
from .errors import FalAssetFetchError


__all__ = [
    "ContentRef",
    "content_ref_for_url",
    "default_content_store",
    "remembered_ref",
    "write_blob_to_file",
]


DFLT_CHUNK_SIZE = 1 << 16
"""Bytes per read when streaming a remote asset into the blob store."""

CONTENT_STORE_DIRNAME = "content"
"""Sub-directory of the falaw cache holding the default content store."""

URL_INDEX_DIRNAME = "url_index"
"""Sub-directory of the falaw cache holding the ``url -> ContentRef`` hints."""


UrlFetcher = Callable[[str], Iterable[bytes]]
"""A callable that yields the bytes of a URL in chunks.

The injection seam for tests and for callers that need custom transport
(auth headers, retries, a local mirror). :func:`_http_chunks` is the default.
"""


@dataclass(frozen=True, slots=True)
class ContentRef:
    """A content-addressed handle on some bytes falaw has materialized.

    ``content_hash`` is the SHA-256 hex digest of the bytes — the value
    ``lacing.Artifact.asset_id`` is contractually required to hold, and the
    value that goes into a downstream cache key in place of a URL.
    """

    content_hash: str
    bytes_size: int


def default_content_store():
    """The falaw-cache-rooted :class:`lacing.ArtifactStore`.

    Rooted at ``<falaw cache dir>/content``, so it moves with
    ``$FALAW_CACHE_DIR`` / ``$FALAW_DATA_DIR`` like every other piece of falaw
    state. Constructed per call (the constructor only ensures directories
    exist) so a test that re-points the cache dir gets a fresh store.
    """
    from lacing import ArtifactStore

    return ArtifactStore.from_directory(
        os.path.join(_cache_dir(), CONTENT_STORE_DIRNAME)
    )


def content_ref_for_url(
    url: str,
    *,
    store=None,
    fetcher: Optional[UrlFetcher] = None,
    refresh: bool = False,
) -> ContentRef:
    """Materialize ``url``'s bytes into ``store`` and return their content hash.

    Idempotent and download-free on repeat: the ``url -> ContentRef`` index is
    consulted first, and a remembered reference whose blob is still present is
    returned without touching the network. That is what makes re-executing an
    already-cached plan free rather than re-downloading every clip.

    Args:
        url: The remote asset URL (typically fal's CDN).
        store: Injected :class:`lacing.ArtifactStore`; defaults to
            :func:`default_content_store`.
        fetcher: Injected byte source; defaults to :func:`_http_chunks`.
        refresh: Ignore the remembered reference and re-fetch. Only useful when
            you suspect the index is wrong — fal URLs are per-upload, so the
            same URL never legitimately serves different bytes.

    Raises:
        FalAssetFetchError: the bytes could not be retrieved, or the response
            was empty. Never returns a reference it could not back with bytes —
            a silent zero-byte "artifact" is the failure mode this guards.
    """
    store = default_content_store() if store is None else store
    if not refresh:
        remembered = remembered_ref(url)
        if remembered is not None and store.has_blob(remembered.content_hash):
            return remembered
    ref = _fetch_into_store(url, store, fetcher or _http_chunks)
    _remember_ref(url, ref)
    return ref


def remembered_ref(url: str) -> Optional[ContentRef]:
    """The :class:`ContentRef` previously recorded for ``url``, if any.

    A *hint*, not a guarantee: it says "the last time falaw fetched this URL,
    the bytes hashed to this" and says nothing about whether those bytes are
    still in any store. Callers must verify (``store.has_blob(...)``, or an
    already-materialized file on disk) before trusting it.

    Public because it is the cheap pre-check that lets a caller answer "do I
    already have this?" without a network round-trip — see
    :func:`falaw.cache.materialize_asset`.
    """
    path = _url_index_path(url)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            record = json.load(f)
        return ContentRef(
            content_hash=record["content_hash"], bytes_size=int(record["bytes_size"])
        )
    except Exception:  # noqa: BLE001 — a corrupt hint is a miss, never a failure
        return None


def write_blob_to_file(content_hash: str, path: str, *, store=None) -> str:
    """Materialize the blob for ``content_hash`` as a **copy** at ``path``.

    Writes via a temporary file and an atomic rename, so a concurrent reader
    never sees a partial file.

    Why a copy and not a hard link
    ------------------------------
    Hard-linking the store's own blob file would be free, and an earlier cut of
    this function did exactly that — but a hard link makes the returned path
    and the content-store blob **the same inode**. Any consumer that writes
    through the returned path (ffmpeg writing in place, an accidental ``open(p,
    "ab")``) then leaves a blob whose SHA-256 no longer matches its own name,
    while ``has_blob`` keeps answering ``True`` — the store starts serving
    *wrong bytes under a correct content address*, which is precisely the
    failure class content addressing exists to eliminate. Making the link
    read-only instead is not an option either: the store's backend writes blobs
    with ``open(path, "wb")``, so a read-only blob breaks re-putting identical
    bytes.

    A copy costs disk (and, on APFS/btrfs/XFS, ``shutil.copyfile`` gets
    copy-on-write for free). Immutability of the content store is worth it.

    Returns ``path``.

    Raises:
        KeyError: the store holds no blob for ``content_hash``.
    """
    store = default_content_store() if store is None else store
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = f"{path}.{uuid.uuid4().hex[:8]}.part"
    source = store.blob_path(content_hash)
    try:
        if source is not None:
            shutil.copyfile(str(source), tmp)
        else:
            with open(tmp, "wb") as f:
                for chunk in store.iter_blob(content_hash):
                    f.write(chunk)
        os.replace(tmp, path)
    except BaseException:
        _unlink_quietly(tmp)
        raise
    return path


def _unlink_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# --- fetching ---------------------------------------------------------------


def _http_chunks(url: str, *, chunk_size: int = DFLT_CHUNK_SIZE) -> Iterator[bytes]:
    """Yield the bytes of ``url`` in ``chunk_size`` chunks. The default fetcher."""
    with urllib.request.urlopen(url) as resp:  # noqa: S310 (fal https URLs)
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                return
            yield chunk


def _fetch_into_store(url: str, store, fetcher: UrlFetcher) -> ContentRef:
    """Stream ``url`` through ``fetcher`` into ``store``; return the ContentRef.

    The byte count is accumulated *during* the stream, so falaw itself never
    holds the payload. Note that **peak process memory is still ~2x the asset**
    today: ``lacing.ArtifactStore.put_blob_stream`` accumulates into a
    ``bytearray`` and then copies it to ``bytes`` before writing (its own
    docstring says so, and thorwhalen/lacing#25 tracks replacing it with
    write-to-tempfile + atomic rename). Measured: a 64 MB asset peaks at
    ~129 MB. That is a lacing-side fix; nothing here needs to change when it
    lands.
    """
    counter = [0]

    def counted() -> Iterator[bytes]:
        for chunk in fetcher(url):
            counter[0] += len(chunk)
            yield chunk

    try:
        content_hash = store.put_blob_stream(counted())
    except Exception as e:  # noqa: BLE001 — re-raised as a typed falaw error
        raise FalAssetFetchError(
            f"Could not fetch asset bytes from {url!r}: {e}. falaw needs the "
            "bytes to content-address the artifact, and fal-served URLs expire "
            "and are then permanently deleted. If you are running an offline "
            "test suite whose stubbed responses carry made-up URLs, inject a "
            "transport (`asset_fetcher=` on falaw.execute_plan, or `fetcher=` "
            "here) rather than reaching for the network.",
            url=url,
            cause=e,
        ) from e
    if counter[0] == 0:
        raise FalAssetFetchError(
            f"Asset at {url!r} returned zero bytes — refusing to record an "
            "empty artifact as if it were valid media.",
            url=url,
        )
    return ContentRef(content_hash=content_hash, bytes_size=counter[0])


# --- the url -> ContentRef hint index ---------------------------------------


def _url_index_path(url: str) -> str:
    import hashlib

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    d = os.path.join(_cache_dir(), URL_INDEX_DIRNAME, digest[:2])
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{digest}.json")


def _remember_ref(url: str, ref: ContentRef) -> None:
    path = _url_index_path(url)
    tmp = f"{path}.{uuid.uuid4().hex[:8]}.part"
    with open(tmp, "w") as f:
        json.dump(
            {
                "url": url,
                "content_hash": ref.content_hash,
                "bytes_size": ref.bytes_size,
            },
            f,
        )
    os.replace(tmp, path)
