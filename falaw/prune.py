"""Capacity management for the falaw cache: see what is on disk, and reclaim it.

Before thorwhalen/falaw#14 the cache held kilobyte JSON manifests. It now
content-addresses every media result, so it also holds the **bytes** of every
generated image, clip and audio track. On any machine that has rendered a real
project that is gigabytes, and on the production box (a 40 GB volume) it is a
capacity question rather than a cosmetic one.

Nothing here runs automatically, and that is the design rather than an omission.
**Deleting a blob is a spending decision**: :func:`falaw.plan.execute` treats a
cache entry it cannot turn back into bytes as a *miss* and re-executes it, so
disk reclaimed today is re-billed the next time that beat renders. Every prune
is therefore ``dry_run=True`` by default and returns a :class:`PruneReport`
that says — before anything is removed — how many cache entries the prune would
put back on the invoice.

The cache has four areas, with very different economics:

``manifests``
    The fal responses, keyed by call. Small. Dropping one **re-bills that
    call**, unconditionally.
``content``
    The content-addressed blobs (falaw#14). This is where the gigabytes are.
    Dropping one re-bills every call whose asset URL has since expired — fal
    deletes expired files permanently, so the blob was the last copy.
``assets``
    :func:`falaw.materialize_asset` output — a *copy* of a blob, not a hard
    link (deliberately; see :func:`falaw.content.write_blob_to_file`). It
    doubles the on-disk cost of every materialized asset and is the **cheapest**
    thing to reclaim: while the blob survives, re-materializing is a local copy
    and costs nothing.
``url_index``
    ``url -> content hash`` hints. Tiny, and a pure hint — droppable freely, at
    the price of a re-download.

Examples
--------

What is actually on disk, broken down by area:

>>> usage = cache_usage()
>>> sorted(a.name for a in usage.areas)
['assets', 'content', 'manifests', 'url_index']

A prune is a dry run unless you say otherwise, and refuses to run unbounded:

>>> prune_content()
Traceback (most recent call last):
    ...
ValueError: prune_content needs a bound: pass older_than= and/or max_bytes=...
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterator, Optional, Sequence, Union

from .cache import ASSETS_DIRNAME, _cache_dir
from .content import CONTENT_STORE_DIRNAME, URL_INDEX_DIRNAME, remembered_ref


__all__ = [
    "AreaUsage",
    "CacheUsage",
    "PruneCandidate",
    "PruneReport",
    "cache_usage",
    "prune_assets",
    "prune_content",
    "prune_manifests",
]


MANIFESTS_AREA = "manifests"
CONTENT_AREA = "content"
ASSETS_AREA = "assets"
URL_INDEX_AREA = "url_index"

AREA_NAMES = (MANIFESTS_AREA, CONTENT_AREA, ASSETS_AREA, URL_INDEX_AREA)
"""Every area :func:`cache_usage` reports, in "cheapest to reclaim" *reverse* order."""

CONTENT_HASH_LENGTH = 64
"""Hex characters in a SHA-256 digest — how an asset filename's hash is found."""

Age = Union[float, int, timedelta]
"""An age bound: seconds, or a :class:`~datetime.timedelta`."""


# --- usage ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AreaUsage:
    """Disk usage of one cache area.

    ``entries`` counts the area's own unit — cache entries for ``manifests``,
    blobs for ``content``, files for ``assets`` and ``url_index`` — not files
    on disk, which is why it is reported next to ``bytes`` rather than derived
    from it.
    """

    name: str
    path: str
    entries: int
    bytes: int

    @property
    def megabytes(self) -> float:
        return round(self.bytes / 1_000_000, 2)


