# falaw roadmap

**Created 2026-08-04**, from the `video_gen` node-graph / ComfyUI research programme. Before
this, `misc/docs/` held only the mirrored fal.ai API documentation. This file is the ordering
and the *don't-do* list; the work itself lives in GitHub issues.

---

## What falaw owns

falaw owns **the priceable, cacheable, legally-permitted unit of billable work**.

```
lacing        annotation graph, Artifact, ArtifactStore (SSOT for content-addressed bytes)
   |
nw.Transform  plan() -> falaw.Plan   ...   execute() -> falaw.execute_plan
   |                                        (nw/transforms/__init__.py:206)
falaw.Plan    <-- the facade boundary: what will be called, what it costs, whether it is cached
   |
backends      fal.ai today; one more later (see Track 2)
```

Everything above falaw reads three numbers off a `Plan` and trusts them: `total_cost_usd`,
`has_unknown_costs`, `cache_hit_savings_usd` (reelee surfaces all three in its agent cost gate,
`reelee/agent.py:186-188`, and its CLI, `reelee/cli.py:136-137`). **Those three numbers being true
is falaw's core responsibility.** Three of the four tracks below exist because one of them
currently isn't.

---

## Track 1 — Content addressing (highest value; blocks all fan-out)

falaw addresses generated media by *where it is*, not by *what it is*. fal's own documentation
says **"Each upload produces a unique URL with no shared namespace"** and that expired CDN files
are **"permanently deleted and cannot be recovered"** (both mirrored in this repo at
`misc/docs/fal_ai_docs_full.md`, lines 17794 and 22058). So a URL identifies neither content nor
anything durable, and falaw keys on it in three places.

| | Where | What |
|---|---|---|
| **D3** | `falaw/plan.py:583` | `fake_id = hash_bytes(url)`, `bytes_size = 0` — breaks lacing's stated SHA-256-of-bytes contract |
| **D1** | `falaw/plan.py:432` + `falaw/cache.py:56-62` | `<from N>` resolves to `artifacts[N].url` *before* the cache key is computed |
| **D2** | `falaw/plan.py:357-363` vs `falaw/plan.py:432` | plan-time peek uses unresolved args; execute uses resolved args — different keys |

**Order:** D2 lands with Track 2 (same function, same pass). D3 lands before D1 (you cannot
substitute an `asset_id` for a URL until `asset_id` is the content hash).

