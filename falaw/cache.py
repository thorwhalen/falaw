"""Content-addressed cache for fal calls.

Why this exists: the directorial workflow ("a single edit, the scene
re-renders around it") only works if unchanged beats *don't* re-render.
A cache hit is the difference between a 30-second edit-and-preview
loop and a 5-minute one.

Design:

* Key = SHA256 of (model_id, sorted(arguments_json)). Two structurally
  identical fal calls collapse to the same key.
* Value = the raw fal response, plus optional locally-downloaded asset
  paths. We persist both the JSON manifest and the binary downloads.
* Cache root: ``$FALAW_CACHE_DIR`` or ``$FALAW_DATA_DIR/cache`` or
  ``~/.config/falaw/cache``.
* The cache is *per-process* aware via lru_cache for hot lookups;
  on-disk for persistence across runs.

**The key arguments are not always the wire arguments.** A chained plan
(``generate_image`` → ``image_to_video``) sends fal a *URL* for the upstream
image, but a URL is minted fresh per upload — so keying on it guarantees a
miss the moment the upstream is genuinely re-executed, and the miss re-bills
the expensive downstream call for unchanged work. :func:`cached_call_fal`
therefore takes an optional ``key_arguments``: the same call with upstream
references resolved to **content hashes** (``sha256:<hex>``) instead of URLs.
See :mod:`falaw.content` for how those hashes are produced.

Usage:

    from falaw.cache import cached_call_fal
    raw = cached_call_fal("fal-ai/flux/dev", {"prompt": "..."})

The wrapped variant has the same signature as `core.call_fal` but skips
the network when the (model_id, arguments) tuple was seen before.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any, Mapping, Optional

from .core import call_fal


# --- cache root -----------------------------------------------------------


def _cache_dir() -> str:
    base = (
        os.environ.get("FALAW_CACHE_DIR")
        or (
            os.environ.get("FALAW_DATA_DIR")
            and os.path.join(os.environ["FALAW_DATA_DIR"], "cache")
        )
        or os.path.expanduser("~/.config/falaw/cache")
    )
    os.makedirs(base, exist_ok=True)
    return base


def _key(application: str, arguments: Mapping[str, Any]) -> str:
    blob = json.dumps(
        {"app": application, "args": dict(arguments)},
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _entry_dir(key: str) -> str:
    # Two-char shard so the cache directory listing stays manageable.
    d = os.path.join(_cache_dir(), key[:2], key)
    os.makedirs(d, exist_ok=True)
    return d


def _manifest_path(key: str) -> str:
    return os.path.join(_entry_dir(key), "manifest.json")


# --- public API -----------------------------------------------------------


def cache_get(application: str, arguments: Mapping[str, Any]) -> Optional[dict]:
    """Return the raw fal response if cached, else None."""
    path = _manifest_path(_key(application, arguments))
    if not os.path.exists(path):
        return None
    with open(path) as f:
        manifest = json.load(f)
    return manifest.get("raw")


def cache_put(
    application: str,
    arguments: Mapping[str, Any],
    raw: dict,
    *,
    note: str = "",
    wire_arguments: Optional[Mapping[str, Any]] = None,
) -> str:
    """Persist a fal response. Returns the entry directory path.

    Args:
        application: fal model id.
        arguments: the arguments the entry is **keyed** on.
        raw: the fal response to store.
        note: free-form label recorded in the manifest.
        wire_arguments: the arguments actually sent to fal, when they differ
            from the key arguments (chained calls send URLs but are keyed on
            content hashes). Recorded for debugging only — it never affects
            the key.

    The manifest is written to a temporary file and moved into place with
    :func:`os.replace`, so a reader never sees a half-written entry. That is not
    hypothetical since ``execute_plan(concurrency=N)``: two calls of one Plan
    that are structurally identical land on the same key, and an interleaved
    ``json.dump`` would leave a permanently unparseable entry — a cache that
    poisons itself under exactly the fan-out it exists to make cheap.
    """
    key = _key(application, arguments)
    d = _entry_dir(key)
    manifest = {
        "key": key,
        "application": application,
        "arguments": dict(arguments),
        "raw": raw,
        "note": note,
        "stored_at": time.time(),
    }
    if wire_arguments is not None:
        manifest["wire_arguments"] = dict(wire_arguments)
    path = _manifest_path(key)
    tmp = f"{path}.{uuid.uuid4().hex[:8]}.part"
    try:
        with open(tmp, "w") as f:
            json.dump(manifest, f, indent=2, default=str)
        os.replace(tmp, path)
    except BaseException:
        _unlink_quietly(tmp)
        raise
    return d


def _unlink_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def drop_cache_entry(application: str, arguments: Mapping[str, Any]) -> bool:
    """Delete the cache entry for ``(application, arguments)``. Returns whether one existed.

    The counterpart to :func:`cache_put`, and the mechanism that keeps a cache
    from becoming a *trap*. An entry whose response can no longer be turned
    into a usable artifact — fal deleted the URL and the bytes are not in the
    content store — must be a **miss**, not a permanent failure: without this,
    the only escape is ``use_cache=False``, which re-bills the whole plan
    rather than the one dead call. :func:`falaw.plan.execute` calls it.

    Only the manifest is removed. Blobs in the content store are shared by
    content hash across entries and are never dropped from here.
    """
    path = _manifest_path(_key(application, arguments))
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


def emit_cache_hit(application: str, on_event=None) -> None:
    """Emit the synthetic ``cache_hit`` progress event for ``application``.

    Shared by :func:`cached_call_fal` and :func:`falaw.plan.execute` (which
    drives the cache directly, because it must decide whether a hit is
    *usable* before committing to it) so a UI sees one event shape either way.
    """
    import uuid as _uuid

    from .events import ProgressEvent, emit

    emit(
        ProgressEvent(
            kind="cache_hit",
            application=application,
            call_id=_uuid.uuid4().hex[:12],
        ),
        also=(on_event,) if on_event else (),
    )


def cached_call_fal(
    application: str,
    arguments: Mapping[str, Any],
    *,
    key_arguments: Optional[Mapping[str, Any]] = None,
    refresh: bool = False,
    on_event=None,
) -> dict:
    """Call a fal model, but reuse the cached response when present.

    Args:
        application: fal model id.
        arguments: model input dict — what is sent **on the wire**.
        key_arguments: what the cache entry is **keyed** on, when that differs
            from what goes on the wire. Defaults to ``arguments``. The split
            exists because a chained call must send fal an expiring URL for its
            upstream input while being keyed on that input's *content hash*, so
            a byte-identical upstream regeneration hits instead of re-billing.
        refresh: if True, bypass the cache and overwrite it with a fresh result.
        on_event: Per-call subscriber for :class:`falaw.events.ProgressEvent`.
            On a cache hit, a synthetic ``cache_hit`` event is emitted so
            UIs can show "skipped" instead of "running".

    Returns:
        Raw fal response (whether from cache or network).
    """
    key_args = arguments if key_arguments is None else key_arguments
    if not refresh:
        hit = cache_get(application, key_args)
        if hit is not None:
            emit_cache_hit(application, on_event)
            return hit
    raw = call_fal(application, arguments, on_event=on_event)
    cache_put(
        application,
        key_args,
        raw,
        wire_arguments=None if key_arguments is None else arguments,
    )
    return raw


def materialize_asset(
    url: str,
    *,
    key_hint: str = "",
    store=None,
    fetcher=None,
    refresh: bool = False,
) -> str:
    """Download a remote asset to the cache and return the local path.

    The local filename is content-addressed by the asset's **bytes**, so two
    URLs serving identical bytes resolve to one file. The extension is a
    presentational hint for ffmpeg/PIL; the SHA-256 is the address.

    Repeat calls are free, in three widening circles — this is what makes it
    safe to call from a loop over 200 shots:

    1. the file is already on disk here (no store lookup, no network);
    2. the bytes are in the content store (no network) — so it still works
       after fal has expired the URL;
    3. otherwise, one download.

    Circle 1 matters on its own: the content store is prunable, so an asset
    can survive as a materialized file after its blob is gone.

    Args:
        url: the remote asset URL. ``file://`` is supported and is used
            deliberately by downstream packages for locally-rendered media.
        key_hint: optional human-readable filename prefix.
        store: injected :class:`lacing.ArtifactStore`; defaults to
            :func:`falaw.content.default_content_store`.
        fetcher: injected byte source (``url -> Iterable[bytes]``); defaults to
            the ``urllib``-based one. The seam for custom transport (auth
            headers, retries) and for a hermetic test suite.
        refresh: re-fetch even when a remembered content hash exists. Pass this
            for a **mutable** URL — the ``url -> hash`` hint index assumes the
            URL is immutable, which is true of fal's own but not of an
            arbitrary one.

    Raises:
        falaw.errors.FalAssetFetchError: the bytes could not be retrieved.
            Unlike a generated-media artifact (which degrades to URL-only —
            see :func:`falaw.plan.execute`), there is nothing to degrade to
            here: the caller asked for a local file.
    """
    # Local import: ``falaw.content`` imports ``_cache_dir`` from this module,
    # so importing it at module scope would be a cycle.
    from .content import content_ref_for_url, remembered_ref, write_blob_to_file

    if not refresh:
        hint = remembered_ref(url)
        if hint is not None:
            path = _asset_path(url, key_hint, hint.content_hash)
            if os.path.exists(path):
                return path
    ref = content_ref_for_url(url, store=store, fetcher=fetcher, refresh=refresh)
    path = _asset_path(url, key_hint, ref.content_hash)
    if os.path.exists(path):
        return path
    return write_blob_to_file(ref.content_hash, path, store=store)


def _asset_path(url: str, key_hint: str, content_hash: str) -> str:
    """Where :func:`materialize_asset` puts the bytes for ``content_hash``."""
    ext = _infer_ext_from_url(url)
    fname = f"{key_hint + '-' if key_hint else ''}{content_hash}{ext}"
    return os.path.join(_cache_dir(), "assets", fname)


def _infer_ext_from_url(url: str) -> str:
    base = url.split("?", 1)[0]
    for ext in (
        ".mp4",
        ".mov",
        ".webm",
        ".mp3",
        ".wav",
        ".m4a",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    ):
        if base.lower().endswith(ext):
            return ext
    return ".bin"


def cache_stats() -> dict:
    """Quick summary of the cache: entry count and disk usage."""
    root = _cache_dir()
    entries = 0
    total_bytes = 0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            entries += int(f == "manifest.json")
            total_bytes += os.path.getsize(os.path.join(dirpath, f))
    return {
        "root": root,
        "manifest_entries": entries,
        "size_bytes": total_bytes,
        "size_mb": round(total_bytes / 1_000_000, 2),
    }
