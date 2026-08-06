"""Plan / Execute primitives — separate planning (data) from execution (effects).

Today every falaw operation is eager: ``generate_image(prompt)`` makes the
API call immediately. That means:

- A budget gate has to predict cost from outside the call and *hope* the
  prediction matches what the operation will actually do.
- Tests need a fake fal_client to exercise any code that touches an
  operation, even when the test is about composition or cost.
- A UI can't show "you're about to spend $4.12, click confirm" without
  a separate, parallel cost-prediction code path.

The fix is to give every operation two surfaces:

1. ``plan_X(...) -> CallPlan``: pure data describing the call that *would*
   happen — model_id, arguments, predicted cost, cache status. No API contact.
2. ``execute(plan, ...) -> list[Artifact]``: turns a Plan (one or more
   CallPlans) into materialized Artifacts. The eager wrappers
   (``generate_image``, etc.) are now thin: ``execute(plan_X(...))[0]``.

A higher-level orchestrator (a music-video render, a storyboard generation)
builds a Plan by composing CallPlans across multiple operations. The Plan
gets a typed ``total_cost_usd``, can be inspected, edited, dry-run, or
serialized — all without the network.

Examples
--------

>>> from falaw.plan import CallPlan, Plan
>>> p1 = CallPlan(
...     tool="generate_image",
...     application="fal-ai/flux/dev",
...     arguments={"prompt": "a tiger", "image_size": "landscape_4_3"},
...     output_kind="image",
...     estimated_cost_usd=0.025,
...     cache_status="miss",
... )
>>> p2 = CallPlan(
...     tool="image_to_video",
...     application="fal-ai/minimax/hailuo-02/pro/image-to-video",
...     arguments={"image_url": "<from p1>"},
...     output_kind="video",
...     estimated_cost_usd=0.50,
...     cache_status="miss",
... )
>>> plan = Plan(calls=(p1, p2))
>>> plan.total_cost_usd
0.525
>>> plan.cache_hit_savings_usd
0.0
>>> [c.tool for c in plan.calls]
['generate_image', 'image_to_video']

Plans concatenate, so an orchestrator can build one shot's Plan and then
append it to a scene-level Plan:

>>> shot_plan = Plan(calls=(p1,))
>>> scene_plan = Plan(calls=()) + shot_plan + Plan(calls=(p2,))
>>> len(scene_plan.calls)
2
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Literal, Optional


CacheStatus = Literal["hit", "miss", "stale", "unknown"]
"""Whether the cache will short-circuit this call.

- ``hit``: A cached response exists and will be returned without an API call.
- ``miss``: No cache entry; the call will hit fal.
- ``stale``: An entry exists but is expected to be invalidated (e.g. a
  ``force=True`` re-render asked for it). Today we don't distinguish stale
  from miss for cost — both are billed.
- ``unknown``: Plan was built without consulting the cache.
"""


OutputKind = Literal["image", "video", "audio", "json", "text", "binary"]
"""Coarse class of what this call produces. Mirrors :class:`lacing.Artifact.kind`
so the producer knows what shape of Artifact to materialize."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CallPlan:
    """A single planned fal call. Pure data — no API contact yet.

    ``application`` and ``arguments`` are the *exact* tuple
    ``cached_call_fal(application, arguments)`` would take, so a Plan can be
    cache-checked, executed, or replayed without ambiguity.
    """

    tool: str
    """High-level tool name — ``"generate_image"``, ``"image_to_video"``, etc.
    Distinct from ``application`` because one tool may dispatch to several
    fal models depending on quality tier."""

    application: str
    """The fal model id that will be invoked (e.g. ``"fal-ai/flux/dev"``)."""

    arguments: dict
    """Keyword arguments to pass to fal. Will be JSON-canonicalized for
    cache key computation; should be JSON-serializable."""

    output_kind: OutputKind
    """What kind of Artifact this call will produce."""

    estimated_cost_usd: Optional[float] = None
    """Predicted cost in USD. ``None`` when the model has no ``cost_estimate``
    populated (callers can distinguish "free" from "unknown")."""

    cache_status: CacheStatus = "unknown"
    """Whether the cache will short-circuit this call. ``"hit"`` means
    ``execute`` won't bill, so :attr:`Plan.total_cost_usd` and
    :attr:`Plan.cache_hit_savings_usd` reflect that."""

    expected_duration_s: Optional[tuple[float, float]] = None
    """``(min, max)`` duration the model can produce, or ``None`` if no
    duration contract is known. Plan-level validators can check that the
    requested duration fits this range and raise :class:`FalDurationOutOfRange`
    *before* the call instead of letting it silently truncate."""

    metadata: dict = field(default_factory=dict)
    """Free-form labels for downstream consumers. Conventional keys:
    ``shot_id``, ``beat_id``, ``character_name``, ``strategy``."""

    # -- predicted-billable cost --------------------------------------------

    @property
    def billable_cost_usd(self) -> float:
        """Cost that will actually be billed (0 on cache hit, estimate otherwise).

        Returns ``0.0`` (not ``None``) on cache hit or unknown estimate so
        sums are well-defined; use :attr:`estimated_cost_usd` ``is None`` to
        check unknown status explicitly.
        """
        if self.cache_status == "hit":
            return 0.0
        return self.estimated_cost_usd or 0.0


