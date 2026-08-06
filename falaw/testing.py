"""Make a suite that uses falaw genuinely offline — the fake asset transport.

falaw content-addresses every media result (:mod:`falaw.content`): a fal URL is
neither unique-per-content nor durable, so it cannot be an identity, and
:func:`falaw.execute_plan` therefore **reads the bytes** behind every result. A
downstream suite that stubs the fal *response* but not the *asset transport* is
consequently resolving its made-up URLs for real — one DNS lookup and one
connection attempt per test.

Such a suite passes anyway. That is the trap. falaw deliberately degrades a
failed asset fetch to a URL-only artifact with a :class:`UserWarning` rather
than raising, so an upstream hiccup cannot throw away a render fal has already
billed for — which means reaching the network is *invisible* downstream. The
costs are real all the same: the suite is slower and behaves differently
without a network; it exercises the *degraded* path rather than the content
addressing it appears to exercise; and a stub URL whose host happens to answer
**200** pulls arbitrary internet content into the cache with the test still
green.

This module is falaw's answer, so no consumer has to write one. Three autouse
fixtures, each re-exportable into a ``conftest.py`` in one line:

>>> from falaw.testing import (  # doctest: +SKIP
...     fake_assets,
...     isolated_falaw_cache,
...     no_outbound_network,
... )  # noqa: F401

:func:`fake_assets`
    Serves falaw's asset fetches from memory. An unregistered URL yields
    deterministic synthetic bytes derived from the URL, so two different stub
    URLs behave like two genuinely different renders;
    :meth:`FakeAssets.serve` pins explicit bytes — which is how a test makes
    two *different* URLs serve the *same* bytes, the case content addressing
    exists for; :meth:`FakeAssets.fail` makes a URL 404, as an expired fal
    asset does, which is how a test exercises the degrade path on purpose.

:func:`isolated_falaw_cache`
    Points falaw's manifest cache, content store and url-index at a throwaway
    directory. A precondition for the fake, not a nicety: once the fetches
    *succeed*, an un-isolated run durably records synthetic test bytes under
    real-looking URLs in the developer's own ``~/.config/falaw/cache``.

:func:`no_outbound_network`
    The backstop. The other two close the holes we know about; this one
    notices the next one. Every non-loopback DNS lookup or socket connect is
    refused **and recorded**, and the recording fails the test at teardown.

**Refusing is not reporting**, and that distinction is the whole design of the
guard. A guard that only raises is invisible here, because falaw's fetch path
is a funnel of broad ``except Exception`` handlers that exist for good reasons:
``_fetch_into_store`` turns any ``Exception`` into a ``FalAssetFetchError``,
which ``execute`` then **degrades** to a URL-only artifact with a warning
(rather than discard a render fal has already billed); ``remembered_ref``
treats any ``Exception`` as a cache miss; ``make_call_plan``'s cache probe
falls back to ``"unknown"``. An ordinary-``Exception`` refusal is absorbed by
all three, and the suite stays green with the regression back in place.

Hence two measures, not one. :class:`OutboundNetworkAttempt` derives from
:class:`BaseException` so it escapes those funnels (``execute_isolated``
deliberately re-raises a non-``Exception``, since a run-level abort is not a
call failure) — and every attempt is **recorded** anyway, because that only
covers the funnels *inside falaw*. A consumer's own ``except BaseException``
re-absorbs it, and a subprocess is out of reach entirely. The record is the
part that cannot be swallowed.

Why not ``FALAW_FETCH_ARTIFACT_BYTES=0``
----------------------------------------
It silences the network too — by turning content addressing **off**. The suite
becomes hermetic and simultaneously stops testing the feature: every
``asset_id`` becomes a response digest rather than a content hash, and no test
covers the path production takes. Faking the transport keeps content addressing
under test with bytes the test controls. See
:data:`falaw.plan.FETCH_BYTES_ENVVAR`.

Opting a test back into the real world
--------------------------------------
A test carrying any marker in :data:`DFLT_LIVE_MARKERS` (``live_api``) gets the
real transport and no network guard, and keeps the cache isolation. Suites with
another such marker build their own fixtures from the factories:

>>> gated = make_fake_assets_fixture(live_markers=("live_api", "live_capture"))

The classes and context managers here need no pytest; only the fixtures do.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.parse
from contextlib import contextmanager
from typing import Iterator, Optional, Sequence

from .content import DFLT_CHUNK_SIZE, using_url_fetcher


__all__ = [
    "DFLT_LIVE_MARKERS",
    "DFLT_SYNTHETIC_PREFIX",
    "FakeAssets",
    "LOCAL_HOSTNAMES",
    "NON_NETWORK_SCHEMES",
    "OutboundNetworkAttempt",
    "blocked_outbound_network",
    "fake_assets",
    "is_network_url",
    "isolated_falaw_cache",
    "make_fake_assets_fixture",
    "make_isolated_falaw_cache_fixture",
    "make_no_outbound_network_fixture",
    "no_outbound_network",
    "serving_fake_assets",
    "synthetic_asset_bytes",
]


DFLT_LIVE_MARKERS = ("live_api",)
"""Pytest markers meaning "this test is allowed to reach the real world".