@dataclass(frozen=True, slots=True)
class CacheUsage:
    """Where the falaw cache's disk is going, by area.

    The whole point of the breakdown: ``size_bytes`` alone cannot tell you
    whether you are looking at gigabytes of irreplaceable blobs or gigabytes of
    ``assets/`` copies that cost nothing to regenerate.
    """

    root: str
    areas: tuple[AreaUsage, ...]

    @property
    def total_bytes(self) -> int:
        return sum(a.bytes for a in self.areas)

    @property
    def total_megabytes(self) -> float:
        return round(self.total_bytes / 1_000_000, 2)

    def area(self, name: str) -> AreaUsage:
        """The :class:`AreaUsage` named ``name``.

        Raises:
            KeyError: no such area. The valid names are :data:`AREA_NAMES`.
        """
        for a in self.areas:
            if a.name == name:
                return a
        raise KeyError(f"no cache area named {name!r}; expected one of {AREA_NAMES}")

    def summary(self) -> str:
        """One human-readable line per area, largest first."""
        lines = [f"falaw cache at {self.root}: {self.total_megabytes} MB total"]
        for a in sorted(self.areas, key=lambda a: a.bytes, reverse=True):
            lines.append(f"  {a.name:<10} {a.megabytes:>10} MB  ({a.entries} entries)")
        return "\n".join(lines)


def cache_usage() -> CacheUsage:
    """Disk usage of the falaw cache, broken down by area.

    The structured form behind :func:`falaw.cache_stats`. Read the module
    docstring for what each area costs to reclaim.
    """
    root = _cache_dir()
    return CacheUsage(
        root=root,
        areas=(
            _manifests_usage(root),
            _content_usage(root),
            _assets_usage(root),
            _url_index_usage(root),
        ),
    )


def _dir_bytes(path: str) -> tuple[int, int]:
    """``(file_count, total_bytes)`` under ``path``; ``(0, 0)`` when absent."""
    files = 0
    total = 0
    for dirpath, _dirs, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:  # vanished under us — a prune elsewhere, or a temp file
                continue
            files += 1
    return files, total


def _manifests_usage(root: str) -> AreaUsage:
    entries = 0
    total = 0
    for path in _iter_manifest_paths(root):
        entries += 1
        try:
            total += os.path.getsize(path)
        except OSError:
            continue
    return AreaUsage(name=MANIFESTS_AREA, path=root, entries=entries, bytes=total)


def _content_usage(root: str) -> AreaUsage:
    path = os.path.join(root, CONTENT_STORE_DIRNAME)
    # Count *blobs*, not files: `from_directory` also lays down a `catalog/`,
    # which falaw never writes but which would otherwise inflate the count.
    blobs_dir = os.path.join(path, "blobs")
    entries, _ = _dir_bytes(blobs_dir)
    _, total = _dir_bytes(path)
    return AreaUsage(name=CONTENT_AREA, path=path, entries=entries, bytes=total)


def _assets_usage(root: str) -> AreaUsage:
    path = os.path.join(root, ASSETS_DIRNAME)
    entries, total = _dir_bytes(path)
    return AreaUsage(name=ASSETS_AREA, path=path, entries=entries, bytes=total)


def _url_index_usage(root: str) -> AreaUsage:
    path = os.path.join(root, URL_INDEX_DIRNAME)
    entries, total = _dir_bytes(path)
    return AreaUsage(name=URL_INDEX_AREA, path=path, entries=entries, bytes=total)


def _iter_manifest_paths(root: Optional[str] = None) -> Iterator[str]:
    """Every ``manifest.json`` in the cache, skipping the three named areas.

    Cache entries live at ``<root>/<2-hex>/<key>/manifest.json``. The other
    areas are named directories (``content``, ``assets``, ``url_index``), none
    of which is two characters long, so the shard layout and the area layout
    cannot collide.
    """
    root = _cache_dir() if root is None else root
    skip = {CONTENT_STORE_DIRNAME, ASSETS_DIRNAME, URL_INDEX_DIRNAME}
    try:
        shards = os.listdir(root)
    except OSError:
        return
    for shard in shards:
        if shard in skip:
            continue
        shard_dir = os.path.join(root, shard)
        if not os.path.isdir(shard_dir):
            continue
        for dirpath, _dirs, filenames in os.walk(shard_dir):
            if "manifest.json" in filenames:
                yield os.path.join(dirpath, "manifest.json")