@dataclass(frozen=True, slots=True)
class Plan:
    """An ordered sequence of :class:`CallPlan` — a render plan, in essence.

    Plans compose: ``a + b`` returns a new Plan with ``a.calls`` followed by
    ``b.calls``. ``Plan(calls=())`` is the identity. Plans are frozen, so
    edits return new Plans (use :meth:`with_call_replaced` for in-place-feel).
    """

    calls: tuple[CallPlan, ...] = ()

    def __add__(self, other: "Plan") -> "Plan":
        if not isinstance(other, Plan):
            return NotImplemented
        return Plan(calls=self.calls + other.calls)

    def __len__(self) -> int:
        return len(self.calls)

    def __iter__(self):
        return iter(self.calls)

    def __getitem__(self, idx):
        return self.calls[idx]

    @property
    def total_cost_usd(self) -> float:
        """Sum of :attr:`CallPlan.billable_cost_usd` across all calls."""
        return sum((c.billable_cost_usd for c in self.calls), 0.0)

    @property
    def cache_hit_savings_usd(self) -> float:
        """USD that would have been spent without the cache.

        Equal to ``sum(c.estimated_cost_usd for c in calls if c.cache_status == "hit"
        and c.estimated_cost_usd is not None)``.
        """
        return sum(
            (
                c.estimated_cost_usd or 0.0
                for c in self.calls
                if c.cache_status == "hit"
            ),
            0.0,
        )

    @property
    def has_unknown_costs(self) -> bool:
        """True if any non-cache-hit call has no cost estimate.

        Use this to refuse to gate on a budget when the estimate is incomplete.
        """
        return any(
            c.estimated_cost_usd is None and c.cache_status != "hit" for c in self.calls
        )

    def with_call_replaced(self, index: int, new_call: CallPlan) -> "Plan":
        """Return a new Plan with ``calls[index]`` replaced."""
        new_calls = list(self.calls)
        new_calls[index] = new_call
        return Plan(calls=tuple(new_calls))


# --- serialization ----------------------------------------------------------

PLAN_DICT_SCHEMA = "falaw.plan/v1"
"""The ``schema`` tag :func:`plan_to_dict` writes and :func:`plan_from_dict`
expects. Bumped only on a breaking change to the dict shape."""


def call_plan_to_dict(call: CallPlan) -> dict:
    """Convert a :class:`CallPlan` to a plain JSON-serializable dict.

    The inverse of :func:`call_plan_from_dict`. ``expected_duration_s`` (a
    ``tuple``) becomes a 2-element list since JSON has no tuple type;
    everything else is already JSON-native.
    """
    return {
        "tool": call.tool,
        "application": call.application,
        "arguments": call.arguments,
        "output_kind": call.output_kind,
        "estimated_cost_usd": call.estimated_cost_usd,
        "cache_status": call.cache_status,
        "expected_duration_s": (
            list(call.expected_duration_s)
            if call.expected_duration_s is not None
            else None
        ),
        "metadata": call.metadata,
    }


def call_plan_from_dict(d: dict) -> CallPlan:
    """Rebuild a :class:`CallPlan` from a :func:`call_plan_to_dict` dict.

    ``arguments`` / ``metadata`` are copied (a deserialized plan owns its own
    data); ``expected_duration_s`` is re-tupled.
    """
    duration = d.get("expected_duration_s")
    return CallPlan(
        tool=d["tool"],
        application=d["application"],
        arguments=dict(d["arguments"]),
        output_kind=d["output_kind"],
        estimated_cost_usd=d.get("estimated_cost_usd"),
        cache_status=d.get("cache_status", "unknown"),
        expected_duration_s=(tuple(duration) if duration is not None else None),
        metadata=dict(d.get("metadata") or {}),
    )


def plan_to_dict(plan: Plan) -> dict:
    """Convert a :class:`Plan` to a plain JSON-serializable dict.

    The result round-trips through :func:`plan_from_dict`. This is the
    substrate primitive a consumer (a persistence layer, an MCP transport, a
    plan-diff tool) builds on — falaw owns the wire shape of its own Plan so
    every consumer agrees on it. Carries a ``schema`` tag (:data:`PLAN_DICT_SCHEMA`)
    so a future breaking change is detectable.
    """
    return {
        "schema": PLAN_DICT_SCHEMA,
        "calls": [call_plan_to_dict(c) for c in plan.calls],
    }


def plan_from_dict(d: dict) -> Plan:
    """Rebuild a :class:`Plan` from a :func:`plan_to_dict` dict.

    Raises ``ValueError`` if ``d`` carries an unrecognized ``schema`` tag — a
    plan written by an incompatible future version should fail loudly, not
    silently lose calls. A missing ``schema`` is tolerated (treated as v1) so
    hand-written plans stay easy.
    """
    schema = d.get("schema")
    if schema is not None and schema != PLAN_DICT_SCHEMA:
        raise ValueError(
            f"Cannot deserialize Plan: unknown schema {schema!r} "
            f"(this falaw understands {PLAN_DICT_SCHEMA!r})."
        )
    return Plan(calls=tuple(call_plan_from_dict(c) for c in d.get("calls", ())))


