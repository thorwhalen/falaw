# falaw.canonical

One canonical byte-form for everything falaw hashes (falaw#17).

falaw derives money-bearing identities from JSON: the per-call cache key
(`falaw.cache._key()`), the whole-plan idempotency handle
([`falaw.plan.plan_hash()`](falaw.plan.md#falaw.plan.plan_hash)), and the dry-run artifact id
(`falaw.plan._synthetic_artifact`). Before this module each site called
`json.dumps(..., sort_keys=True, default=str)` — and `default=str` is a
**give-up-quietly branch inside a key-composition function**, which fails in
both directions at once:

* two structurally different values whose `str()` coincide collapse to one
  key — `Decimal("0.5")` vs `"0.5"`, `Path("/a/b")` vs `"/a/b"` — a
  silent *wrong hit*: the caller is handed someone else’s artifact and billed
  it as a saving;
* an object without a stable `str()` (the default `<Ref object at 0x...>`
  repr) mints a fresh key per instance — a *permanent miss* plus unbounded
  cache growth.

JSON’s silent key coercion has the same collision property from the other
side: `{1: "x"}` and `{"1": "x"}` dump to identical bytes, so two
different argument dicts share a key. (`lacing` rejects the same case in
its digests, for the same reason.)

The rule this module enforces: \*\*a key-composition function must never have a
“give up quietly” branch.\*\* [`canonical_blob()`](#falaw.canonical.canonical_blob) serializes with
`sort_keys=True`, **no** `default`, `allow_nan=False`, and string-only
mapping keys — anything else raises [`falaw.errors.FalNonCanonicalArgument`](falaw.errors.md#falaw.errors.FalNonCanonicalArgument)
naming the offending path and type, so the failure is a diagnosable refusal at
plan time rather than a wrong artifact at collect time.

Two payload projections live here **side by side, on purpose**:

* [`cache_key_payload()`](#falaw.canonical.cache_key_payload) — `{app, args}`, the per-call content-addressed
  cache key;
* [`plan_identity_payload()`](#falaw.canonical.plan_identity_payload) — `{app, args, tool}`, the structural
  idempotency form shared by `plan_hash` and the dry-run artifact id.

The field sets differ deliberately (`tool` is a falaw-side label; the
underlying fal call is the same whatever the tool was called), but a field
that changes *what the call produces* must go into **both** — in this module,
in one commit. `backend` (falaw#15’s `CallPlan.backend`) is exactly that
field: both projections accept it, and it lands in the hashed payload
whenever it is not [`DFLT_BACKEND`](#falaw.canonical.DFLT_BACKEND) — omitted, not merely equal, when it
is. Two consequences, both load-bearing:

* a backend added to `plan_hash` but not the cache key would let one
  backend return another backend’s artifact as a wrong hit — the reason the
  two projections take the parameter together rather than one growing it
  first;
* omitting the field for the default backend means every call falaw has ever
  planned or cached — all of them `"fal"` today — keeps its **exact**
  pre-#15 digest. A future non-default backend hashes under a genuinely
  different key (correctly — it *is* a different call), without silently
  invalidating the deployed fal cache the day this ships.

Byte-compatibility: for JSON-native payloads the output of
[`canonical_blob()`](#falaw.canonical.canonical_blob) is identical to the old form, so every cache entry
whose arguments were already JSON-native keeps its key. Invalidated —
deliberately, because their keys were unreliable or unportable — are entries
whose arguments needed any of JSON’s laxities: the `default=str`
stringification, a bare `NaN`/`Infinity` (previously serialized natively),
or silently-coerced non-string mapping keys. `tests/test_canonical.py` pins
the stability half with literal digests.

### Module Attributes

| [`DFLT_BACKEND`](#falaw.canonical.DFLT_BACKEND)   | The only execution backend falaw ships until a second one lands (falaw#15).   |
|-----------------------------------------------------------------|-------------------------------------------------------------------------------|

### Functions

| [`canonical_blob`](#falaw.canonical.canonical_blob)(payload)                        | The one byte-form falaw hashes: sorted keys, no fallback, no NaN.                         |
|-------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| [`ensure_canonical`](#falaw.canonical.ensure_canonical)(payload, \*[, context])       | Raise `FalNonCanonicalArgument` unless `payload` is canonical JSON.                       |
| [`cache_key_payload`](#falaw.canonical.cache_key_payload)(application, arguments, \*)  | `{app, args}` — what the per-call content-addressed cache keys on.                        |
| [`plan_identity_payload`](#falaw.canonical.plan_identity_payload)(application, ...[, ...]) | `{app, args, tool}` — the structural form behind `plan_hash` and the dry-run artifact id. |

### falaw.canonical.DFLT_BACKEND *= 'fal'*

The only execution backend falaw ships until a second one lands
(falaw#15). The single source for two defaults that must agree:
`CallPlan.backend`’s field default, and the value [`cache_key_payload()`](#falaw.canonical.cache_key_payload)
/ [`plan_identity_payload()`](#falaw.canonical.plan_identity_payload) omit from the hashed payload.

### falaw.canonical.cache_key_payload(application, arguments, , backend='fal', key_extra=None)

`{app, args}` — what the per-call content-addressed cache keys on.

No `tool`: two CallPlans differing only in falaw-side labelling make the
same fal call and *should* share a cache entry. `backend` joins the
payload only when it is not [`DFLT_BACKEND`](#falaw.canonical.DFLT_BACKEND) — see the module
docstring for why that asymmetry, not unconditional inclusion, is the
safe choice. A field that changes what the call **produces** must be
added here AND in [`plan_identity_payload()`](#falaw.canonical.plan_identity_payload).

`key_extra` joins under the same omit-if-empty rule: identity a caller
declares beyond the wire arguments (nw#27’s Transform `impl_version` is
the first customer — “same interface, changed behaviour” must miss the
cache without renaming anything). Empty means absent, so every key ever
issued without one is unchanged.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### falaw.canonical.canonical_blob(payload)

The one byte-form falaw hashes: sorted keys, no fallback, no NaN.

Raises `FalNonCanonicalArgument` for anything JSON cannot represent
faithfully — there is deliberately no `default=` escape hatch, because a
hashing function that guesses is a hashing function that collides.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### falaw.canonical.ensure_canonical(payload, , context='arguments')

Raise `FalNonCanonicalArgument` unless `payload` is canonical JSON.

Canonical means: `str` / `bool` / `int` / finite `float` / `None`
scalars, `list` / `tuple` sequences, and mappings with **string** keys,
recursively. Call this at a boundary (`make_call_plan`,
`cached_call_fal`) so the refusal happens while it is still free —
before any network call, not on the way to one.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### falaw.canonical.plan_identity_payload(application, arguments, , tool, backend='fal', key_extra=None)

`{app, args, tool}` — the structural form behind `plan_hash` and
the dry-run artifact id.

Includes `tool` so a re-plan of the same request is recognizable as the
same *plan* even though the cache would treat the calls identically.
`backend` and `key_extra` join the payload under the same
omit-if-default rule as [`cache_key_payload()`](#falaw.canonical.cache_key_payload); keep the two functions
adjacent so adding a field to one is an explicit decision about the other.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
