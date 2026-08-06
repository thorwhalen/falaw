# falaw

Agent-friendly Python facade over fal.ai for generating and managing AI media (images, video, audio).

```python
from falaw import generate_image, list_models, journal

r = generate_image("a tiger eye, macro, 35mm", quality="fast")
r.first.download(to="./tiger.png")

[m.id for m in list_models(category="video")]
journal.note("schnell at quality='fast' defaults to 1024x1024")
```

## Why

`fal-client` already gives you 100+ models behind a uniform call. What
agents (and humans) still struggle with is *which* model to use, *what*
parameters it takes, and *what to do with* the URL it returns. `falaw`
adds:

- Task-level verbs (`generate_image`, `text_to_speech`, ...) with smart model selection by quality tier.
- A queryable model registry --- no more grepping docs for IDs.
- `Result` / `Asset` objects that download, name, and organize outputs.
- A journal so each session leaves notes for the next one.
- A Claude skill, plus stub bridges for MCP and HTTP services --- all derived from the same tool registry.

## Install

```bash
pip install -e .
export FAL_KEY="your-fal-api-key"
```

## Core surface

| Function | Purpose |
| --- | --- |
| `generate_image(prompt, *, quality, image_size, model_id, extra)` | Text-to-image, picks FLUX by quality tier. |
| `text_to_speech(text, *, quality, voice, model_id, extra)` | TTS, picks a voice model by tier. |
| `list_models(*, category, quality_tier)` | Browse the catalog. |
| `pick_model(*, category, quality_tier)` | Pick a sensible default. |
| `call_fal(application, arguments, *, on_event)` | Escape hatch to any fal model. Emits `ProgressEvent`s + auto-journals on error. |
| `cached_call_fal(...)` | Same, plus content-addressed cache; emits `cache_hit` events on reuse. |
| `execute_plan(plan, *, concurrency=N)` | Run a `Plan` → `list[Artifact]`. Raises on the first failure, unwrapped. |
| `execute_plan_isolated(plan, *, concurrency=N)` | Run a `Plan` → `ExecutionReport`: one outcome per call, so one bad call does not discard the rest. |
| `plan_dependencies(plan)` | The Plan's `"<from N>"` dependency DAG, and its structural validator. |
| `render_scene(scene, *, concurrency=N)` / `iter_render_scene(...)` | Render every shot+beat; thread-pooled, with yield-as-done iterator. |
| `estimate_scene_cost(scene)` | Walk a Scene, return a `CostRollup` with per-line USD breakdown. |
| `subscribe(callback)` | Attach a global subscriber to the `ProgressEvent` bus. |
| `journal.note / issue / improvement(...)` | Leave a trace for future sessions. |
| `Session(output_dir=...)` | Optional stateful controller. |

### Structured progress events

`call_fal` and `cached_call_fal` emit `ProgressEvent`s at every
lifecycle transition (`queued`, `progress`, `log`, `done`, `error`,
`cache_hit`). Subscribe per-call (`on_event=`) or globally
(`falaw.subscribe(...)`); the legacy `on_log=print` is still honored
for backward compatibility.

```python
from falaw import subscribe, generate_image

subscribe(lambda ev: print(f"[{ev.kind}] {ev.application} {ev.elapsed_s:.2f}s"))
generate_image("a tiger eye", quality="fast")
```

### Cost estimation

`ModelRecord.cost_estimate: CostEstimate | None` carries a structured
`{kind, amount, currency}` price (kinds: `per_call | per_image |
per_second | per_token | per_megapixel`). `estimate_scene_cost(scene)`
sums per-call costs and returns a `CostRollup` with per-line
breakdown. Models without a populated `cost_estimate` appear in the
rollup's `skipped` list so audits surface drift.

### Fan-out: partial results, bounded concurrency, per-call isolation

A `Plan` is a fan-out — 200 panels is 200 `CallPlan`s in one Plan — so
`execute_plan`'s `list[Artifact]` has no room to say *"call 7 failed, here are
the other 199"*. `execute_plan_isolated` does:

```python
from falaw import execute_plan_isolated

report = execute_plan_isolated(plan, concurrency=8)

for outcome in report.outcomes:          # always one per call, in plan order
    if outcome.ok:
        save(outcome.artifact)
    elif outcome.status == "failed":
        retry_later(outcome.call, outcome.error)   # retry this call verbatim
    else:
        replan(outcome.call, outcome.reason)       # blocked: its input does not exist

report.estimated_spend_usd, report.has_unknown_costs, report.cache_hit_savings_usd
```