def plan_hash(plan: Plan) -> str:
    """Stable, plan-scoped **structural idempotency key** for a whole :class:`Plan`.

    Answers "does this whole plan match one I already ran?" — the handle a job
    manager (its first customer, :mod:`nw.jobs`) uses to dedup double-submits and
    to replay a resumed render for free. It is computed *before* execution and
    with ``<from N>`` placeholders intact, so it is stable across re-plans of the
    same structural request.

    The digest canonicalizes each call over ``{app, args, tool}`` — matching
    :func:`_synthetic_artifact`'s canonicalization, and deliberately **not** the
    per-call content-addressed cache key (:func:`falaw.cache._key`, which keys on
    ``{app, args}`` with no ``tool``). ``plan_hash`` and the per-call cache key
    therefore key on *different* bytes and must not be assumed to agree
    call-for-call; what is reused from the cache is only the canonicalization
    *discipline* (``sort_keys=True`` / ``default=str``), which is all a
    stable-across-re-plans dedup handle needs.

    Two structurally-identical plans hash equal; changing any call's ``app``,
    ``args``, or ``tool`` — or the *order* of calls — changes the hash.

    >>> a = CallPlan(tool="generate_image", application="fal-ai/flux/dev",
    ...              arguments={"prompt": "a tiger"}, output_kind="image")
    >>> b = CallPlan(tool="image_to_video", application="fal-ai/svd",
    ...              arguments={"image_url": "<from 0>"}, output_kind="video")
    >>> plan_hash(Plan(calls=(a, b))) == plan_hash(Plan(calls=(a, b)))
    True
    >>> plan_hash(Plan(calls=(a, b))) == plan_hash(Plan(calls=(b, a)))
    False
    """
    import hashlib
    import json as _json

    blob = _json.dumps(
        [
            {"app": c.application, "args": c.arguments, "tool": c.tool}
            for c in plan.calls
        ],
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# --- planning helpers -------------------------------------------------------


def make_call_plan(
    *,
    tool: str,
    application: str,
    arguments: dict,
    output_kind: OutputKind,
    estimated_cost_usd: Optional[float] = None,
    expected_duration_s: Optional[tuple[float, float]] = None,
    metadata: Optional[dict] = None,
    consult_cache: bool = True,
) -> CallPlan:
    """Build a :class:`CallPlan` and (optionally) check the cache.

    When ``consult_cache=True`` (the default), the cache is peeked using the
    same key the eventual call would produce; ``cache_status`` is set to
    ``"hit"`` if a cached entry exists, ``"miss"`` otherwise. This makes
    ``Plan.total_cost_usd`` honest: a fully-cached Plan reports $0.

    When ``consult_cache=False`` (e.g. for unit tests or "what would a fresh
    run cost?" reporting), ``cache_status`` is ``"unknown"``.

    Known gap (falaw#15): the peek uses the *unresolved* arguments, so for a
    chained call — one whose arguments still hold a ``<from N>`` placeholder —
    it keys on the placeholder rather than on the upstream content ref
    :func:`execute` will key on. ``cache_status`` is therefore not to be
    trusted for chained calls, and a plan's reported cost can understate what
    the run bills. Fixing it needs the upstream to have executed, which is a
    planner-level change, not a converter-level one.
    """
    status: CacheStatus = "unknown"
    if consult_cache:
        # Local import to avoid a cycle: cache imports from core, core imports
        # from errors, none of which need plan.
        try:
            from .cache import cache_get  # type: ignore[import-not-found]

            status = "hit" if cache_get(application, arguments) is not None else "miss"
        except Exception:
            # Cache lookup is best-effort — if it errors (corrupted manifest,
            # etc.) fall back to ``"unknown"`` rather than fail the planner.
            status = "unknown"
    return CallPlan(
        tool=tool,
        application=application,
        arguments=arguments,
        output_kind=output_kind,
        estimated_cost_usd=estimated_cost_usd,
        cache_status=status,
        expected_duration_s=expected_duration_s,
        metadata=metadata or {},
    )


# --- execution --------------------------------------------------------------


# Type for the per-call result-to-Artifact converter.
ResultToArtifact = Callable[[dict, CallPlan], "Artifact"]  # noqa: F821


DFLT_FETCH_BYTES = True
"""Whether :func:`execute` downloads media results to content-address them.

True — an artifact whose ``asset_id`` is not the SHA-256 of its bytes breaks
``lacing.Artifact``'s contract and puts an expiring location into every
downstream cache key.
"""

FETCH_BYTES_ENVVAR = "FALAW_FETCH_ARTIFACT_BYTES"
"""Env var overriding :data:`DFLT_FETCH_BYTES` process-wide.

Set it to ``0`` for one legitimate case: an **offline test suite** whose
stubbed fal responses carry URLs that resolve to nothing. It is not a
production setting — see the ``fetch_bytes`` argument of :func:`execute` for
what opting out costs. Read at call time, so a test can set it after import.
"""


def _fetch_bytes_default() -> bool:
    """Resolve the effective ``fetch_bytes`` default from the environment."""
    import os

    raw = os.environ.get(FETCH_BYTES_ENVVAR)
    if raw is None:
        return DFLT_FETCH_BYTES
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def execute(
    plan: Plan,
    *,
    on_event: Optional[Callable] = None,
    dry_run: bool = False,
    use_cache: bool = True,
    artifact_converter: Optional[ResultToArtifact] = None,
    content_store=None,
    fetch_bytes: Optional[bool] = None,
    asset_fetcher=None,
) -> list:
    """Execute a Plan, returning a list of materialized :class:`lacing.Artifact`s.

    Args:
        plan: The Plan to execute.
        on_event: Optional per-call event subscriber (passed to ``call_fal``).
        dry_run: When True, no fal calls are made; synthetic Artifacts are
            returned with placeholder ``asset_id`` and ``url=None``. Useful
            for exercising downstream composition without an API key.
        use_cache: When True (default), executes via ``cached_call_fal`` so
            cache hits skip the network. When False, every call is fresh.
        artifact_converter: Per-CallPlan converter from raw fal response to
            :class:`lacing.Artifact`. When ``None`` (default), a built-in
            converter handles the common shapes (``{images: [{url}]}``,
            ``{video: {url}}``, ``{audio: {url}}``). Mutually exclusive with
            ``content_store`` / ``fetch_bytes`` / ``asset_fetcher``, which
            configure the built-in converter only — passing both raises, rather
            than silently ignoring the ones a custom converter cannot honour.
        content_store: Injected :class:`lacing.ArtifactStore` that media bytes
            are materialized into. Defaults to
            :func:`falaw.content.default_content_store` (a directory store
            rooted in the falaw cache). Point this at an S3-backed store to
            share content — and therefore cache hits — across machines.
        fetch_bytes: Whether to download each media result so its ``asset_id``
            is the SHA-256 of its bytes. Defaults to :data:`DFLT_FETCH_BYTES`
            (true), overridable process-wide via :data:`FETCH_BYTES_ENVVAR`.
            **Opting out forfeits caching for chained calls**: without bytes
            there is no content hash, so downstream calls fall back to keying
            on the upstream URL — which fal mints fresh per upload, so the
            downstream entry can never be reused across runs or machines. It
            also means ``asset_id`` is *not* a content hash, in violation of
            ``lacing.Artifact``'s contract. Use it only when you genuinely
            want URL-only artifacts and no reuse.
        asset_fetcher: Injected byte source (``url -> Iterable[bytes]``) used to
            read media results; defaults to a ``urllib``-based fetcher. This is
            the seam a **hermetic test suite** should use: a downstream suite
            whose stubbed fal responses carry made-up URLs must inject a fake
            transport here, or execution will reach for the network. (Setting
            ``$FALAW_FETCH_ARTIFACT_BYTES=0`` also works but is blunter — it
            turns off content addressing altogether, so the suite stops
            exercising the thing it is testing.)

    Failure handling — a paid result is never discarded
    ---------------------------------------------------
    Two different things can go wrong when reading a result's bytes, and they
    get two different answers:

    - **A fresh call whose bytes cannot be fetched.** fal has already run — and
      billed — the generation. Raising would throw away a result we paid for,
      typically over a transient network failure. So the artifact **degrades**:
      ``url`` is kept, ``bytes_size`` stays 0, ``asset_id`` is a digest of the
      response and is *not* claimed to be a content hash, and a
      :class:`UserWarning` is emitted. Downstream key resolution reads
      ``bytes_size == 0`` and falls back to the URL — a guaranteed cache
      *miss*, never a wrong hit.
    - **A cache hit that cannot be materialized** — fal deleted the URL and the
      bytes are not in the content store. The entry is unusable, so it is
      treated as a **miss**: it is invalidated and the call re-executed once.
      A cache must never become a trap whose only escape is re-billing the
      whole plan with ``use_cache=False``.

    Placeholder resolution — the wire/key split
    -------------------------------------------
    Any string argument equal to ``"<from N>"`` (for an integer ``N``) is
    rewritten *just before* the call is made — so a multi-step plan (e.g.
    generate_image → image_to_video) can reference the upstream output without
    the planner needing to know its URL. The rewrite happens after the upstream
    call has executed; planning itself is unaffected.

    It happens **twice**, into two different argument sets, because the same
    value cannot serve both jobs:

    - the **wire** arguments get ``artifacts[N].url`` — what fal needs in order
      to fetch the input;
    - the **key** arguments get ``sha256:<artifacts[N].asset_id>`` — the
      upstream's content hash, so a byte-identical upstream regeneration
      produces a downstream cache *hit* instead of re-billing the expensive
      call. Keying on the URL instead is the defect this split exists to fix
      (falaw#14): fal mints a unique URL per upload, so a URL-keyed downstream
      entry is unreachable the moment the upstream genuinely re-runs.

    An upstream artifact with no materialized bytes has no content hash, so its
    key ref falls back to the URL — a guaranteed miss, never a wrong hit.

    Returns:
        One :class:`lacing.Artifact` per :class:`CallPlan` in ``plan.calls``,
        in the same order.
    """
    from lacing import Artifact

    if dry_run:
        return [_synthetic_artifact(c) for c in plan.calls]

    if artifact_converter is not None:
        _refuse_converter_configuration(content_store, fetch_bytes, asset_fetcher)
        converter = artifact_converter
        # A custom converter defines its own notion of a usable artifact, so we
        # do not second-guess its cache hits.
        usable_from_cache = _always_usable
    else:
        wants_bytes = _fetch_bytes_default() if fetch_bytes is None else fetch_bytes
        converter = _make_artifact_converter(
            content_store=content_store,
            fetch_bytes=wants_bytes,
            asset_fetcher=asset_fetcher,
        )
        usable_from_cache = _make_usability_check(fetch_bytes=wants_bytes)

    artifacts: list[Artifact] = []
    for call in plan.calls:
        wire_args = _resolve_placeholders(call.arguments, artifacts, ref=_wire_ref)
        # Only resolved when it will be used — the key ref is stricter than the
        # wire ref (it needs bytes *or* a URL), and an uncached run must not
        # inherit that stricter requirement.
        key_args = (
            _resolve_placeholders(call.arguments, artifacts, ref=_key_ref)
            if use_cache
            else wire_args
        )
        artifacts.append(
            _execute_call(
                call,
                wire_args,
                key_args,
                converter=converter,
                usable_from_cache=usable_from_cache,
                use_cache=use_cache,
                on_event=on_event,
            )
        )
    return artifacts


def _execute_call(
    call: CallPlan,
    wire_args: dict,
    key_args: dict,
    *,
    converter: "ResultToArtifact",
    usable_from_cache,
    use_cache: bool,
    on_event,
):
    """Run one :class:`CallPlan`, returning its Artifact. See :func:`execute`.

    Split out of the loop because a cache hit is not unconditionally usable:
    the response may name an asset fal has since deleted, whose bytes are not
    in the content store. That entry can never become an artifact again, so it
    is dropped and the call re-executed — the alternative is a cache entry that
    fails forever and can only be escaped by re-billing the entire plan.
    """
    from .cache import cached_call_fal, drop_cache_entry, emit_cache_hit
    from .core import call_fal

    key_arguments = None if key_args is wire_args else key_args
    if use_cache:
        from .cache import cache_get

        hit = cache_get(call.application, key_args)
        if hit is not None:
            # Speculative: the conversion may turn out to be unusable, in which
            # case its own complaints are noise the caller must not see (we are
            # about to discard the artifact and say something more useful). Any
            # warning from a conversion we *keep* is replayed verbatim.
            with warnings.catch_warnings(record=True) as probe_warnings:
                warnings.simplefilter("always")
                artifact = converter(hit, call)
            if usable_from_cache(artifact, hit):
                for w in probe_warnings:
                    warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)
                emit_cache_hit(call.application, on_event)
                return artifact
            warnings.warn(
                f"Dropping the falaw cache entry for {call.application!r}: its "
                "recorded result names an asset that can no longer be read "
                "(fal-served URLs expire and are permanently deleted, and the "
                "bytes are not in the content store). Re-executing the call — "
                "this one costs money.",
                UserWarning,
                stacklevel=3,
            )
            drop_cache_entry(call.application, key_args)
        raw = cached_call_fal(
            call.application,
            wire_args,
            key_arguments=key_arguments,
            refresh=True,
            on_event=on_event,
        )
    else:
        raw = call_fal(call.application, wire_args, on_event=on_event)
    return converter(raw, call)


