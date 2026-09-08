"""Re-quote a persisted :class:`falaw.Plan` at today's rates (falaw#60).

A ``CallPlan``'s ``estimated_cost_usd`` is frozen at plan time. That is right —
a quote is a statement about a moment — but rate tables move: falaw 0.0.46
re-quoted every premium LLM call **tenfold upward**, so a preview saved the day
before under-quotes the run it is being used to price. Under-quoting is the one
direction a cost gate must never err in.

Re-quoting cannot be done from ``application`` and ``arguments`` alone. The
quantity hints that priced a call — a clip's duration, a prompt's token bound —
are estimator-only and deliberately never enter the wire arguments, so they are
not on the serialized call. :class:`falaw.CostBasis` is where a ``plan_*``
records them, together with which rate table it consulted; this module is what
reads one back:

>>> from falaw import plan_generate_image, Plan, reprice_plan
>>> plan = Plan(calls=(plan_generate_image("a tiger", consult_cache=False),))
>>> repriced = reprice_plan(plan)
>>> [c.status for c in repriced.calls]
['unchanged']
>>> repriced.plan.total_cost_usd == plan.total_cost_usd
True

Three rules, in order of importance:

- **Pure data.** Nothing here touches the network or a billing API, exactly
  like ``plan_*``. Re-pricing reads the committed tables and does arithmetic.
- **A plan with no basis is never assumed current.** Such a call comes back as
  ``"no_basis"`` with its cost *cleared to* ``None``. Keeping the frozen figure
  would be the bug this module exists to fix, dressed as a feature.
- **Unknown is unknown, never free.** A basis whose model has left the
  catalogue, whose pricer is not registered, or whose table no longer prices it
  re-prices to ``None`` — which lights up
  :attr:`falaw.Plan.has_unknown_costs` and forces approval.

The per-call diff says which of those happened, and
:attr:`CallRepricing.basis_changed` says whether the *table* moved underneath
the quote — the audit answer the frozen number could never give.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Iterator, Literal, Mapping, Optional

from .cost import estimate_call_cost
from .llm_rates import (
    CUSTOM_LLM_RATES_TABLE,
    LLM_RATES_TABLE,
    llm_ceiling_usd,
    llm_rates_table_version,
)
from .plan import CallPlan, CostBasis, Plan
from .registry import MODEL_CATALOGUE_TABLE, get_model, models_table_version


RepriceStatus = Literal["unchanged", "changed", "unknown", "no_basis"]
"""What re-pricing was able to say about one call.

- ``unchanged``: re-quoted, and today's rates give the same number.
- ``changed``: re-quoted to a different number — the interesting case.
- ``unknown``: a basis was present but could not be re-quoted — the model has
  left the catalogue, no pricer is registered under that name, the table no
  longer prices it, or the basis names a **different table** than the pricer
  reads (two sets of books do not re-quote each other). The new cost is
  ``None``.
- ``no_basis``: the call carries no :class:`falaw.CostBasis` at all — it was
  planned before falaw#60, or by something that never recorded one. The new
  cost is ``None``, because the honest answer to "what does this cost today?"
  is that nobody can tell.
"""


CATALOGUE_PRICER = "model_catalogue"
"""``CostBasis.pricer`` for a call priced from a ``models.json`` record."""

LLM_RATES_PRICER = "llm_rates"
"""``CostBasis.pricer`` for a routed LLM call priced from ``llm_rates.json``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Pricer:
    """One pricing rule, and the table that backs it.

    The seam for a caller with their own numbers: build a ``Pricer`` closing
    over a reconciled rate table and pass ``pricers={**DFLT_PRICERS,
    LLM_RATES_PRICER: mine}`` to :func:`reprice_plan`. The ``table`` /
    ``version`` pair is stamped onto the re-priced call's basis, so the next
    audit can see which table produced which number.

    ``table`` is also a **gate, not just a label**: a call whose basis names a
    different table is reported as ``unknown`` rather than re-quoted, so a row
    priced from your invoice is never silently re-quoted at falaw's published
    rate (or the reverse). Give your ``Pricer`` the same ``table`` string the
    basis carries — :data:`falaw.llm_rates.CUSTOM_LLM_RATES_TABLE` for anything
    a ``plan_*`` priced with ``llm_rates=``.
    """

    quote: Callable[[CostBasis], Optional[float]]
    """Price ``basis`` in USD, or return ``None`` for *unknown*. May raise; a
    raise is reported as ``"unknown"`` with the exception text as the reason,
    so one unpriceable row never aborts a whole plan's re-quote."""

    table: str
    """Identity of the table this pricer reads, for the refreshed basis."""

    version: Callable[[], str] = lambda: ""
    """Today's version of that table, for the refreshed basis."""