falaw's own convention. A suite using another name (``live_capture``, say)
passes its own tuple to the fixture factories rather than editing this.
"""

DFLT_SYNTHETIC_PREFIX = "falaw-test-asset"
"""Prefix of the stand-in bytes an unpinned URL serves.

Only ever seen while debugging — which is exactly why it is worth setting per
suite (``FakeAssets(synthetic_prefix="nw-test-asset")``): a hexdump in a
failing assertion then names the suite that invented the bytes.
"""

LOCAL_HOSTNAMES = frozenset(
    {"", "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
)
"""Hostnames that mean "this machine" without a DNS round-trip."""

NON_NETWORK_SCHEMES = frozenset({"", "file"})
"""URL schemes that do not leave this machine, and so are not faked.

``file://`` is a documented falaw input — downstream packages hand it locally
rendered media that way — so faking it would replace a real mp4 with synthetic
bytes and break the ffmpeg that reads it. Such URLs fall through to the real
fetcher unless a test pins them explicitly.
"""


def synthetic_asset_bytes(url: str, *, prefix: str = DFLT_SYNTHETIC_PREFIX) -> bytes:
    """Deterministic stand-in bytes for a URL nothing has pinned.

    Derived from the URL, so two different stub URLs behave like two genuinely
    different renders — and the same stub URL hashes the same way on every run,
    which is what lets a test assert on a content hash at all.

    >>> synthetic_asset_bytes("https://fal.media/x.png")
    b'falaw-test-asset::https://fal.media/x.png'
    >>> a = synthetic_asset_bytes("https://fal.media/one.png")
    >>> b = synthetic_asset_bytes("https://fal.media/two.png")
    >>> a == b
    False
    """
    return f"{prefix}::{url}".encode("utf-8")


def is_network_url(url: str) -> bool:
    """True when resolving ``url`` would leave this machine.

    >>> is_network_url("https://fal.media/x.png")
    True
    >>> is_network_url("file:///tmp/rendered.mp4"), is_network_url("/tmp/x.mp4")
    (False, False)
    """
    return urllib.parse.urlparse(url).scheme not in NON_NETWORK_SCHEMES


class FakeAssets:
    """An in-memory ``url -> bytes`` transport standing in for the network.

    Install it with :func:`falaw.content.using_url_fetcher` (the
    :func:`fake_assets` fixture does), after which every falaw entry point that
    reads asset bytes is served from here.

    Three behaviours, each of which a downstream suite discovered it needed:

    - an **unpinned** network URL yields :func:`synthetic_asset_bytes`;
    - :meth:`serve` **pins** explicit bytes, which is how a test makes two
      *different* URLs serve the *same* bytes — the case content addressing
      exists for — or aligns falaw's view of an asset with bytes the test also
      wrote to disk itself;
    - :meth:`fail` makes a URL **404**, as an expired fal asset does, which is
      how a test exercises falaw's degrade-to-URL-only path on purpose.

    Every fetch is **recorded** in :attr:`fetched`, and that is not a
    convenience. falaw degrades a failed fetch to a URL-only artifact with a
    warning rather than raising, so a fake that only *refused* an unexpected
    URL would be swallowed and the test would pass. Assert on what was fetched,
    not on an exception:

    >>> from lacing import ArtifactStore
    >>> from falaw import content_ref_for_url
    >>> from falaw.content import using_url_fetcher
    >>> store, assets = ArtifactStore.in_memory(), FakeAssets()
    >>> shared = assets.serve("https://fal.media/one.png", b"identical bytes")
    >>> _ = assets.serve("https://fal.media/two.png", shared)
    >>> with using_url_fetcher(assets.chunks):
    ...     one = content_ref_for_url("https://fal.media/one.png", store=store)
    ...     two = content_ref_for_url("https://fal.media/two.png", store=store)
    >>> one.content_hash == two.content_hash  # two URLs, one content address
    True
    >>> assets.fetched
    ['https://fal.media/one.png', 'https://fal.media/two.png']
    """

    def __init__(
        self,
        *,
        synthetic_prefix: str = DFLT_SYNTHETIC_PREFIX,
        fake_non_network_urls: bool = False,
    ) -> None:
        """Build an empty transport.

        Args:
            synthetic_prefix: prefix of the bytes an unpinned URL serves.
            fake_non_network_urls: whether ``file://`` URLs and bare paths are
                faked too. False by default — they are not the network, and a
                test that wrote a real file expects to read it back. Pinning
                such a URL with :meth:`serve` overrides this either way.
        """
        self.by_url: dict[str, Optional[bytes]] = {}
        self.fetched: list[str] = []
        self.synthetic_prefix = synthetic_prefix
        self.fake_non_network_urls = fake_non_network_urls

    def synthetic(self, url: str) -> bytes:
        """The bytes an unpinned ``url`` serves."""
        return synthetic_asset_bytes(url, prefix=self.synthetic_prefix)

    def serve(self, url: str, data: bytes) -> bytes:
        """Make ``url`` serve exactly ``data``. Returns ``data``, for chaining."""
        self.by_url[url] = data
        return data

    def fail(self, url: str) -> None:
        """Make ``url`` 404, the way an expired fal asset does."""
        self.by_url[url] = None

    def handles(self, url: str) -> bool:
        """Whether this transport answers for ``url`` rather than deferring.

        A pinned URL always. An unpinned one only when it is a network URL (or
        :attr:`fake_non_network_urls` is set) — see :data:`NON_NETWORK_SCHEMES`.
        """
        if url in self.by_url:
            return True
        return self.fake_non_network_urls or is_network_url(url)

    def chunks(self, url: str, *, chunk_size: int = DFLT_CHUNK_SIZE) -> Iterator[bytes]:
        """Yield ``url``'s bytes — the :data:`falaw.content.UrlFetcher` to install.

        Raises:
            urllib.error.HTTPError: ``url`` was marked with :meth:`fail`.
        """
        self.fetched.append(url)
        if not self.handles(url):
            from .content import _http_chunks

            yield from _http_chunks(url, chunk_size=chunk_size)
            return
        data = self.by_url.get(url)
        if url not in self.by_url:
            data = self.synthetic(url)
        if data is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]
        for offset in range(0, len(data), chunk_size):
            yield data[offset : offset + chunk_size]


@contextmanager
def serving_fake_assets(assets: Optional[FakeAssets] = None) -> Iterator[FakeAssets]:
    """Install a :class:`FakeAssets` as falaw's transport for the duration.

    The pytest-free core of :func:`fake_assets`, for a caller driving falaw
    outside a pytest session (a script, a notebook, another test runner).

    >>> from falaw import materialize_asset
    >>> with serving_fake_assets() as assets:
    ...     _ = assets.serve("https://fal.media/x.png", b"pinned")
    ...     path = materialize_asset("https://fal.media/x.png")
    >>> with open(path, "rb") as f:
    ...     f.read()
    b'pinned'
    """
    assets = FakeAssets() if assets is None else assets
    with using_url_fetcher(assets.chunks):
        yield assets


# --- the no-outbound-connection backstop ------------------------------------


class OutboundNetworkAttempt(BaseException):
    """An offline test tried to talk to a non-local host.

    Derived from :class:`BaseException`, not :class:`Exception`, on purpose:
    the fetch path is a funnel of ``except Exception`` handlers that turn a
    failed fetch into a degraded-but-successful result (falaw's URL-only
    artifact fallback is the main one), so anything catchable would be caught.

    That still is not enough on its own. It escapes *falaw's* funnels, not a
    consumer's own ``except BaseException`` — and not a subprocess, which opens
    its own sockets where nothing here has reach. Which is why every attempt is
    also **recorded**; see :func:`blocked_outbound_network`.
    """


def _is_local_address(address) -> bool:
    """True when ``address`` is loopback, unspecified, or not an IP endpoint.

    Non-tuple addresses (``AF_UNIX`` paths, ``AF_NETLINK`` ints) are local by
    construction — which keeps a local Postgres or a unix-socket service
    reachable from an otherwise offline suite. A bare hostname that is not a
    known loopback alias counts as outbound: resolving it is itself a network
    round-trip.
    """
    import ipaddress

    if not isinstance(address, (tuple, list)) or not address:
        return True
    host = address[0]
    if host is None:
        return True
    host = str(host)
    if host in LOCAL_HOSTNAMES:
        return True
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def _is_local_hostname(host) -> bool:
    """True for a hostname that resolves without leaving this machine."""
    if host is None:
        return True
    text = host.decode("utf-8", "replace") if isinstance(host, bytes) else str(host)
    text = text.strip("[]")
    if text in LOCAL_HOSTNAMES or text.endswith(".localhost"):
        return True
    return _is_local_address((text,))


@contextmanager
def blocked_outbound_network() -> Iterator[list]:
    """Refuse **and record** every non-local socket use; yield the record.

    The yielded list is the point. Raising alone is not a guard here: falaw
    swallows a failed fetch by design, and a refusal that reaches a consumer's
    own broad ``except`` — or happens in a subprocess — vanishes without trace.
    A caller asserts on the list afterwards; :func:`no_outbound_network` fails
    the test at teardown when it is non-empty.

    A test that *means* to provoke an attempt drains the list
    (``attempts.clear()``) instead of failing.

    Blind spot worth knowing: a subprocess opens its own sockets in its own
    process, where this has no reach. ffmpeg is the one that matters.

    >>> import socket
    >>> with blocked_outbound_network() as attempts:
    ...     try:
    ...         socket.getaddrinfo("example.com", 443)
    ...     except OutboundNetworkAttempt:
    ...         pass
    >>> attempts
    ["a DNS lookup for 'example.com'"]
    """
    attempts: list = []
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def refuse(what: str) -> OutboundNetworkAttempt:
        attempts.append(what)
        return OutboundNetworkAttempt(
            f"An offline test attempted {what}. Stub the transport instead — "
            "`falaw.testing.fake_assets` serves falaw's asset fetches, and a "
            "test needing its own HTTP should fake the call it makes."
        )

    def guarded_getaddrinfo(host, port, *args, **kwargs):
        if not _is_local_hostname(host):
            raise refuse(f"a DNS lookup for {host!r}")
        return real_getaddrinfo(host, port, *args, **kwargs)

    def guarded_connect(self, address, *args, **kwargs):
        if not _is_local_address(address):
            raise refuse(f"a connection to {address!r}")
        return real_connect(self, address, *args, **kwargs)

    def guarded_connect_ex(self, address, *args, **kwargs):
        if not _is_local_address(address):
            raise refuse(f"a connection to {address!r}")
        return real_connect_ex(self, address, *args, **kwargs)

    socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]
    socket.socket.connect = guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = guarded_connect_ex  # type: ignore[method-assign]
    try:
        yield attempts
    finally:
        socket.getaddrinfo = real_getaddrinfo  # type: ignore[assignment]
        socket.socket.connect = real_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = real_connect_ex  # type: ignore[method-assign]


# --- the pytest fixtures ----------------------------------------------------


def _fixture(**kwargs):
    """:func:`pytest.fixture` when pytest is importable, else a no-op decorator.

    Everything above is pytest-free, and this module is imported by the docs
    build — which installs falaw without its test extra — merely to read
    docstrings. A hard ``import pytest`` at module scope would break that. The
    fixtures are unusable without a pytest session anyway, so degrading them to
    plain functions loses nothing.
    """
    try:
        import pytest
    except ModuleNotFoundError:  # pragma: no cover - docs build only
        return lambda func: func
    return pytest.fixture(**kwargs)


def _is_live(request, live_markers: Sequence[str]) -> bool:
    """True when the test under ``request`` is allowed real external I/O."""
    return any(request.node.get_closest_marker(m) is not None for m in live_markers)


def make_fake_assets_fixture(
    *,
    live_markers: Sequence[str] = DFLT_LIVE_MARKERS,
    synthetic_prefix: str = DFLT_SYNTHETIC_PREFIX,
    fake_non_network_urls: bool = False,
    autouse: bool = True,
):
    """Build a ``fake_assets`` fixture with non-default settings.

    :func:`fake_assets` is ``make_fake_assets_fixture()``. Use this when the
    suite's live-marker names differ, or to label the synthetic bytes with the
    suite's own name:

    >>> fake_assets = make_fake_assets_fixture(  # doctest: +SKIP
    ...     live_markers=("live_api", "live_capture"),
    ...     synthetic_prefix="reelee-test-asset",
    ... )
    """

    def fake_assets(request) -> Iterator[Optional[FakeAssets]]:
        """Serve falaw's media fetches from memory instead of the network.

        Installed via :func:`falaw.content.using_url_fetcher`, so it covers
        ``execute_plan``, ``execute_plan_isolated``, ``materialize_asset`` and
        ``content_ref_for_url`` at once — including the ones a consumer reaches
        through its own public API, which takes no transport argument and should
        not grow one just for tests. An explicitly passed ``fetcher=`` wins over
        it, as it should.
        """
        if _is_live(request, live_markers):
            yield None
            return
        assets = FakeAssets(
            synthetic_prefix=synthetic_prefix,
            fake_non_network_urls=fake_non_network_urls,
        )
        with serving_fake_assets(assets):
            yield assets

    return _fixture(autouse=autouse)(fake_assets)


def make_isolated_falaw_cache_fixture(*, autouse: bool = True):
    """Build an ``isolated_falaw_cache`` fixture. See :func:`isolated_falaw_cache`."""

    def isolated_falaw_cache(tmp_path, monkeypatch) -> Iterator[str]:
        """Point every falaw on-disk store at a throwaway directory."""
        root = tmp_path / "falaw"
        monkeypatch.setenv("FALAW_DATA_DIR", str(root / "data"))
        monkeypatch.setenv("FALAW_CACHE_DIR", str(root / "cache"))
        yield str(root)

    return _fixture(autouse=autouse)(isolated_falaw_cache)


def make_no_outbound_network_fixture(
    *,
    live_markers: Sequence[str] = DFLT_LIVE_MARKERS,
    autouse: bool = True,
):
    """Build a ``no_outbound_network`` fixture. See :func:`no_outbound_network`."""

    def no_outbound_network(request) -> Iterator[list]:
        """Refuse and report every non-loopback connection attempt."""
        if _is_live(request, live_markers):
            yield []
            return
        with blocked_outbound_network() as attempts:
            yield attempts
        if attempts:
            import pytest

            # Teardown, not the call site, on purpose: falaw degrades a failed
            # fetch to a warning and ``execute_isolated`` catches
            # ``BaseException``, so a guard that only raised would let the
            # regression back in with the suite still green.
            pytest.fail(
                "Outbound network access attempted by an offline test: "
                + "; ".join(dict.fromkeys(attempts)),
                pytrace=False,
            )

    return _fixture(autouse=autouse)(no_outbound_network)


fake_assets = make_fake_assets_fixture()
"""Autouse fixture serving falaw's asset fetches from memory.