def _content_ref_or_none(url: str, content_store, asset_fetcher):
    """``(ContentRef | None, store)`` for ``url`` — ``None`` on a fetch failure.

    fal has already run and **billed** the generation by the time we get here,
    so a failure to read the bytes must not throw the result away: a transient
    network error would turn a paid render into nothing at all. The caller
    degrades to a URL-only artifact instead, and this function makes the
    failure loud rather than silent.
    """
    from .content import content_ref_for_url, default_content_store
    from .errors import FalAssetFetchError

    store = default_content_store() if content_store is None else content_store
    try:
        return content_ref_for_url(url, store=store, fetcher=asset_fetcher), store
    except FalAssetFetchError as e:
        warnings.warn(
            f"{e} Falling back to a URL-only artifact: `asset_id` is a digest "
            "of the response, NOT a content hash, and `bytes_size` is 0. "
            "Chained calls downstream of it cannot be cache-reused, and the "
            "artifact dies with the URL.",
            UserWarning,
            stacklevel=4,
        )
        return None, store


def _always_usable(artifact, raw: dict) -> bool:
    return True


def _make_usability_check(*, fetch_bytes: bool):
    """Whether a cache hit converted by the **built-in** converter is usable.

    Unusable means exactly one thing: bytes were wanted, the recorded response
    names an asset, and the artifact came back with none — so the bytes are
    neither behind the URL nor in the content store, and no amount of retrying
    the *cache* will produce them.
    """

    def usable(artifact, raw: dict) -> bool:
        if not fetch_bytes:
            return True
        if artifact.bytes_size > 0:
            return True
        return _extract_first_url(raw) is None

    return usable