**Note this is a documented shortcut, not an oversight.** `_default_artifact_converter`'s docstring
(`falaw/plan.py:562-568`) states "the Artifact's `asset_id` is the SHA-256 of the URL and
`bytes_size` is 0 (we don't download by default)". Fixing it means downloading bytes by default —
a real bandwidth and latency change — so it needs an opt-out and a docstring rewrite in the same
pass.

**Prerequisite already in place:** `lacing.ArtifactStore.put_blob` / `put_blob_stream`
(`lacing/artifact_store.py:182`, `:197`) is content-addressed, `dol`-backed, and **imported by
nothing in falaw** (`rg 'ArtifactStore|put_blob' falaw/` returns nothing). Use it; do not write a
second blob store here.

**Downstream in sibling repos** (do not attempt them from falaw):

- `lacing.Provenance.was_derived_from` is `list[UUID]` (`lacing/model.py:86`) and cannot hold a
  64-char hex `asset_id`, so artifact-to-artifact lineage is structurally unrepresentable —
  falaw writes `was_derived_from=[]` at both artifact sites (`falaw/plan.py:539`, `:608`).
  Widening it is a **lacing schema migration**, and because real data lives on the live server it
  falls under the on-disk-format exception: a genuine migration, not a rename.
- `nw.stale_after` is pure reachability and cannot compare content hashes until D1+D3 and the
  lacing migration land.

## Track 2 — Backend-parametric `Plan`

`CallPlan` gains `backend: str = "fal"`; `execute_plan` dispatches on it through an
`xdol.Registry`, defaulting to today's fal path; `backend` enters **both** `plan_hash` and the
per-call cache key. Additive, two files, roughly a day. It is the gate on a second execution
backend — **a Transform flavor without a priceable `Plan` reads $0.00 on a real GPU spend, which
under the committed prepaid-billing direction is a billing bug, not a style preference.**

## Track 3 — The terms-and-licence perimeter (new; falaw is the named owner)

A per-`(model, backend)` licence-and-terms ledger, **queried at plan time**, with `unknown`
meaning refusal — the same fail-closed discipline as `has_unknown_costs`. Copyleft is the famous
perimeter; vendor terms are the one that actually binds a commercial product, and until this round
nobody owned it. The key is `(model, backend)` and not `model` alone because the backend is
exactly what decides whether an upstream weights licence flows through to us: a model called
through a hosted API is governed by that host's terms, while the same weights self-hosted bind us
directly. **FLUX.1-dev is the worked example** — `flux-1-dev-non-commercial-license` on the
weights, and it is falaw's current default for `pick_model(category="image",
quality_tier="balanced")`. Ideogram's "entirely human generated" representation is the other
landmine: it is **incompatible with stamping C2PA `trainedAlgorithmicMedia`** — a contradiction,
not a caution.

## Track 4 — Cost data honesty

19 of 40 records in `falaw/data/models.json` carry **no** `cost_estimate` at all (6 of those 19 have
only the legacy free-text `cost_hint`); of the 21 that do, 16 are `source="approximate"`, 4
`"docs"`, 1 `"empirical"`. fal publishes `GET /v1/models/pricing?endpoint_id=...` and
`POST /v1/models/pricing/estimate`. Read the vendor's number instead of maintaining ours by hand;
that is what turns `has_unknown_costs=True` (forced approval on every plan touching an unpriced
model) into a real quote.

---

## Ordering

```
Track 2 (backend + D2) ──┐
                         ├──> a second execution backend
Track 1: D3 ──> D1 ──────┤
                         └──> fan-out of any size
Track 3 (ledger) ── independent, land before any third-party tenancy
Track 4 (pricing) ── independent, cheapest, unblocks gated (vs forced) approval
```

**Rule of thumb from the research:** on a 150-shot short film (total $114–$123 depending on
hosting), hosted-model spend is ~86% of the bill and hosting choice moves ~7.7%. **One cache hit
on a single premium 5-second clip ($1.50 for Sora 2 Pro) is worth more than the entire hosting
delta for two films.** Track 1 outranks everything.

---

## Do not do

- **Do not add a second execution backend before Track 2 lands.** A backend reachable through an
  `execute` override has no priceable `Plan`.
- **Do not build a second blob store.** `lacing.ArtifactStore` exists and is unwired.
- **Do not put a version in a backend or operation identifier.** Version belongs in a field that
  folds into the cache key, not in the id.
- **Do not let a key-composition function degrade quietly.** `json.dumps(..., default=str)` must
  raise, not stringify (see the cache-key issue).
- **Do not price an unknown as free.** `estimate_call_cost` already returns `None` correctly
  (`falaw/cost.py:59-107`) — keep it, and keep `has_unknown_costs` fail-closed.
- **Do not "fix" `plan_hash` by resolving `<from N>` placeholders.** It hashes with placeholders
  intact *on purpose*, so it stays stable across re-plans of the same structural request
  (`falaw/plan.py:288-317`). D2 is fixed in `make_call_plan`, not there.

---

## Provenance of this roadmap

Derived from the `video_gen` research programme (private `priv` repo):
`data/groups/video_gen/docs/reelee_comfyui_decisions_and_rationale.md` (decisions of record) and
briefs **B** (evaluation / incrementality / caching), **J** (extension and licence boundary),
**K** (ComfyUI execution semantics — the defect register), **M** (deployment and cost), **O**
(the facade spec and build order) under `data/groups/video_gen/docs/research/`.

Every claim above was re-verified against this repo's source on 2026-08-04 (v0.0.22, 210 tests
collected); where a research claim and the code disagreed, the code won and the issue says so.