Re-export it into a ``conftest.py`` and the whole suite is covered::

    from falaw.testing import fake_assets  # noqa: F401

Yields the :class:`FakeAssets` in force, so a test can pin bytes
(``fake_assets.serve(url, data)``), 404 a URL (``fake_assets.fail(url)``) or
assert on what was fetched (``fake_assets.fetched``). Yields ``None`` for a
test marked ``live_api``, which gets the real transport.
"""

isolated_falaw_cache = make_isolated_falaw_cache_fixture()
"""Autouse fixture pointing falaw's on-disk state at a throwaway directory.

falaw's manifest cache, content store and url-index all hang off
``$FALAW_CACHE_DIR`` / ``$FALAW_DATA_DIR``. Without this a run writes into the
developer's real cache and inherits the previous run's ``url -> content hash``
index — and once :func:`fake_assets` makes the fetches *succeed*, it durably
records synthetic test bytes under real-looking URLs there. Yields the root of
the throwaway directory.
"""

no_outbound_network = make_no_outbound_network_fixture()
"""Autouse fixture failing any test that reaches a non-loopback address.

The backstop behind :func:`fake_assets`: that one closes the holes we know
about, this one notices the next. Yields the list of recorded attempts, so a
test that means to provoke one can drain it (``no_outbound_network.clear()``)
instead of failing at teardown. Inert for a test marked ``live_api``.
"""