def _refuse_converter_configuration(content_store, fetch_bytes, asset_fetcher) -> None:
    """Reject ``artifact_converter=`` combined with built-in-converter knobs.

    ``content_store`` / ``fetch_bytes`` / ``asset_fetcher`` configure the
    built-in converter and are structurally unreachable from a custom one.
    Accepting them silently is worse than useless: a caller pointing falaw at a
    shared S3 content store *and* supplying a converter would get an empty
    store and no indication why.
    """
    supplied = [
        name
        for name, value in (
            ("content_store", content_store),
            ("fetch_bytes", fetch_bytes),
            ("asset_fetcher", asset_fetcher),
        )
        if value is not None
    ]
    if supplied:
        raise ValueError(
            f"execute(artifact_converter=...) cannot be combined with "
            f"{', '.join(supplied)} — those configure the built-in converter "
            "and a custom converter cannot honour them. Configure your "
            "converter directly (see falaw.plan._artifact_from_response for "
            "the built-in one), or drop artifact_converter."
        )


_PLACEHOLDER_PREFIX = "<from "

CONTENT_REF_PREFIX = "sha256:"
"""Prefix marking a content hash where a cache key would otherwise hold a URL.

Self-describing on purpose: a reader of a cache manifest can tell at a glance
that an argument was keyed on *what the upstream produced* rather than *where
it was served from*, and the prefixed form can never be confused with a
literal URL argument.
"""