def _quote_from_catalogue(basis: CostBasis) -> Optional[float]:
    """Re-run :func:`falaw.estimate_call_cost` for a catalogue-priced call."""
    return estimate_call_cost(get_model(basis.priced), **basis.quantities)


def _quote_from_llm_rates(basis: CostBasis) -> Optional[float]:
    """Re-run :func:`falaw.llm_ceiling_usd` for a routed-LLM call."""
    return llm_ceiling_usd(basis.priced, **basis.quantities)


DFLT_PRICERS: Mapping[str, Pricer] = {
    CATALOGUE_PRICER: Pricer(
        quote=_quote_from_catalogue,
        table=MODEL_CATALOGUE_TABLE,
        version=models_table_version,
    ),
    LLM_RATES_PRICER: Pricer(
        quote=_quote_from_llm_rates,
        table=LLM_RATES_TABLE,
        version=llm_rates_table_version,
    ),
}
"""The pricers falaw ships — one per rate table it owns.

Keyed by :attr:`falaw.CostBasis.pricer`. A basis naming anything else
re-prices as ``"unknown"``: an unrecognized rule is a reason to refuse a
number, not to keep the old one.
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class CallRepricing:
    """The before/after for one call in a re-priced plan."""

    index: int
    """Position in the original :class:`falaw.Plan`."""

    call: CallPlan
    """The re-priced call — the same call with today's
    ``estimated_cost_usd`` and a basis stamped with today's table version."""

    old_cost_usd: Optional[float]
    """What the persisted plan said, ``None`` if it said unknown."""

    new_cost_usd: Optional[float]
    """What today's rates say, ``None`` for unknown or no-basis."""

    status: RepriceStatus
    """Which of the four cases this call fell into — see :data:`RepriceStatus`."""

    reason: str = ""
    """Why, when the status is ``"unknown"`` or ``"no_basis"``. Empty otherwise."""

    basis_changed: bool = False
    """True when the rate table's identity or version moved between the
    persisted basis and today's — the audit answer to "did the price change
    because the *table* changed?". Always ``False`` for ``"no_basis"``, which
    has nothing to compare against."""

    @property
    def delta_usd(self) -> Optional[float]:
        """``new - old``, or ``None`` when either side is unknown.

        ``None`` rather than ``0.0``: a call that lost or gained its price did
        not move by zero, and a caller summing deltas must not be handed a
        number that says it did.
        """
        if self.old_cost_usd is None or self.new_cost_usd is None:
            return None
        return self.new_cost_usd - self.old_cost_usd


@dataclass(frozen=True, slots=True, kw_only=True)
class RepricedPlan:
    """Result of :func:`reprice_plan` — the new Plan plus the per-call diff.

    Read :attr:`plan` for the re-quoted plan (it is an ordinary
    :class:`falaw.Plan`, so ``known_cost_usd`` / ``unknown_call_count`` /
    ``has_unknown_costs`` mean what they always mean), and :attr:`calls` for
    what changed and why.
    """

    plan: Plan
    """The re-priced plan. Structurally identical to the input — same calls,
    same order, same arguments, so ``plan_hash`` is unmoved — with today's
    costs."""

    calls: tuple[CallRepricing, ...] = ()
    """One entry per call of the input plan, in order."""

    def __len__(self) -> int:
        return len(self.calls)

    def __iter__(self) -> Iterator[CallRepricing]:
        return iter(self.calls)

    def __getitem__(self, idx):
        return self.calls[idx]

    @property
    def changed(self) -> tuple[CallRepricing, ...]:
        """Calls whose price moved — the ones a re-quote exists to surface."""
        return tuple(c for c in self.calls if c.status == "changed")

    @property
    def unpriced(self) -> tuple[CallRepricing, ...]:
        """Calls today's rates cannot price: ``"unknown"`` plus ``"no_basis"``.

        A budget gate refuses while this is non-empty, the same way it refuses
        on :attr:`falaw.Plan.has_unknown_costs` — the two are the same
        judgement, one made at re-quote time.
        """
        return tuple(c for c in self.calls if c.status in ("unknown", "no_basis"))

    @property
    def known_delta_usd(self) -> float:
        """Sum of :attr:`CallRepricing.delta_usd` over calls priced both times.

        The movement you can actually see. It says nothing about the calls in
        :attr:`unpriced` — read that alongside it, never this alone.
        """
        return sum((c.delta_usd or 0.0 for c in self.calls), 0.0)