# --- prune reports ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PruneCandidate:
    """One thing a prune would delete (or did).

    ``last_modified`` is ``None`` when the age could not be determined — a
    non-filesystem blob backend, or a manifest too corrupt to read. Such a
    candidate is never selected by ``older_than`` (an unprovable age is not
    evidence of staleness) and is evicted last under ``max_bytes``.
    """

    key: str
    path: str
    bytes: int
    last_modified: Optional[float] = None


@dataclass(frozen=True, slots=True)
class PruneReport:
    """What a prune removed, or — with ``dry_run=True`` — would remove.

    ``rebillable_entries`` is the number this exists for: cache entries that
    will **cost money again** because of this prune. Its meaning is exact per
    area, and each is a different claim:

    - ``manifests`` — every dropped entry re-bills, so it equals the candidate
      count.
    - ``content`` — entries whose recorded response names an asset that resolves
      (through the ``url -> hash`` index) to a blob being dropped. Those become
      *unmaterializable* from cache; they re-download if fal still serves the
      URL and re-render if it does not, and falaw cannot tell which from here.
      This mirrors exactly the predicate :func:`falaw.plan.execute` uses to
      decide a hit is unusable, so it is the same population, not an estimate
      of it.
    - ``assets`` — only the copies whose blob is *also* gone. While the blob
      survives, re-materializing is a local copy and costs nothing.
    """

    area: str
    dry_run: bool
    candidates: tuple[PruneCandidate, ...] = ()
    kept_entries: int = 0
    kept_bytes: int = 0
    rebillable_entries: int = 0
    errors: tuple[str, ...] = field(default=())

    @property
    def freed_bytes(self) -> int:
        """Bytes freed — or, under ``dry_run``, that would be freed."""
        return sum(c.bytes for c in self.candidates)

    @property
    def freed_megabytes(self) -> float:
        return round(self.freed_bytes / 1_000_000, 2)

    def summary(self) -> str:
        """A human-readable line, phrased in the tense the run actually was."""
        verb = "would free" if self.dry_run else "freed"
        parts = [
            f"{self.area}: {verb} {self.freed_megabytes} MB "
            f"across {len(self.candidates)} entries "
            f"({self.kept_entries} kept, {round(self.kept_bytes / 1_000_000, 2)} MB)"
        ]
        if self.rebillable_entries:
            tense = "would become" if self.dry_run else "became"
            parts.append(
                f"  WARNING: {self.rebillable_entries} cache "
                f"{'entry' if self.rebillable_entries == 1 else 'entries'} "
                f"{tense} re-billable — re-running them costs money again"
            )
        if self.errors:
            parts.append(f"  {len(self.errors)} deletion(s) failed: {self.errors[0]}")
        return "\n".join(parts)


# --- selection --------------------------------------------------------------


def _as_seconds(older_than: Age) -> float:
    if isinstance(older_than, timedelta):
        return older_than.total_seconds()
    return float(older_than)


def _require_a_bound(func_name: str, older_than, max_bytes) -> None:
    """Refuse an unbounded prune.

    Neither reading is safe to guess: "delete everything" would silently make
    the whole cache re-billable, and "delete nothing" would make a command the
    caller believes reclaimed space a no-op.
    """
    if older_than is None and max_bytes is None:
        raise ValueError(
            f"{func_name} needs a bound: pass older_than= and/or max_bytes=. "
            "Refusing to guess whether an unbounded call means 'everything' "
            "or 'nothing' — one of those silently re-bills your whole cache."
        )