def _wire_ref(artifact, idx: int, placeholder: str) -> str:
    """What a ``<from N>`` reference becomes **on the wire** — the upstream URL."""
    if not artifact.url:
        raise ValueError(
            f"Placeholder {placeholder!r} references artifact[{idx}] but it has no URL."
        )
    return artifact.url


def _key_ref(artifact, idx: int, placeholder: str) -> str:
    """What a ``<from N>`` reference becomes **in the cache key**.

    The upstream's content hash (``sha256:<hex>``) whenever its bytes were
    materialized — that is what makes a byte-identical upstream regeneration
    hit downstream. ``bytes_size > 0`` is the signal that ``asset_id`` really
    is the SHA-256 of those bytes; it holds for falaw's own converter and is
    the contract a custom ``artifact_converter`` must honour.

    With no bytes there is no content identity, so we fall back to the URL:
    sound but unreusable (a fresh URL each upload ⇒ a guaranteed miss), which
    is strictly better than inventing an id that could produce a *wrong* hit.
    """
    if artifact.bytes_size > 0:
        return f"{CONTENT_REF_PREFIX}{artifact.asset_id}"
    if artifact.url:
        return artifact.url
    raise ValueError(
        f"Placeholder {placeholder!r} references artifact[{idx}] but it has "
        "neither materialized bytes nor a URL."
    )


def _resolve_placeholders(arguments: dict, artifacts: list, *, ref) -> dict:
    """Rewrite ``<from N>`` strings in ``arguments`` via ``ref(artifact, idx, ph)``.

    Only string values are rewritten; nested dicts/lists/tuples are recursed
    into. ``arguments`` is not modified — a new dict is returned when any
    rewrite happens, otherwise the original object is returned (identity that
    :func:`execute` uses to detect "wire and key arguments are the same").
    """
    if not _has_placeholder(arguments):
        return arguments
    return _resolve(arguments, artifacts, ref)


def _has_placeholder(value) -> bool:
    if isinstance(value, str):
        return value.startswith(_PLACEHOLDER_PREFIX)
    if isinstance(value, dict):
        return any(_has_placeholder(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_placeholder(v) for v in value)
    return False


def _resolve(value, artifacts: list, ref):
    if isinstance(value, str) and value.startswith(_PLACEHOLDER_PREFIX):
        return _lookup_artifact_ref(value, artifacts, ref)
    if isinstance(value, dict):
        return {k: _resolve(v, artifacts, ref) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, artifacts, ref) for v in value]
    if isinstance(value, tuple):
        return tuple(_resolve(v, artifacts, ref) for v in value)
    return value


def _lookup_artifact_ref(placeholder: str, artifacts: list, ref) -> str:
    """Parse ``"<from N>"`` and return ``ref(artifacts[N], N, placeholder)``."""
    body = placeholder[len(_PLACEHOLDER_PREFIX) :].rstrip(">").strip()
    try:
        idx = int(body)
    except ValueError as e:
        raise ValueError(
            f"Bad placeholder {placeholder!r} — expected '<from N>' where N is an integer."
        ) from e
    if idx < 0 or idx >= len(artifacts):
        raise ValueError(
            f"Placeholder {placeholder!r} references artifact index {idx}, "
            f"but only {len(artifacts)} artifact(s) have been materialized."
        )
    return ref(artifacts[idx], idx, placeholder)