def reprice_plan(
    plan: Plan,
    *,
    pricers: Mapping[str, Pricer] = DFLT_PRICERS,
) -> RepricedPlan:
    """Re-quote every call in ``plan`` against today's rate tables.

    Pure data: no network, no billing API, nothing executed. Returns a new
    :class:`RepricedPlan` — the input plan is untouched.

    A call carrying a :class:`falaw.CostBasis` is re-quoted through the pricer
    its basis names, with the exact quantity hints that produced the original
    figure, and comes back with a basis re-stamped to today's table version. A
    call carrying no basis is reported as ``"no_basis"`` and its cost is
    **cleared to** ``None``: the frozen number is a fact about a past moment,
    and silently re-presenting it as a current quote is the failure this
    function exists to prevent. That clearing lights up
    :attr:`falaw.Plan.has_unknown_costs`, which is exactly right — nobody can
    say what that call costs today.

    A basis is only re-quoted by a pricer reading the **same table** it names.
    A mismatch is ``"unknown"``, not a re-quote: two tables are two sets of
    books, and pricing a caller's reconciled $0.50 row at falaw's published
    $0.01 would be a 50x under-quote wearing the clothes of a price drop. Pass
    a :class:`Pricer` naming that table to re-quote against the same books.

    ``cache_status`` is carried through unchanged. Re-pricing answers "what
    would this cost?", not "is it still cached?"; peeking the cache here would
    quietly turn a re-quote into an I/O operation and make a hit look like a
    price drop. Re-plan the calls if you want a fresh cache reading.

    Args:
        plan: The plan to re-quote, typically just deserialized with
            :func:`falaw.plan_from_dict`.
        pricers: Pricing rules by :attr:`falaw.CostBasis.pricer` name. The seam
            for a caller who has reconciled real numbers against their own
            invoice — see :class:`Pricer`.

    >>> from falaw import Plan, CallPlan, reprice_plan
    >>> stale = CallPlan(tool="generate_image", application="fal-ai/flux/dev",
    ...                  arguments={"prompt": "a tiger"}, output_kind="image",
    ...                  estimated_cost_usd=0.025)
    >>> out = reprice_plan(Plan(calls=(stale,)))
    >>> out.calls[0].status
    'no_basis'
    >>> out.plan.calls[0].estimated_cost_usd is None   # unknown, not $0.025
    True
    >>> out.plan.has_unknown_costs
    True
    """
    rows = [
        _reprice_call(i, call, pricers=pricers) for i, call in enumerate(plan.calls)
    ]
    return RepricedPlan(
        plan=Plan(calls=tuple(r.call for r in rows)),
        calls=tuple(rows),
    )


