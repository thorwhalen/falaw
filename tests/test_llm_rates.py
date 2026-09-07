"""Tests for the per-routed-model LLM rate table and its ceiling quote (falaw#50 A)."""

from __future__ import annotations

import json

import pytest

from falaw.llm_rates import (
    TOKENS_PER_RATE_UNIT,
    LlmRate,
    _rates_path,
    get_llm_rate,
    list_llm_rates,
    llm_ceiling_usd,
    load_llm_rates,
)
from falaw.operations.llm import _DEFAULT_LLM, _DEFAULT_MODEL
from falaw.plan import Plan, plan_hash
from falaw.registry import get_model

# The `model` enum fal's any-llm endpoint doc published on the table's fetch
# date. Pinned here so a stale table shows up as a failing test rather than as
# an unpriceable plan in someone's pipeline.
ANY_LLM_MODEL_ENUM = (
    "deepseek/deepseek-r1",
    "deepseek/deepseek-v3.1-terminus",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-haiku-4.5",
    "anthropic/claude-3.7-sonnet",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3-5-haiku",
    "anthropic/claude-3-haiku",
    "google/gemini-pro-1.5",
    "google/gemini-flash-1.5",
    "google/gemini-flash-1.5-8b",
    "google/gemini-2.0-flash-001",
    "google/gemini-2.5-flash",
    "google/gemini-2.5-flash-lite",
    "google/gemini-2.5-pro",
    "meta-llama/llama-3.2-1b-instruct",
    "meta-llama/llama-3.2-3b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-3.1-70b-instruct",
    "openai/gpt-oss-120b",
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "openai/gpt-4.1",
    "openai/o3",
    "openai/gpt-5-chat",
    "openai/gpt-5-mini",
    "openai/gpt-5-nano",
    "meta-llama/llama-4-maverick",
    "meta-llama/llama-4-scout",
    "moonshotai/kimi-k2.5",
)

# A model with both bases populated, used wherever a test needs token rates.
PRICED_MODEL = "anthropic/claude-sonnet-4.5"
# A model fal routes but nobody publishes upstream token rates for.
PER_CALL_ONLY_MODEL = "google/gemini-flash-1.5"


# --- the table is data, and the data is well-formed -------------------------


def test_table_covers_every_model_the_router_accepts():
    table = load_llm_rates()
    assert set(ANY_LLM_MODEL_ENUM) <= set(table)


def test_falaw_default_model_is_priced():
    # The one that matters most: every plan_llm_complete with no `model=`
    # routes here, so an unpriced default would make every LLM plan unknown.
    assert get_llm_rate(_DEFAULT_MODEL) is not None


def test_every_row_carries_a_source_and_a_date():
    for rate in list_llm_rates():
        assert rate.source, f"{rate.model} has no source"
        assert rate.date, f"{rate.model} has no date"


def test_every_row_prices_a_request_positively():
    # A zero or negative per-request price would plan as known-free and sail
    # through a spend gate — the failure mode the whole issue is about.
    for rate in list_llm_rates():
        assert rate.per_call_usd > 0, rate.model


def test_token_rates_are_both_present_or_both_absent_and_non_negative():
    for rate in list_llm_rates():
        both = (rate.input_usd_per_mtok is None) == (rate.output_usd_per_mtok is None)
        assert both, f"{rate.model} has half a token basis"
        assert rate.has_token_rates == (rate.input_usd_per_mtok is not None)
        for value in (rate.input_usd_per_mtok, rate.output_usd_per_mtok):
            if value is not None:
                assert value >= 0, rate.model


def test_tier_is_one_of_the_two_fal_publishes():
    assert {r.tier for r in list_llm_rates()} <= {"standard", "premium"}


def test_premium_rows_cost_more_per_request_than_standard_rows():
    by_tier = {"standard": set(), "premium": set()}
    for rate in list_llm_rates():
        by_tier[rate.tier].add(rate.per_call_usd)
    assert min(by_tier["premium"]) > max(by_tier["standard"])


def test_table_file_is_versioned():
    with open(_rates_path(), encoding="utf-8") as f:
        table = json.load(f)
    assert isinstance(table["version"], int)
    assert table["rows"]


# --- the fix: the routed model, not the router ------------------------------


def test_default_model_quotes_above_the_flat_router_price():
    # The bug: fal-ai/any-llm's single record says $0.001, but falaw's default
    # model is on fal's published premium list and bills 10x that. A gate fed
    # the router price under-quotes every LLM call in the pipeline.
    router_flat = get_model(_DEFAULT_LLM).cost_estimate.amount
    assert llm_ceiling_usd(_DEFAULT_MODEL) > router_flat


def test_unknown_model_is_unknown_not_the_router_price():
    assert llm_ceiling_usd("some/model-nobody-priced") is None
    assert get_llm_rate("some/model-nobody-priced") is None


# --- the ceiling: composition, monotonicity, all-or-nothing -----------------


def test_hints_never_quote_below_the_request_price():
    flat = llm_ceiling_usd(PRICED_MODEL)
    tiny = llm_ceiling_usd(PRICED_MODEL, input_tokens=1, max_output_tokens=1)
    assert tiny == flat


def test_a_long_prompt_on_a_big_model_quotes_above_the_request_price():
    flat = llm_ceiling_usd(PRICED_MODEL)
    long_prompt = llm_ceiling_usd(
        PRICED_MODEL, input_tokens=200_000, max_output_tokens=8_000
    )
    assert long_prompt > flat