def _synthetic_artifact(call: CallPlan):
    """A placeholder Artifact for ``dry_run=True``. Not byte-stable across runs."""
    from lacing import Artifact, hash_bytes

    # Deterministic asset_id from the call's identity, so dry-run twice over
    # the same Plan yields the same Artifact.id pair (helpful for testing).
    import json as _json

    blob = _json.dumps(
        {"app": call.application, "args": call.arguments, "tool": call.tool},
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    synthetic_id = hash_bytes(blob)
    return Artifact(
        asset_id=synthetic_id,
        kind=call.output_kind,
        path=None,
        url=None,
        bytes_size=0,
        duration_s=None,
        mime=None,
        provenance=_dry_run_provenance(call),
        cost_usd=0.0,
        producer_call_id=f"dry-run:{synthetic_id[:12]}",
    )


def _dry_run_provenance(call: CallPlan):
    from lacing.artifact import _now_rt
    from lacing.model import Provenance

    return Provenance(
        was_generated_by=f"agent:falaw-plan@{call.application}",
        was_attributed_to="dry-run",
        was_derived_from=[],
        generated_at_time=_now_rt(),
        activity="infer",
    )


def _make_artifact_converter(
    *, content_store=None, fetch_bytes: bool = True, asset_fetcher=None
) -> ResultToArtifact:
    """Build the default raw-response → :class:`lacing.Artifact` converter.

    A factory rather than a plain function because the conversion needs three
    injected decisions — *which* content store the bytes land in, *how* they
    are read, and whether to read them at all — while :data:`ResultToArtifact`
    (the pluggable converter contract every caller may implement) stays a
    two-argument callable.
    """

    def convert(raw: dict, call: CallPlan):
        return _artifact_from_response(
            raw,
            call,
            content_store=content_store,
            fetch_bytes=fetch_bytes,
            asset_fetcher=asset_fetcher,
        )

    return convert


def _artifact_from_response(
    raw: dict,
    call: CallPlan,
    *,
    content_store=None,
    fetch_bytes: bool = True,
    asset_fetcher=None,
):
    """Convert a fal response to an Artifact using the common response shapes.

    Handles these patterns observed across fal models:

    - ``{"images": [{"url": ..., "content_type": ...}, ...]}`` — flux family
    - ``{"image": {"url": ..., "content_type": ...}}``        — some edits
    - ``{"video": {"url": ..., "content_type": ...}}``        — i2v / t2v / lipsync
    - ``{"audio": {"url": ..., "content_type": ...}}``        — TTS
    - ``{"audio_url": "..."}``                                — voice-clone
    - ``{"output": "..."}`` (string)                          — LLM endpoints

    The first matching pattern wins. For multi-asset responses (e.g. flux
    with ``num_images > 1``), only the first asset becomes an Artifact —
    callers wanting all assets should provide their own converter.

    Every Artifact is **content-addressed**: ``asset_id`` is the SHA-256 of the
    artifact's bytes, as ``lacing.Artifact`` contractually requires.

    - Media calls: the bytes are streamed once into ``content_store`` (see
      :mod:`falaw.content`), ``bytes_size`` is their real length, ``url`` is
      kept as a *hint*, and the artifact survives fal deleting the URL because
      the bytes are in the store. ``path`` is set when the store exposes a
      local file for the blob (the directory-backed default does; an in-memory
      or object-store one returns ``None`` — read those through
      ``ArtifactStore.iter_blob(asset_id)``). Re-converting the same response
      later is download-free (the ``url -> content hash`` index).
    - ``json`` / ``text`` calls with **no URL** — the ``fal-ai/any-llm`` case:
      the textual response is materialized to a content-addressed file in the
      falaw cache and ``Artifact.path`` points at it.

    Degraded (URL-only) artifacts
    -----------------------------
    Two cases produce an Artifact whose ``asset_id`` is a digest of the whole
    response rather than a content hash, with ``bytes_size == 0``: an explicit
    ``fetch_bytes=False``, and a fetch that failed (which also emits a
    :class:`UserWarning` — see :func:`execute` for why a *billed* result is
    degraded rather than discarded).

    The response digest is deliberately **not** the SHA-256 of the URL. Hashing
    the URL is the falaw#14 defect: it looks like a content hash, so it makes
    two byte-identical renders appear different while satisfying every check
    that only tests "is this 64 hex chars". ``bytes_size == 0`` is the honest
    signal, and it is what downstream key resolution reads to fall back to the
    URL rather than trust the id.

    Note that ``path``/``url`` are location *hints*, machine-local in the
    ``path`` case. Only ``asset_id`` + the content store are portable.
    """
    from lacing import Artifact
    from lacing.artifact import _now_rt
    from lacing.model import Provenance

    url = _extract_first_url(raw)
    duration = _extract_duration_s(raw)
    mime = _extract_content_type(raw)
    path = None
    bytes_size = 0

    if url and fetch_bytes:
        ref, store = _content_ref_or_none(url, content_store, asset_fetcher)
        if ref is None:
            # A degraded, honestly-labelled artifact — never a lost paid result.
            asset_id = _response_digest(raw)
        else:
            asset_id = ref.content_hash
            bytes_size = ref.bytes_size
            path = store.blob_path(asset_id)
    elif url:
        # No bytes ⇒ no content identity. Digest the response rather than the
        # URL so nothing pretends to be a content hash; see the docstring.
        asset_id = _response_digest(raw)
    elif call.output_kind in ("json", "text"):
        # LLM-style response: no URL, the content *is* the text. Materialize
        # it to a content-addressed cache file so the Artifact is usable.
        content = _extract_text_content(raw)
        if call.output_kind == "json":
            # ``output_kind="json"`` promises a parseable JSON artifact,
            # but real models wrap it in a ```json fence anyway.
            content = _unwrap_json_fence(content)
        path, asset_id = _materialize_text_to_cache(content, call.output_kind)
        bytes_size = len(content.encode("utf-8"))
        mime = mime or (
            "application/json" if call.output_kind == "json" else "text/plain"
        )
    else:
        # Last-resort: hash the response itself.
        asset_id = _response_digest(raw)

    prov = Provenance(
        was_generated_by=f"agent:fal@{call.application}",
        was_attributed_to=call.metadata.get("attributed_to", "user:unknown"),
        was_derived_from=[],
        generated_at_time=_now_rt(),
        activity="create",
    )

    return Artifact(
        asset_id=asset_id,
        kind=call.output_kind,
        path=path,
        url=url,
        bytes_size=bytes_size,
        duration_s=duration,
        mime=mime,
        provenance=prov,
        cost_usd=call.billable_cost_usd or None,
        producer_call_id=None,  # set by orchestrators that thread through call_id
    )


def _response_digest(raw) -> str:
    """SHA-256 of the canonicalized response — a last-resort, non-content id.

    Used only where falaw has no bytes to hash. It is *not* a content hash and
    must never be treated as one: it changes whenever any field of the response
    changes (including a re-minted URL), which is exactly what makes it safe —
    it can only ever cause a cache *miss*, never a wrong hit.
    """
    import json as _json

    from lacing import hash_bytes

    return hash_bytes(_json.dumps(raw, sort_keys=True, default=str).encode("utf-8"))


def _unwrap_json_fence(text: str) -> str:
    """Strip a Markdown code fence an LLM wrapped a JSON response in.

    ``output_kind="json"`` promises the materialized artifact is a
    parseable JSON document, but real models routinely answer with
    ```` ```json … ``` ```` even when the prompt forbids it. Drop a
    leading ```` ``` ```` / ```` ```json ```` line and a trailing
    ```` ``` ```` line; a clean (non-fenced) body is returned unchanged
    apart from surrounding whitespace. This normalizes — it does not
    validate — so unparseable text passes through untouched.
    """
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    lines = lines[1:]  # drop the opening ``` / ```json line
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_text_content(raw) -> str:
    """Pull plain text out of an LLM response shape (any-llm / OpenAI-style).

    Mirrors the extraction in ``falaw.operations.llm``; kept here so the
    converter has no dependency on the operations layer.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("output", "text", "response", "completion", "content"):
            v = raw.get(key)
            if isinstance(v, str) and v.strip():
                return v
        choices = raw.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            msg = choices[0].get("message")
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                return msg["content"]
    return str(raw)


def _materialize_text_to_cache(content: str, kind: str) -> tuple[str, str]:
    """Write ``content`` to a content-addressed file in the falaw cache.

    Returns ``(path, asset_id)`` where ``asset_id`` is the SHA-256 hex of the
    content bytes. Idempotent: the same content writes the same file.
    """
    import os

    from lacing import hash_bytes

    from .cache import _cache_dir

    data = content.encode("utf-8")
    asset_id = hash_bytes(data)
    ext = ".json" if kind == "json" else ".txt"
    assets_dir = os.path.join(_cache_dir(), "assets")
    os.makedirs(assets_dir, exist_ok=True)
    path = os.path.join(assets_dir, f"llm-{asset_id}{ext}")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return path, asset_id


def _extract_first_url(raw: dict) -> Optional[str]:
    """Find the first asset URL in a fal response, regardless of shape."""
    if not isinstance(raw, dict):
        return None
    images = raw.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return first.get("url")
        if isinstance(first, str):
            return first
    for key in ("video", "audio", "image"):
        v = raw.get(key)
        if isinstance(v, dict) and "url" in v:
            return v["url"]
    if isinstance(raw.get("audio_url"), str):
        return raw["audio_url"]
    if isinstance(raw.get("video_url"), str):
        return raw["video_url"]
    if isinstance(raw.get("image_url"), str):
        return raw["image_url"]
    return None


def _extract_duration_s(raw: dict) -> Optional[float]:
    if not isinstance(raw, dict):
        return None
    for key in ("video", "audio"):
        v = raw.get(key)
        if isinstance(v, dict):
            d = v.get("duration") or v.get("duration_s")
            if isinstance(d, (int, float)):
                return float(d)
    return None


def _extract_content_type(raw: dict) -> Optional[str]:
    if not isinstance(raw, dict):
        return None
    for key in ("video", "audio", "image"):
        v = raw.get(key)
        if isinstance(v, dict) and isinstance(v.get("content_type"), str):
            return v["content_type"]
    images = raw.get("images")
    if isinstance(images, list) and images and isinstance(images[0], dict):
        return images[0].get("content_type")
    return None
