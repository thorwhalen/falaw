# falaw.pricing

Read fal’s pricing API into `models.json` cost estimates (falaw#18).

19 of the catalogue’s 40 models carry no structured `cost_estimate`, so
`Plan.has_unknown_costs` — correctly — forces approval on nearly every
plan. fal publishes the real numbers (`GET /v1/models/pricing`), and this
module turns them into catalogue entries with `source="api"`:

```pycon
>>> from falaw import refresh_model_prices
>>> summary = refresh_model_prices()          # dry-run: reports, writes nothing
>>> summary = refresh_model_prices(write=True)   # persists to models.json
```

Design rules, in order of importance:

- **This is a refresh job, not a runtime lookup.** `plan_*` never touches
  the network; plans price themselves from the committed catalogue.
- **An unmapped billing unit is recorded, never guessed.** fal’s `unit` is
  a free string (“image”, “megapixel”, GPU/compute units, …); only units with
  an unambiguous `CostKind` mapping become estimates. A
  GPU-second is machine time, not output time — mapping it to `per_second`
  would misprice by the model’s realtime factor, so it stays unpriced and
  visible in the summary instead.
- **The API wins, loudly.** A hand-written price the API disagrees with is
  overwritten, and the delta is reported — stale pricing data is the normal
  case, not the exception.

### Module Attributes

| [`PRICING_URL`](#falaw.pricing.PRICING_URL)         | fal's unit-pricing endpoint.                                       |
|----------------------------------------------------------------------|--------------------------------------------------------------------|
| [`MAX_IDS_PER_REQUEST`](#falaw.pricing.MAX_IDS_PER_REQUEST) | The endpoint's documented per-request cap on `endpoint_id` values. |
| [`MAX_429_RETRIES`](#falaw.pricing.MAX_429_RETRIES)     | Attempts per request before giving up on a rate-limited endpoint.  |

### Functions

| [`fetch_model_prices`](#falaw.pricing.fetch_model_prices)(endpoint_ids, \*[, ...])     | `{endpoint_id: {"unit_price", "unit", "currency"}}` from fal's API.   |
|--------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`refresh_model_prices`](#falaw.pricing.refresh_model_prices)(\*[, write, api_key, ...]) | Refresh `models.json` cost estimates from fal's pricing API.          |

### falaw.pricing.MAX_429_RETRIES *= 5*

Attempts per request before giving up on a rate-limited endpoint.

The bisection around unknown ids multiplies request count, and the live
endpoint rate-limits aggressively — a refresh job should wait its turn,
not die halfway with a partial price table.

### falaw.pricing.MAX_IDS_PER_REQUEST *= 50*

The endpoint’s documented per-request cap on `endpoint_id` values.

### falaw.pricing.PRICING_URL *= 'https://api.fal.ai/v1/models/pricing'*

fal’s unit-pricing endpoint. Accepts 1-50 `endpoint_id` values per call.

### falaw.pricing.fetch_model_prices(endpoint_ids, , api_key=None, http_get=None, batch_size=50)

`{endpoint_id: {"unit_price", "unit", "currency"}}` from fal’s API.

Batches requests at `batch_size` ids (the endpoint caps at
[`MAX_IDS_PER_REQUEST`](#falaw.pricing.MAX_IDS_PER_REQUEST)). Ids the API does not know are simply
absent from the result — the caller decides what absence means. That
takes work: the live endpoint answers a batch containing even one
unknown id with a blanket 404, so a failed batch is bisected down to
the ids that actually price (O(unknown x log batch) extra requests).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### falaw.pricing.refresh_model_prices(, write=False, api_key=None, http_get=None, models_path=None, today=None)

Refresh `models.json` cost estimates from fal’s pricing API.

Returns a summary dict; `write=False` (default) reports what would
change without touching the file. `models_path` and `today` exist
for tests (the fetch date lands in each estimate’s `notes`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