Three states, not two. **Failed** means the call raised and can be retried as
it is. **Blocked** means it never ran — a `"<from N>"` placeholder whose
producer did not succeed — so it has to be re-planned, not retried. A caller
that cannot tell them apart retries a call whose input does not exist.

`concurrency` bounds how many calls are in flight; independent calls run in
parallel, and a call is never started beside the producer it consumes. It
defaults to `1` (sequential) everywhere, here and in `render_scene`, because
every call is a paid request: parallelism is opt-in. Weigh the vendor's rate
limit and memory — materializing a media result peaks at roughly twice the
asset's size, and `concurrency` multiplies that.

`execute_plan` keeps the plain `list[Artifact]` contract and re-raises the
first failure **unwrapped**, so falaw's typed error hierarchy still reaches the
caller. It is `execute_plan_isolated(...).artifacts_or_raise()` — one engine,
two policies.

`render_scene(..., concurrency=4)` runs shots and beats in parallel through the
same kind of thread pool (fal calls are HTTP-bound). Use
`iter_render_scene(...)` to yield `(kind, result)` pairs as each unit completes
— handy for live UI updates.

## Architecture

Single source of truth: a `ToolSpec` dataclass per tool. From it we derive every external surface:

```
falaw.registry  ──► bridges/skill.py    ──►  .claude/skills/falaw/SKILL.md
                ──► bridges/mcp.py      ──►  MCP server          (planned)
                ──► bridges/service.py  ──►  qh HTTP service     (planned)
                ──► (UI)                                          (planned)
```

Adding a new surface is a new bridge module, never a re-implementation of the operations.

## Self-improvement loop

Every session can read and write the agent journal at `~/.config/falaw/journal/`. The Claude skill instructs Claude to:

1. Read recent entries before novel work.
2. Write a note / issue / improvement when something surprises it.

`call_fal` auto-journals failures with the application id and arguments, so the next session recognizes the trap.

## Layout

```
falaw/
  base.py            ToolSpec, ModelRecord
  core.py            call_fal: subscribe + auto-journal
  registry.py        register_tool, list/get/pick model
  results.py         Asset, Result, parse_response
  session.py         Session
  journal.py         file-backed journal
  operations/
    images.py        generate_image
    audio.py         text_to_speech
  bridges/
    skill.py         render Claude SKILL.md from registry
    mcp.py           (stub)
    service.py       (stub)
  data/
    models.json      seed catalog
    skills/falaw/    generated skill files (shipped with package)
misc/
  docs/              aggregated fal.ai docs (3MB md, llms.txt, llms-full.txt)
  regenerate_skill.py
tests/
```

## Regenerate the skill after adding a tool

```bash
python misc/regenerate_skill.py
```

Writes `falaw/data/skills/falaw/SKILL.md` and `.claude/skills/falaw/SKILL.md`.

## Status

v0 --- functional core, real Claude skill, stubs for MCP and HTTP service. The bridges share the same registry, so filling in the stubs is additive.

## Roadmap

See [`misc/docs/roadmap.md`](misc/docs/roadmap.md) for the ordered work and the standing
constraints. In short, four tracks:

1. **Content addressing** --- *landed* (falaw#14). `Artifact.asset_id` is the SHA-256 of the
   artifact's bytes and the per-call cache key holds upstream *content* hashes, not fal CDN URLs.
   fal states that every upload gets a unique URL and that expired files are permanently deleted,
   so URL-keying meant a byte-identical regeneration missed the cache and a stored response decayed
   into a dead link. Bytes now route through `lacing.ArtifactStore.put_blob_stream`. Still open:
   the plan-time cache peek keys on *unresolved* arguments (D2), which lands with track 2.
2. **Backend-parametric `Plan`** --- `CallPlan.backend` + registry dispatch in `execute_plan`, so
   a second execution backend is still priced, cached and dry-runnable.
3. **Licence-and-terms ledger** --- per `(model, backend)`, queried at plan time, `unknown` means
   refuse.
4. **Cost data from the vendor** --- read fal's pricing API instead of hand-maintaining
   `data/models.json` (19 of 40 records currently carry no structured price at all).