def _select(
    candidates: Sequence[PruneCandidate],
    *,
    older_than: Optional[Age],
    max_bytes: Optional[int],
    now: float,
) -> tuple[list[PruneCandidate], list[PruneCandidate]]:
    """Split ``candidates`` into ``(to_delete, to_keep)``.

    Age is the file's mtime — when falaw last **wrote** those bytes, not when
    it last read them. That is a deliberate limitation, not an oversight: POSIX
    atime is unreliable under ``relatime``/``noatime``, and falaw's hottest read
    path (:func:`falaw.materialize_asset` circle 1) never opens the blob at all,
    so a true LRU would need write-on-read bookkeeping on the path that exists
    to avoid I/O. Age-ordered eviction is what this is; it is not LRU and the
    docstrings do not claim to be.
    """
    doomed: list[PruneCandidate] = []
    survivors = list(candidates)

    if older_than is not None:
        cutoff = now - _as_seconds(older_than)
        aged = [
            c
            for c in survivors
            if c.last_modified is not None and c.last_modified < cutoff
        ]
        doomed.extend(aged)
        aged_ids = {id(c) for c in aged}
        survivors = [c for c in survivors if id(c) not in aged_ids]

    if max_bytes is not None:
        # Oldest first; unknown age last, so an unprovable age is evicted only
        # when dropping everything datable was not enough.
        survivors.sort(
            key=lambda c: (c.last_modified is None, c.last_modified or 0.0),
            reverse=True,
        )
        # `survivors` is now newest-first: keep from the front while under budget.
        kept: list[PruneCandidate] = []
        running = 0
        for c in survivors:
            if running + c.bytes <= max_bytes:
                kept.append(c)
                running += c.bytes
            else:
                doomed.append(c)
        survivors = kept

    return doomed, survivors


def _delete(paths_by_key, candidates: Sequence[PruneCandidate]) -> tuple[str, ...]:
    """Run ``paths_by_key`` over each candidate, collecting failures as strings.

    A prune that aborts halfway leaves the caller with neither the disk nor a
    report, so a failed deletion is recorded and the sweep continues.
    """
    errors = []
    for c in candidates:
        try:
            paths_by_key(c)
        except Exception as e:  # noqa: BLE001 — one bad file must not abort the sweep
            errors.append(f"{c.key}: {type(e).__name__}: {e}")
    return tuple(errors)


# --- content ----------------------------------------------------------------


def _blob_candidates(store) -> list[PruneCandidate]:
    blobs = getattr(store, "blobs", None)
    if blobs is None:
        return []
    out = []
    for content_hash in list(blobs):
        path = store.blob_path(content_hash)
        if path is not None:
            try:
                st = os.stat(path)
            except OSError:
                continue
            out.append(
                PruneCandidate(
                    key=content_hash,
                    path=str(path),
                    bytes=st.st_size,
                    last_modified=st.st_mtime,
                )
            )
        else:
            # Opaque backend (in-memory, object store): size is knowable, age
            # is not. `_select` keeps unknown-age blobs unless space forces it.
            try:
                size = len(blobs[content_hash])
            except Exception:  # noqa: BLE001 — an unreadable blob is not prunable data
                continue
            out.append(
                PruneCandidate(
                    key=content_hash, path="", bytes=size, last_modified=None
                )
            )
    return out


def _entries_referencing(hashes: set[str], root: str) -> int:
    """How many cache entries resolve their asset to one of ``hashes``.

    Walks manifests, extracts the response's asset URL exactly as
    :func:`falaw.plan.execute` does, and maps it through the ``url -> hash``
    hint index. An entry that fails any step is not counted: it is already
    unmaterializable, so this prune is not what breaks it.
    """
    if not hashes:
        return 0
    from .plan import extract_first_url

    count = 0
    for path in _iter_manifest_paths(root):
        try:
            with open(path) as f:
                manifest = json.load(f)
        except Exception:  # noqa: BLE001 — a corrupt manifest is already a miss
            continue
        url = extract_first_url(manifest.get("raw") or {})
        if not url:
            continue
        ref = remembered_ref(url)
        if ref is not None and ref.content_hash in hashes:
            count += 1
    return count


