# falaw.results

Result wrapper: parse fal responses into typed assets, lazy download.

### Functions

| [`parse_response`](#falaw.results.parse_response)(raw, \*, application, arguments)   | Best-effort parser over the common fal response shapes.   |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------|

### Classes

| [`Asset`](#falaw.results.Asset)(url, kind[, content_type, width, ...])   | A single piece of generated media.                                  |
|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`Result`](#falaw.results.Result)([assets, raw, application, arguments])  | A fal call result with parsed assets and the original raw response. |

### *class* falaw.results.Asset(url, kind, content_type='', width=0, height=0, duration_s=0.0, metadata=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A single piece of generated media.

Holds the URL plus minimal typed metadata. `download` materializes it.

#### download(, to=None)

Download the asset to a file. Returns the local path.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### *class* falaw.results.Result(assets=<factory>, raw=<factory>, application='', arguments=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A fal call result with parsed assets and the original raw response.

The raw response is kept so callers can inspect provider-specific fields
(timings, seed, has_nsfw_concepts, …) that we do not normalize.

### falaw.results.parse_response(raw, , application, arguments)

Best-effort parser over the common fal response shapes.

fal models return a variety of layouts (lists, single objects, bare URLs).
We normalize each into Asset(url, kind, …). Unknown shapes pass through
as `raw` only — callers can read `result.raw` for anything we miss.

* **Return type:**
  [`Result`](#falaw.results.Result)