def _reprice_call(
    index: int,
    call: CallPlan,
    *,
    pricers: Mapping[str, Pricer],
) -> CallRepricing:
    """One call's re-quote — the whole decision, in one place.

    Every ``unknown`` path leaves the *original* basis on the call: nothing
    re-priced it, so nothing new gets to claim it did. Only a call that came
    back with a number is re-stamped with the pricer's table and version.
    """
    old = call.estimated_cost_usd
    basis = call.cost_basis

    def unknown(reason: str, *, basis_changed: bool = False) -> CallRepricing:
        return CallRepricing(
            index=index,
            call=replace(call, estimated_cost_usd=None),
            old_cost_usd=old,
            new_cost_usd=None,
            status="unknown",
            reason=reason,
            basis_changed=basis_changed,
        )

    if basis is None:
        return CallRepricing(
            index=index,
            call=replace(call, estimated_cost_usd=None),
            old_cost_usd=old,
            new_cost_usd=None,
            status="no_basis",
            reason=(
                "no cost_basis recorded, so the quote cannot be re-run; the "
                "plan-time figure is a past fact, not a current price"
            ),
        )

    pricer = pricers.get(basis.pricer)
    if pricer is None:
        return unknown(f"no pricer registered as {basis.pricer!r}")

    if basis.table != pricer.table:
        # Two tables are two sets of books. Re-quoting a row priced against a
        # caller's reconciled invoice ($0.50) with falaw's published rate
        # ($0.01) is a 50x *under-quote* dressed as a price drop — the exact
        # direction this module exists to prevent, on the exact caller the
        # Pricer seam is advertised for. A caller who wants their own numbers
        # re-quoted passes a Pricer that names their table.
        return unknown(
            f"basis was priced against {basis.table or 'an unnamed table'!r}, "
            f"but pricer {basis.pricer!r} reads {pricer.table!r}; pass a Pricer "
            "naming that table to re-quote against the same books",
            basis_changed=True,
        )

    new_basis = replace(basis, table=pricer.table, table_version=pricer.version())
    basis_changed = basis.table_version != new_basis.table_version
    try:
        new = pricer.quote(basis)
    except Exception as exc:  # noqa: BLE001 — one bad row must not abort the plan
        # A persisted basis can name a model the catalogue has since dropped,
        # or carry a quantity a pricer no longer accepts. Both are honest
        # "unknown"s with a reason attached; raising here would make one stale
        # row cost the caller the other 199 re-quotes.
        return unknown(f"{type(exc).__name__}: {exc}", basis_changed=basis_changed)

    if new is None:
        return unknown(
            f"{basis.pricer!r} cannot price {basis.priced!r} today",
            basis_changed=basis_changed,
        )

    return CallRepricing(
        index=index,
        call=replace(call, estimated_cost_usd=new, cost_basis=new_basis),
        old_cost_usd=old,
        new_cost_usd=new,
        status="unchanged" if new == old else "changed",
        basis_changed=basis_changed,
    )


def catalogue_cost_basis(
    model_id: str,
    **quantities: Optional[float],
) -> CostBasis:
    """A :class:`falaw.CostBasis` for a call priced from ``models.json``.

    ``quantities`` are :func:`falaw.estimate_call_cost` keywords (``count``,
    ``seconds``, ``megapixels``, ``tokens``); ``None`` values are dropped, so a
    hint that was never supplied is recorded as absent rather than as ``null``
    — the same thing the estimator saw.

    >>> catalogue_cost_basis("fal-ai/flux/dev", seconds=None).quantities
    {}
    """
    return CostBasis(
        pricer=CATALOGUE_PRICER,
        priced=model_id,
        quantities=_supplied(quantities),
        table=MODEL_CATALOGUE_TABLE,
        table_version=models_table_version(),
    )


def llm_cost_basis(
    routed_model: str,
    *,
    input_tokens: Optional[int] = None,
    max_output_tokens: Optional[int] = None,
    custom_rates: bool = False,
) -> CostBasis:
    """A :class:`falaw.CostBasis` for a routed LLM call priced from the rate table.

    ``custom_rates=True`` records that the quote came from a caller-supplied
    ``rates=`` table rather than the committed one: there is no file to digest,
    so the version stays empty and the table names itself
    :data:`falaw.llm_rates.CUSTOM_LLM_RATES_TABLE`. :func:`reprice_plan` then
    **refuses** to re-quote it with the committed table, reporting ``unknown``
    — a caller's reconciled $0.50 row re-priced at falaw's published $0.01 is a
    50x under-quote, not a price drop. Re-quote it by passing a
    :class:`Pricer` over your table that names that same identity.
    """
    return CostBasis(
        pricer=LLM_RATES_PRICER,
        priced=routed_model,
        quantities=_supplied(
            {"input_tokens": input_tokens, "max_output_tokens": max_output_tokens}
        ),
        table=CUSTOM_LLM_RATES_TABLE if custom_rates else LLM_RATES_TABLE,
        table_version="" if custom_rates else llm_rates_table_version(),
    )


def _supplied(quantities: Mapping[str, object]) -> dict:
    """``quantities`` minus the keys whose value was ``None``."""
    return {k: v for k, v in quantities.items() if v is not None}