def prune_content(
    *,
    older_than: Optional[Age] = None,
    max_bytes: Optional[int] = None,
    dry_run: bool = True,
    store=None,
) -> PruneReport:
    """Reclaim content-addressed blobs — the gigabytes (falaw#22).

    This is the **expensive** prune. A blob is the last copy of an asset once
    fal has expired its URL ("expired files are permanently deleted and cannot
    be recovered"), so dropping one can turn a free cache hit into a re-rendered
    clip. The report says how many entries that applies to *before* you commit;
    read ``rebillable_entries``.

    Args:
        older_than: drop blobs last written more than this ago — seconds, or a
            :class:`~datetime.timedelta`.
        max_bytes: drop oldest-first until the area fits in this budget.
        dry_run: report without deleting. Default, deliberately.
        store: injected :class:`lacing.ArtifactStore`; defaults to
            :func:`falaw.content.default_content_store`.

    Returns:
        PruneReport: with ``area="content"``.

    Raises:
        ValueError: neither bound was given — see :func:`_require_a_bound`.

    Both bounds may be combined; a blob selected by either is dropped.

    >>> report = prune_content(older_than=timedelta(days=90))
    >>> report.dry_run
    True
    """
    _require_a_bound("prune_content", older_than, max_bytes)
    from .content import default_content_store

    store = default_content_store() if store is None else store
    root = _cache_dir()

    doomed, survivors = _select(
        _blob_candidates(store),
        older_than=older_than,
        max_bytes=max_bytes,
        now=time.time(),
    )
    rebillable = _entries_referencing({c.key for c in doomed}, root)

    errors: tuple[str, ...] = ()
    if not dry_run:
        errors = _delete(lambda c: store.blobs.__delitem__(c.key), doomed)

    return PruneReport(
        area=CONTENT_AREA,
        dry_run=dry_run,
        candidates=tuple(doomed),
        kept_entries=len(survivors),
        kept_bytes=sum(c.bytes for c in survivors),
        rebillable_entries=rebillable,
        errors=errors,
    )


# --- manifests --------------------------------------------------------------


def _manifest_candidates(root: str) -> list[PruneCandidate]:
    out = []
    for path in _iter_manifest_paths(root):
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        # `stored_at` is the truth (the manifest records when falaw wrote it);
        # mtime is the fallback for an entry too corrupt to parse.
        stored_at: Optional[float] = None
        try:
            with open(path) as f:
                stored_at = float(json.load(f).get("stored_at"))
        except Exception:  # noqa: BLE001 — fall back to the filesystem's opinion
            try:
                stored_at = os.path.getmtime(path)
            except OSError:
                stored_at = None
        out.append(
            PruneCandidate(
                key=os.path.basename(os.path.dirname(path)),
                path=path,
                bytes=size,
                last_modified=stored_at,
            )
        )
    return out


def prune_manifests(
    *,
    older_than: Optional[Age] = None,
    max_bytes: Optional[int] = None,
    dry_run: bool = True,
) -> PruneReport:
    """Reclaim cache entries — the fal responses themselves (falaw#22).

    Manifests are kilobytes, so this is rarely where the disk is; it is here
    because a stale *entry* is its own problem — it pins a model version and a
    price you may no longer want served from cache.

    Unlike :func:`prune_content`, the cost is unconditional: every dropped
    entry re-bills its call on the next run, so ``rebillable_entries`` always
    equals the candidate count.

    Args:
        older_than: drop entries stored more than this ago — seconds, or a
            :class:`~datetime.timedelta`. Read from the manifest's own
            ``stored_at``, falling back to file mtime.
        max_bytes: drop oldest-first until the area fits in this budget.
        dry_run: report without deleting. Default, deliberately.

    Returns:
        PruneReport: with ``area="manifests"``.

    Raises:
        ValueError: neither bound was given.

    Only the manifest is removed; blobs are shared by content hash across
    entries and are never dropped from here — the same rule
    :func:`falaw.drop_cache_entry` follows.
    """
    _require_a_bound("prune_manifests", older_than, max_bytes)
    root = _cache_dir()
    doomed, survivors = _select(
        _manifest_candidates(root),
        older_than=older_than,
        max_bytes=max_bytes,
        now=time.time(),
    )
    errors: tuple[str, ...] = ()
    if not dry_run:
        errors = _delete(lambda c: os.remove(c.path), doomed)
    return PruneReport(
        area=MANIFESTS_AREA,
        dry_run=dry_run,
        candidates=tuple(doomed),
        kept_entries=len(survivors),
        kept_bytes=sum(c.bytes for c in survivors),
        rebillable_entries=len(doomed),
        errors=errors,
    )


