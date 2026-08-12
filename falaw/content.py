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
* remembers ``url -> (content_hash, bytes_size, validators)`` in a small
  on-disk index, so re-executing an already-cached plan does **not** re-download
  anything. The index is a *hint*, never an identity, and it is only **sound for
  immutable URLs** — so falaw decides, per URL, whether it may be trusted
  (thorwhalen/falaw#23):

  - a **fal-served** URL is trusted outright, because fal guarantees a URL is
    minted per upload and therefore never re-points at different bytes;
  - **anything else** — an arbitrary caller-supplied ``https://…/reference.png``
    reached through :func:`falaw.cache.materialize_asset`, or a ``file://`` clip
    that gets re-rendered to the same path — is **revalidated** before reuse: a
    conditional request replaying the recorded ``ETag`` / ``Last-Modified``, or
    a ``(mtime, size)`` check for a local file. ``304`` costs a round-trip and
    no payload; a changed asset yields a changed content hash, as it must.

  When falaw *cannot* check — no validators recorded, or an injected transport
  with no conditional-request support — it re-fetches rather than trusting. An
  unverifiable hint is not evidence. :func:`is_immutable_url` is the predicate,
  and :data:`IMMUTABLE_URL_HOSTS` is where you add a host you mint yourself;
* serves the bytes from the store after the URL has expired, so a months-old
  cache hit still yields a usable artifact instead of a dead link.

The blob store is **injected**, never constructed inline by callers:
:func:`default_content_store` is the falaw-cache-rooted default, and every
public function here takes a ``store`` keyword so a caller can point falaw at
an S3-backed store without touching any other code.

So is the **transport**. Per call it is the ``fetcher=`` / ``asset_fetcher=``
argument; for a whole process it is :func:`using_url_fetcher`, which covers
:func:`content_ref_for_url`, :func:`falaw.materialize_asset`,
:func:`falaw.execute_plan` and :func:`falaw.execute_plan_isolated` in one
place. That matters most to *downstream* test suites: falaw content-addresses
every media result, so a suite that stubs the fal response but not the
transport resolves its made-up URLs for real — and stays green while doing it,
because a failed fetch degrades to a URL-only artifact with a warning rather
than raising. :mod:`falaw.testing` ships the fake so no consumer has to write
one.

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
import re
import shutil
import warnings
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, Optional

from .cache import _cache_dir
from .degrade import emit_degradation
from .errors import FalAssetFetchError


__all__ = [
    "ConditionalOutcome",
    "ContentRef",
    "UrlFetcher",
    "Validators",
    "content_ref_for_url",
    "default_content_store",
    "default_url_fetcher",
    "is_immutable_url",
    "remembered_ref",
    "using_url_fetcher",
    "write_blob_to_file",
]


DFLT_CHUNK_SIZE = 1 << 16
"""Bytes per read when streaming a remote asset into the blob store."""

IMMUTABLE_URL_HOSTS = {"fal.media", "fal.run"}
"""Hosts whose URLs are minted per upload and never re-point at other bytes.

A **mutable** set, deliberately: a deployment that serves generated media from
its own immutable-by-construction store (content-addressed object storage, a
CDN with digest-named keys) adds its host here rather than paying a
revalidation round-trip per asset. Adding a host that is *not* immutable
re-introduces thorwhalen/falaw#23, so add only what you mint yourself.
"""

_FETCH_FAILED = (
    "Could not fetch asset bytes from {url}: {error}. falaw needs the bytes to "
    "content-address the artifact, and fal-served URLs expire and are then "
    "permanently deleted. If you are running an offline test suite whose "
    "stubbed responses carry made-up URLs, install a fake transport "
    "(`falaw.testing.fake_assets`, or `falaw.content.using_url_fetcher`) rather "
    "than reaching for the network."
)
"""The one fetch-failure message.

Shared by the eager path (a transport that fails at request time) and the lazy
one (a transport that fails mid-stream). They used to differ, and the eager one
— which the built-in transport now always takes, because a conditional request
calls `urlopen` before returning chunks — was the terse one, losing exactly the
guidance `falaw.testing` exists to give.
"""

GONE_HTTP_STATUSES = frozenset({404, 410})
"""Statuses that mean the asset is gone, rather than momentarily unreachable.

The whole list, deliberately. ``5xx``, ``429`` and every transport error are
*transient* until proven otherwise, and serving stored bytes in response to one
is how a superseded content hash gets reported as current forever.
"""

_NETLOC_FORBIDDEN = ("\\", "%", "@", " ", "\t", "\n", "\r", "\x00")
"""Characters that disqualify a netloc from ever being judged immutable.

Not a hostname-validity rule — a *parser-agreement* rule. Each of these is read
differently by Python's ``urlsplit`` and by a WHATWG-conformant client
(``requests``/``urllib3``), so a netloc containing one means falaw's idea of the
host and the transport's idea of the host may differ. ``@`` is included even
though Python handles it consistently: userinfo has no legitimate role in a
media URL, and every spoof of the form ``https://fal.media@evil.example/x``
depends on it.
"""

_HOSTNAME_RE = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?")
"""A plain DNS name. Anything else is refused by :func:`is_immutable_url`.

Deliberately narrow. The job is not to validate hostnames but to guarantee that
falaw's idea of the host and the transport's idea of the host cannot diverge —
which they do the moment a netloc contains a character Python treats as data
and a WHATWG-conformant client treats as a delimiter.
"""

CONTENT_STORE_DIRNAME = "content"
"""Sub-directory of the falaw cache holding the default content store."""

URL_INDEX_DIRNAME = "url_index"
"""Sub-directory of the falaw cache holding the ``url -> ContentRef`` hints."""


UrlFetcher = Callable[[str], Iterable[bytes]]
"""A callable that yields the bytes of a URL in chunks.

The injection seam for tests and for callers that need custom transport
(auth headers, retries, a local mirror). :func:`default_url_fetcher` resolves
the one in force; :func:`using_url_fetcher` installs another.
"""


_DEFAULT_FETCHER: Optional[UrlFetcher] = None
"""Process-wide override of the transport, or ``None`` for the built-in one.

A plain module global rather than a :class:`~contextvars.ContextVar`, and the
difference is load-bearing. This value has to be visible from **every** thread,
including threads the installer never created: a downstream job runner executes
falaw calls on its own worker pool, and a per-context override set on the main
thread would silently not apply there — leaving a suite that believes it is
hermetic quietly reaching for the network. (Contrast
``falaw.plan._DEGRADE_WARNING_SINK``, which *is* a ContextVar precisely because
it must **not** be shared between concurrently executing calls.)

Consequence to accept: two different fetchers cannot be in force at once in one
process. That is the right trade for what this is — deployment/test
configuration, not per-call state. Per-call transport already has a better
mechanism: the ``fetcher=`` / ``asset_fetcher=`` argument, which always wins.
"""


def default_url_fetcher() -> UrlFetcher:
    """The transport used when no ``fetcher=`` argument is given.

    :func:`using_url_fetcher`'s installed fetcher if there is one, else the
    built-in ``urllib``-based one. Resolved at call time, so every falaw entry
    point that reads asset bytes — :func:`content_ref_for_url`,
    :func:`falaw.materialize_asset`, :func:`falaw.execute_plan` and
    :func:`falaw.execute_plan_isolated` — honours an override installed after
    they were imported.
    """
    return _http_chunks if _DEFAULT_FETCHER is None else _DEFAULT_FETCHER


@contextmanager
def using_url_fetcher(fetcher: UrlFetcher) -> Iterator[UrlFetcher]:
    """Make ``fetcher`` falaw's default asset transport for the duration.

    The **public seam** for replacing falaw's network transport wholesale —
    with an authenticated client, a retrying one, a local mirror, or (the
    common case) an in-memory fake in a test suite.

    Prefer this to reaching for the module's private default: it covers every
    entry point in one place, it needs no ``monkeypatch``, and it cannot be
    invalidated by an internal rename. It is also the only mechanism that
    reaches a call falaw makes from a thread you did not create — see
    :data:`_DEFAULT_FETCHER` for why that matters.

    An explicitly passed ``fetcher=`` / ``asset_fetcher=`` still wins: this
    changes the *default*, never an explicit choice.

    Nests and restores, so an inner block cannot leak over an outer one:

    >>> from lacing import ArtifactStore
    >>> store = ArtifactStore.in_memory()
    >>> before = default_url_fetcher()
    >>> with using_url_fetcher(lambda url: [b"faked"]):
    ...     content_ref_for_url("https://fal.media/x.png", store=store).bytes_size
    5
    >>> default_url_fetcher() is before
    True

    For a ready-made fake with pinned bytes and 404s, see :mod:`falaw.testing`.
    """
    global _DEFAULT_FETCHER
    previous = _DEFAULT_FETCHER
    _DEFAULT_FETCHER = fetcher
    try:
        yield fetcher
    finally:
        _DEFAULT_FETCHER = previous


@dataclass(frozen=True, slots=True)
class Validators:
    """What an origin gave us to ask "are these bytes still current?" cheaply.

    ``etag`` and ``last_modified`` are the HTTP response headers of the same
    names, replayed as ``If-None-Match`` / ``If-Modified-Since`` on the next
    read. A ``file://`` URL has neither, so falaw synthesises an ``etag`` from
    the file's ``(mtime_ns, size)`` — see :func:`_file_validators`. Falsy when
    the origin offered nothing, which is the case falaw must treat as
    "cannot revalidate", never as "unchanged".
    """

    etag: str = ""
    last_modified: str = ""

    def __bool__(self) -> bool:
        return bool(self.etag or self.last_modified)


@dataclass(frozen=True, slots=True)
class ConditionalOutcome:
    """The result of asking an origin whether a URL's bytes changed.

    Either ``not_modified`` (the remembered content hash still stands, at the
    cost of one round-trip and no payload), or the **new** bytes — carried here
    rather than re-requested, because a caller that discovers staleness has
    already paid for the response body.
    """

    not_modified: bool
    chunks: Optional[Iterable[bytes]] = None
    validators: "Validators" = Validators()


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


def is_immutable_url(url: str) -> bool:
    """Whether ``url`` is guaranteed never to serve different bytes later.

    True only for hosts falaw knows mint a fresh URL per upload —
    :data:`IMMUTABLE_URL_HOSTS`, which is fal's own CDN out of the box, and any
    **subdomain** of one. **Everything else is mutable**, including ``file://``:
    a locally-rendered clip re-rendered to the same path is the textbook case of
    one URL serving two different things.

    The default is the safe one on purpose. Guessing "probably immutable" for
    an unknown host is what thorwhalen/falaw#23 was: a changed input producing
    an unchanged content address, silently, with the stale hash flowing into
    ``Artifact.asset_id`` and every downstream cache key.

    Two rules make this a *security* boundary rather than a string comparison,
    and both were added after a review reproduced falaw#23 against the first
    cut of this function:

    1. **The host must be a plain DNS name.** ``urlsplit().hostname`` is not
       what an HTTP client resolves. Python accepts a backslash (and ``%2F``)
       inside a netloc, while WHATWG-conformant clients — including
       ``requests``/``urllib3`` — treat them as *delimiters*. So
       ``http://127.0.0.1:8000\\@fal.media/x`` parses here with hostname
       ``fal.media`` and is fetched from ``127.0.0.1``. Anything outside
       ``[a-z0-9.-]`` is therefore refused outright.
    2. **Matching is label-wise, never by raw suffix.** ``endswith(".fal.media")``
       is true of ``evil.com\\.fal.media``; ``host == h or host.endswith("." + h)``
       is not.

    >>> is_immutable_url("https://v3b.fal.media/files/x.png")
    True
    >>> is_immutable_url("https://fal.media/files/x.png")
    True
    >>> is_immutable_url("https://example.com/reference.png")
    False
    >>> is_immutable_url("file:///tmp/render.mp4")
    False

    A host that merely *contains* a trusted name is not that host, however it
    is spelled:

    >>> is_immutable_url("https://fal.media@evil.example/x.png")
    False
    >>> is_immutable_url("https://notfal.media/x.png")
    False
    >>> is_immutable_url("http://127.0.0.1:8000\\\\@fal.media/x.png")
    False
    """
    split = urllib.parse.urlsplit(url)
    # Judge the *raw* netloc first. `split.hostname` has already made a choice
    # about where the host ends, and that choice is the one an attacker
    # controls: Python splits userinfo on the last `@` and treats `\` as data,
    # so `http://127.0.0.1:8000\@fal.media/x` hands back `fal.media` while
    # requests/urllib3 fetch from `127.0.0.1`. Any netloc carrying a character
    # two conformant parsers can read differently is refused before the host is
    # even looked at — and userinfo is refused outright, because a media URL has
    # no use for it and its only role here is to move the apparent host.
    if not split.netloc or any(c in split.netloc for c in _NETLOC_FORBIDDEN):
        return False
    host = (split.hostname or "").lower().rstrip(".")
    if not host or not _HOSTNAME_RE.fullmatch(host):
        return False
    return any(
        host == trusted or host.endswith("." + trusted)
        for trusted in IMMUTABLE_URL_HOSTS
    )


def content_ref_for_url(
    url: str,
    *,
    store=None,
    fetcher: Optional[UrlFetcher] = None,
    refresh: bool = False,
    assume_immutable: Optional[bool] = None,
) -> ContentRef:
    """Materialize ``url``'s bytes into ``store`` and return their content hash.

    Idempotent and cheap on repeat, but *how* cheap depends on whether the URL
    can change behind falaw's back — and falaw decides that rather than asking
    the caller to know (thorwhalen/falaw#23):

    1. **Immutable URL** (fal's own — see :func:`is_immutable_url`) with a
       remembered hash whose blob is present: returned immediately, **no
       network**. This is what makes re-executing an already-cached plan free
       rather than re-downloading every clip.
    2. **Mutable URL** with a remembered hash: falaw **revalidates** — a
       conditional ``GET`` replaying the recorded ``ETag`` / ``Last-Modified``
       (for ``file://``, a ``(mtime, size)`` comparison). A ``304`` costs one
       round-trip and no payload; a ``200`` means the bytes really changed and
       the new ones are stored, so the content hash changes with them.
    3. **No usable answer** — nothing remembered, no validators recorded, or a
       transport that cannot make conditional requests: a plain fetch.

    Step 3 is the important default. A transport that cannot revalidate makes
    falaw **re-fetch**, never trust: an unverifiable hint is not evidence.

    Args:
        url: The asset URL. ``file://`` is supported and treated as mutable.
        store: Injected :class:`lacing.ArtifactStore`; defaults to
            :func:`default_content_store`.
        fetcher: Injected byte source; defaults to :func:`default_url_fetcher`
            (the built-in ``urllib`` transport unless :func:`using_url_fetcher`
            has installed another). To support revalidation, a custom transport
            exposes a ``conditional_fetch(url, validators) -> ConditionalOutcome``
            attribute; without one it is simply never asked.
        refresh: Skip every shortcut and re-fetch unconditionally. Rarely needed
            now that mutable URLs revalidate on their own — keep it for a URL
            whose origin lies about its validators.
        assume_immutable: Override the host-based decision. ``True`` restores
            the old unconditional trust (use for a host you mint yourself, and
            prefer adding it to :data:`IMMUTABLE_URL_HOSTS`); ``False`` forces
            revalidation even for fal.

    Raises:
        FalAssetFetchError: the bytes could not be retrieved, or the response
            was empty. Never returns a reference it could not back with bytes —
            a silent zero-byte "artifact" is the failure mode this guards.
    """
    store = default_content_store() if store is None else store
    fetcher = fetcher or default_url_fetcher()
    record = None if refresh else _remembered_record(url)
    have_blob = record is not None and store.has_blob(record.ref.content_hash)

    if have_blob:
        immutable = (
            is_immutable_url(url) if assume_immutable is None else assume_immutable
        )
        if immutable:
            return record.ref

    # Offer validators only when the blob is actually here. A `304` is an
    # instruction to serve the copy you already have, so asking for one without
    # a copy would earn an answer carrying no bytes and nothing to fall back on
    # — the HTTP rule for `If-None-Match`, and the same reason for it.
    validators = record.validators if have_blob else Validators()
    try:
        outcome = _read(url, fetcher, validators)
    except FalAssetFetchError as e:
        # The origin is **gone**, and we already hold the bytes. Serving them is
        # the falaw#14 guarantee — "a months-old cache hit still yields a usable
        # artifact instead of a dead link" — and it does not reintroduce
        # falaw#23: there is no newer version being shadowed, because there is
        # no newer version.
        #
        # Only for a *definitive* absence, though. An earlier cut caught every
        # error here, which meant a timeout, a 500, a 429 or a rate-limit made
        # falaw report the superseded hash as current — on that call and every
        # later one. That inverts this fallback's own justification: the truth
        # was available, falaw looked, and answered from memory anyway.
        if have_blob and _is_definitively_gone(e):
            emit_degradation(
                f"{url!r} is gone from its origin ({e}); serving the "
                f"{record.ref.bytes_size} bytes falaw stored earlier. If that "
                "URL was mutable, this content hash may name superseded bytes."
            )
            return record.ref
        raise
    if outcome.not_modified:
        # Believe "unchanged" only when there is something unchanged to serve.
        # `have_blob` gates *sending* validators, but a transport is not
        # obliged to be correct, and this module's own thesis — an unverifiable
        # claim is not evidence — applies at least as much to an injected
        # transport as to an index entry falaw wrote itself.
        if not have_blob:
            raise FalAssetFetchError(
                f"Transport answered 'not modified' for {url!r}, but falaw holds "
                "no bytes for it. A conditional_fetch may only answer "
                "not_modified to validators it was given, and none were sent.",
                url=url,
            )
        return record.ref
    # Outside the `try`: a failure to *store* is not the origin being gone. An
    # earlier cut had `_store_chunks` inside it, so a full disk — the exact
    # condition `falaw.prune` exists for — discarded bytes already in hand and
    # returned the previous content hash for them.
    ref = _store_chunks(url, outcome.chunks or (), store)
    _remember_ref(url, ref, outcome.validators)
    return ref


def _is_definitively_gone(error: FalAssetFetchError) -> bool:
    """Whether ``error`` proves the asset no longer exists at its origin.

    True only for an answer that cannot be transient: HTTP ``404``/``410``, or a
    local file that is not there. A timeout, a refused connection, a ``5xx``, a
    ``429`` and a DNS failure are all **false** — they say the origin could not
    be *reached*, which is a different claim from the asset being gone, and
    treating them alike is what let a stale hash be reported as current
    indefinitely.
    """
    cause = getattr(error, "cause", None)
    if isinstance(cause, urllib.error.HTTPError):
        return cause.code in GONE_HTTP_STATUSES
    return isinstance(cause, FileNotFoundError)


def _conditional_capability(fetcher: UrlFetcher):
    """``fetcher``'s conditional-request capability, or ``None``.

    Checks the callable, and — when it is a **bound method** — the object it is
    bound to. That second lookup is not a nicety: the documented way to install
    :class:`falaw.testing.FakeAssets` is ``using_url_fetcher(assets.chunks)``,
    which hands falaw a bound method while the capability lives on the instance.
    Looking only at the callable would find nothing, and every mutable URL in
    every downstream suite would re-download forever while appearing to work.
    """
    for candidate in (
        fetcher,
        getattr(fetcher, "__self__", None),
        _partial_target(fetcher),
    ):
        capability = getattr(candidate, "conditional_fetch", None)
        if callable(capability):
            return capability
    return None


def _partial_target(fetcher):
    """The callable wrapped by a :func:`functools.partial`, if that is what this is.

    ``partial(assets.chunks, chunk_size=4096)`` is a natural way to install the
    documented fake, and it hides both the attribute and ``__self__``. Losing
    the capability there is silent and costs a full download per read.
    """
    inner = getattr(fetcher, "func", None)
    return None if inner is None else getattr(inner, "__self__", inner)


def _read(url: str, fetcher: UrlFetcher, validators: Validators) -> ConditionalOutcome:
    """Read ``url``, offering ``validators`` for a cheap "unchanged" answer.

    One entry point for both the first read and a revalidation, and that is
    deliberate: routing the *first* fetch through ``conditional_fetch`` too (with
    empty validators, which no origin can match) is what records an ``ETag`` in
    the first place. The plain :data:`UrlFetcher` seam yields bytes and not a
    response, so a transport reached only through it can never earn validators —
    and would then re-download forever, which is option 1 of thorwhalen/falaw#23
    rather than the fix.

    A transport without the capability still works; it simply never gets a cheap
    answer. **So does one whose capability is not the capability**: the lookup is
    duck-typed, so an unrelated ``conditional_fetch``, a wrong signature, or a
    ``MagicMock`` (which auto-creates any attribute, and whose every return value
    is truthy) all reach here. Anything that does not hand back a real
    :class:`ConditionalOutcome` is therefore treated as *no capability* and falls
    through to a plain fetch — never as a "not modified" to be believed.
    """
    conditional = _conditional_capability(fetcher)
    if conditional is not None:
        try:
            outcome = conditional(url, validators)
        except FalAssetFetchError:
            raise
        except TypeError:
            outcome = None  # not the capability we meant; fall through
        except Exception as e:  # noqa: BLE001 — normalized to falaw's typed error
            raise FalAssetFetchError(
                _FETCH_FAILED.format(url=repr(url), error=e), url=url, cause=e
            ) from e
        if isinstance(outcome, ConditionalOutcome):
            return outcome
    return ConditionalOutcome(
        not_modified=False,
        chunks=fetcher(url),
        validators=_validators_for(url, fetcher),
    )


def remembered_ref(url: str) -> Optional[ContentRef]:
    """The :class:`ContentRef` previously recorded for ``url``, if any.

    A *hint*, not a guarantee: it says "the last time falaw fetched this URL,
    the bytes hashed to this" and says nothing about whether those bytes are
    still in any store. Callers must verify (``store.has_blob(...)``, or an
    already-materialized file on disk) before trusting it.

    Public because it is the cheap pre-check that lets a caller answer "do I
    already have this?" without a network round-trip — see
    :func:`falaw.cache.materialize_asset`.

    **It says nothing about whether the URL still serves those bytes.** For a
    mutable URL that question needs :func:`content_ref_for_url`, which
    revalidates; this is the raw recorded value, and trusting it for a
    non-:func:`is_immutable_url` URL is thorwhalen/falaw#23.
    """
    record = _remembered_record(url)
    return None if record is None else record.ref


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
    """Yield the bytes of ``url`` in ``chunk_size`` chunks. The built-in fetcher.

    Private on purpose: it is an *implementation* of :data:`UrlFetcher`, and
    replacing it is done through :func:`using_url_fetcher`, never by rebinding
    this name.
    """
    with urllib.request.urlopen(url) as resp:  # noqa: S310 (fal https URLs)
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                return
            yield chunk


def _file_path_of(url: str) -> Optional[str]:
    """The local path behind a ``file://`` URL, or ``None`` if it is not one."""
    split = urllib.parse.urlsplit(url)
    if split.scheme != "file":
        return None
    return urllib.request.url2pathname(split.path)


def _file_validators(path: str) -> Validators:
    """A synthetic validator for a local file: ``(mtime_ns, ctime_ns, size)``.

    ``file://`` has no ETag, and locally-rendered media is exactly the mutable
    case — re-rendering a clip to the same path leaves the URL identical and the
    bytes different. These three are what a filesystem answers *without reading
    the file*, which is the whole point of a validator.

    **This is a heuristic and it can collide**, which the fallback below cannot:
    a same-length rewrite that also preserves the timestamps reads as unchanged.
    ``ctime_ns`` is included precisely because it narrows that a lot — it is the
    inode's own change time, which the kernel updates on any metadata write and
    which ``cp -p`` / ``rsync -t`` / ``git checkout`` / ``tar -x`` / ``os.utime``
    cannot forge, so the classic "restored a file and kept its mtime" case is
    caught. What remains uncovered is a same-length in-place rewrite on a
    filesystem with coarse timestamp granularity (HFS+ 1 s, FAT 2 s, some
    network mounts) inside one tick.

    If that matters for your data, pass ``refresh=True``, or do not address
    mutable local media by path.
    """
    try:
        st = os.stat(path)
    except OSError:
        return Validators()
    return Validators(etag=f"file:{st.st_mtime_ns}:{st.st_ctime_ns}:{st.st_size}")


def _http_conditional_fetch(
    url: str, validators: Validators, *, chunk_size: int = DFLT_CHUNK_SIZE
) -> ConditionalOutcome:
    """Conditional read for the built-in transport. See :data:`UrlFetcher`.

    Attached to :func:`_http_chunks` as its ``conditional_fetch`` attribute, so
    the built-in transport advertises the capability through the same duck-typed
    seam a custom transport uses — rather than :func:`_revalidate` special-casing
    it by identity.
    """
    local = _file_path_of(url)
    if local is not None:
        current = _file_validators(local)
        if current and current == validators:
            return ConditionalOutcome(not_modified=True)
        return ConditionalOutcome(
            not_modified=False,
            chunks=_http_chunks(url, chunk_size=chunk_size),
            validators=current,
        )

    request = urllib.request.Request(url)
    if validators.etag:
        request.add_header("If-None-Match", validators.etag)
    if validators.last_modified:
        request.add_header("If-Modified-Since", validators.last_modified)
    try:
        response = urllib.request.urlopen(request)  # noqa: S310 (https URLs)
    except urllib.error.HTTPError as e:
        # `HTTPError` *is* the response object, socket and all. Closing it is
        # not tidiness: a 304 is the cheap path this whole feature exists for,
        # so leaking a connection on every hit would make the optimisation cost
        # more than the download it avoids.
        try:
            if e.code == 304:
                return ConditionalOutcome(not_modified=True)
            raise
        finally:
            e.close()
    return ConditionalOutcome(
        not_modified=False,
        chunks=_drain(response, chunk_size),
        validators=_validators_of(response),
    )


_http_chunks.conditional_fetch = _http_conditional_fetch
"""Advertise the built-in transport's revalidation capability on the fetcher itself.

:func:`_revalidate` looks for a ``conditional_fetch`` attribute and asks no
questions about what the fetcher *is*. Attaching it here rather than
special-casing the built-in by identity means the built-in and a custom
transport reach revalidation through exactly one code path — and a transport
that does not set the attribute is simply never asked, which is the documented
"cannot revalidate, therefore re-fetch" case rather than a separate branch.
"""


def _drain(response, chunk_size: int) -> Iterator[bytes]:
    """Yield ``response``'s body in chunks, closing it when done."""
    with response:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                return
            yield chunk


def _validators_of(response) -> Validators:
    """The cache validators an HTTP response offered, if any."""
    headers = getattr(response, "headers", None)
    if headers is None:
        return Validators()
    return Validators(
        etag=headers.get("ETag") or "",
        last_modified=headers.get("Last-Modified") or "",
    )


def _validators_for(url: str, fetcher: UrlFetcher) -> Validators:
    """Validators to record alongside a freshly-stored ``url``.

    Only ``file://`` can produce them without a second request; an HTTP
    transport's response headers are not visible through the plain
    :data:`UrlFetcher` seam (it yields bytes, not a response), so an HTTP URL
    records none on first fetch and earns them on its first *revalidation*,
    which does see the response. Recording nothing is the safe state: no
    validators means :func:`_revalidate` returns ``None`` and the next read
    re-fetches.
    """
    local = _file_path_of(url)
    return _file_validators(local) if local is not None else Validators()


def _store_chunks(url: str, chunks: Iterable[bytes], store) -> ContentRef:
    """Stream ``chunks`` into ``store``; return the ContentRef.

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
        for chunk in chunks:
            counter[0] += len(chunk)
            yield chunk

    try:
        content_hash = store.put_blob_stream(counted())
    except Exception as e:  # noqa: BLE001 — re-raised as a typed falaw error
        raise FalAssetFetchError(
            _FETCH_FAILED.format(url=repr(url), error=e), url=url, cause=e
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


@dataclass(frozen=True, slots=True)
class _IndexRecord:
    """One ``url_index`` entry: the remembered hash plus how to recheck it."""

    ref: ContentRef
    validators: Validators


def _remembered_record(url: str) -> Optional[_IndexRecord]:
    """The full index entry for ``url`` — hash *and* validators.

    Records written before thorwhalen/falaw#23 have no validator fields and
    read back with empty :class:`Validators`. That needs no migration and is
    not a compatibility shim: an entry with no validators is exactly an entry
    falaw cannot revalidate, which already means "re-fetch". The old records
    degrade into the correct behaviour rather than a special case.
    """
    path = _url_index_path(url)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            record = json.load(f)
        return _IndexRecord(
            ref=ContentRef(
                content_hash=record["content_hash"],
                bytes_size=int(record["bytes_size"]),
            ),
            validators=Validators(
                etag=record.get("etag") or "",
                last_modified=record.get("last_modified") or "",
            ),
        )
    except Exception:  # noqa: BLE001 — a corrupt hint is a miss, never a failure
        return None


def _remember_ref(
    url: str, ref: ContentRef, validators: Validators = Validators()
) -> None:
    path = _url_index_path(url)
    tmp = f"{path}.{uuid.uuid4().hex[:8]}.part"
    with open(tmp, "w") as f:
        json.dump(
            {
                "url": url,
                "content_hash": ref.content_hash,
                "bytes_size": ref.bytes_size,
                "etag": validators.etag,
                "last_modified": validators.last_modified,
            },
            f,
        )
    os.replace(tmp, path)