@pytest.mark.parametrize("hint", ["input_tokens", "max_output_tokens"])
def test_quote_is_monotone_in_each_token_hint(hint):
    base = {"input_tokens": 10_000, "max_output_tokens": 10_000}
    previous = None
    for value in (0, 1_000, 50_000, 1_000_000):
        quote = llm_ceiling_usd(PRICED_MODEL, **{**base, hint: value})
        if previous is not None:
            assert quote >= previous
        previous = quote


def test_the_token_basis_uses_the_published_per_million_rates():
    rate = get_llm_rate(PRICED_MODEL)
    input_tokens, output_tokens = 500_000, 100_000
    expected = (
        input_tokens * rate.input_usd_per_mtok
        + output_tokens * rate.output_usd_per_mtok
    ) / TOKENS_PER_RATE_UNIT
    quote = llm_ceiling_usd(
        PRICED_MODEL, input_tokens=input_tokens, max_output_tokens=output_tokens
    )
    assert quote == pytest.approx(expected)
    assert quote > rate.per_call_usd  # the token basis is what binds here


def test_count_scales_the_quote():
    one = llm_ceiling_usd(PRICED_MODEL, input_tokens=100_000, max_output_tokens=1_000)
    three = llm_ceiling_usd(
        PRICED_MODEL, input_tokens=100_000, max_output_tokens=1_000, count=3
    )
    assert three == pytest.approx(3 * one)


@pytest.mark.parametrize(
    "hints",
    [
        {"input_tokens": 50_000},
        {"max_output_tokens": 4_000},
    ],
)
def test_a_token_quote_that_cannot_be_bounded_is_unknown(hints):
    # Half a bound is not a ceiling. None forces approval; a number here would
    # look like a ceiling and silently not be one.
    assert llm_ceiling_usd(PRICED_MODEL, **hints) is None


def test_a_row_without_token_rates_still_prices_a_plain_call():
    assert llm_ceiling_usd(PER_CALL_ONLY_MODEL) is not None


def test_a_row_without_token_rates_cannot_answer_a_token_quote():
    assert (
        llm_ceiling_usd(
            PER_CALL_ONLY_MODEL, input_tokens=50_000, max_output_tokens=1_000
        )
        is None
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"input_tokens": -1, "max_output_tokens": 10},
        {"input_tokens": 10, "max_output_tokens": -1},
        {"count": -1},
    ],
)
def test_negative_quantities_are_refused(kwargs):
    with pytest.raises(ValueError):
        llm_ceiling_usd(PRICED_MODEL, **kwargs)


# --- the override seam ------------------------------------------------------


def test_rates_override_replaces_the_committed_table():
    mine = {
        "my/model": LlmRate(
            model="my/model",
            tier="standard",
            per_call_usd=0.5,
            input_usd_per_mtok=1.0,
            output_usd_per_mtok=2.0,
            source="reconciled against my invoice",
            date="2026-09-07",
        )
    }
    assert llm_ceiling_usd("my/model", rates=mine) == 0.5
    # The committed table is not consulted, and not mutated.
    assert llm_ceiling_usd(PRICED_MODEL, rates=mine) is None
    assert get_llm_rate("my/model") is None


# --- plan_llm_complete wiring ----------------------------------------------


def _plan(**kwargs):
    from falaw import plan_llm_complete

    return plan_llm_complete("summarize this", consult_cache=False, **kwargs)


def test_plan_quotes_the_routed_model_not_the_router():
    router_flat = get_model(_DEFAULT_LLM).cost_estimate.amount
    assert _plan().estimated_cost_usd > router_flat


def test_plan_with_hints_quotes_more_than_without():
    assert (
        _plan(input_tokens=200_000, max_output_tokens=8_000).estimated_cost_usd
        > _plan().estimated_cost_usd
    )


def test_plan_hints_do_not_move_the_plan_hash():
    # Hints are estimator-only: adding one to an existing call site must not
    # change the cache identity or dedup key of the call it prices.
    plain = _plan()
    hinted = _plan(input_tokens=200_000, max_output_tokens=8_000)
    assert plain.arguments == hinted.arguments
    assert plan_hash(Plan(calls=(plain,))) == plan_hash(Plan(calls=(hinted,)))


def test_plan_takes_the_output_cap_from_extra_max_tokens():
    from_extra = _plan(input_tokens=200_000, extra={"max_tokens": 8_000})
    explicit = _plan(input_tokens=200_000, max_output_tokens=8_000)
    assert from_extra.estimated_cost_usd == explicit.estimated_cost_usd


def test_an_explicit_hint_wins_over_extra_max_tokens():
    plan = _plan(input_tokens=1, max_output_tokens=1, extra={"max_tokens": 8_000})
    assert plan.estimated_cost_usd == llm_ceiling_usd(
        _DEFAULT_MODEL, input_tokens=1, max_output_tokens=1
    )


@pytest.mark.parametrize("bogus", ["512", None, True, -1, 1.5])
def test_a_non_integer_extra_max_tokens_leaves_the_hint_unset(bogus):
    # `extra` is a free-form pass-through; only a real non-negative int is a
    # usable bound. Anything else must not be coerced into one.
    plan = _plan(input_tokens=200_000, extra={"max_tokens": bogus})
    assert plan.estimated_cost_usd is None


def test_plan_for_an_unpriced_model_forces_approval():
    plan = _plan(model="some/model-nobody-priced")
    assert plan.estimated_cost_usd is None
    assert Plan(calls=(plan,)).has_unknown_costs is True


def test_plan_accepts_a_rates_override():
    mine = {
        _DEFAULT_MODEL: LlmRate(
            model=_DEFAULT_MODEL,
            tier="standard",
            per_call_usd=0.25,
            source="reconciled against my invoice",
            date="2026-09-07",
        )
    }
    assert _plan(llm_rates=mine).estimated_cost_usd == 0.25