# --- assets -----------------------------------------------------------------


def _content_hash_in_asset_name(filename: str) -> Optional[str]:
    """The content hash embedded in a :func:`falaw.materialize_asset` filename.

    The layout is ``{key_hint-}{content_hash}{ext}``, so the hash is the last
    64 hex characters of the stem. ``None`` when the name does not fit — a file
    falaw did not write, which is reason enough not to reason about it.
    """
    stem = os.path.splitext(filename)[0]
    if len(stem) < CONTENT_HASH_LENGTH:
        return None
    tail = stem[-CONTENT_HASH_LENGTH:]
    try:
        int(tail, 16)
    except ValueError:
        return None
    return tail


def _asset_candidates(root: str) -> list[PruneCandidate]:
    path = os.path.join(root, ASSETS_DIRNAME)
    out = []
    try:
        names = os.listdir(path)
    except OSError:
        return out
    for name in names:
        full = os.path.join(path, name)
        try:
            st = os.stat(full)
        except OSError:
            continue
        if not os.path.isfile(full):
            continue
        out.append(
            PruneCandidate(
                key=name, path=full, bytes=st.st_size, last_modified=st.st_mtime
            )
        )
    return out


def prune_assets(
    *,
    older_than: Optional[Age] = None,
    max_bytes: Optional[int] = None,
    dry_run: bool = True,
    store=None,
) -> PruneReport:
    """Reclaim materialized asset copies — the cheapest disk in the cache (falaw#22).

    ``assets/`` holds a **copy** of each blob rather than a hard link, which is
    deliberate (:func:`falaw.content.write_blob_to_file` explains why a link
    would let a consumer corrupt the content store) but doubles the on-disk cost
    of every materialized asset. That makes this the prune to reach for first:
    while a blob survives, re-materializing its asset is a local copy and costs
    nothing, so ``rebillable_entries`` counts only the copies whose blob is
    *also* gone.

    Args:
        older_than: drop copies last written more than this ago — seconds, or a
            :class:`~datetime.timedelta`.
        max_bytes: drop oldest-first until the area fits in this budget.
        dry_run: report without deleting. Default, deliberately.
        store: injected :class:`lacing.ArtifactStore`, used only to ask whether
            each dropped copy still has a blob behind it; defaults to
            :func:`falaw.content.default_content_store`.

    Returns:
        PruneReport: with ``area="assets"``.

    Raises:
        ValueError: neither bound was given.
    """
    _require_a_bound("prune_assets", older_than, max_bytes)
    from .content import default_content_store

    store = default_content_store() if store is None else store
    root = _cache_dir()
    doomed, survivors = _select(
        _asset_candidates(root),
        older_than=older_than,
        max_bytes=max_bytes,
        now=time.time(),
    )
    orphaned = 0
    for c in doomed:
        content_hash = _content_hash_in_asset_name(c.key)
        if content_hash is None or not store.has_blob(content_hash):
            orphaned += 1

    errors: tuple[str, ...] = ()
    if not dry_run:
        errors = _delete(lambda c: os.remove(c.path), doomed)

    return PruneReport(
        area=ASSETS_AREA,
        dry_run=dry_run,
        candidates=tuple(doomed),
        kept_entries=len(survivors),
        kept_bytes=sum(c.bytes for c in survivors),
        rebillable_entries=orphaned,
        errors=errors,
    )
