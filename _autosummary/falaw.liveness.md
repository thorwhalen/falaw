# falaw.liveness

Is a catalogued endpoint still deployed? (falaw#76)

fal retires endpoints without notice (`fal-ai/imagen4/preview/ultra` answers
`404 Application "imagen4" not found`), and `pick_model` would keep
picking them. fal’s OpenAPI endpoint answers 404 for a dead id and 200 for a
live one without a billed call or an API key, so one GET per id is a free
liveness probe.

### Module Attributes

| [`OPENAPI_URL`](#falaw.liveness.OPENAPI_URL)   | `?endpoint_id=<id>` selects the endpoint.                          |
|----------------------------------------------------------------|--------------------------------------------------------------------|
| [`StatusGetter`](#falaw.liveness.StatusGetter)  | `url -> HTTP status`; injectable so tests never touch the network. |

### Functions

| [`check_model_liveness`](#falaw.liveness.check_model_liveness)([ids, status_of])   | `{endpoint_id: is_live}` for `ids` (default: every catalogued model).                                             |
|-------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| [`dead_models`](#falaw.liveness.dead_models)([ids, status_of])            | The ids from [`check_model_liveness()`](#falaw.liveness.check_model_liveness) that are no longer deployed. |

### falaw.liveness.OPENAPI_URL *= 'https://fal.ai/api/openapi/queue/openapi.json'*

`?endpoint_id=<id>` selects the endpoint.

### falaw.liveness.StatusGetter

`url -> HTTP status`; injectable so tests never touch the network.

alias of `Callable`[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`int`](https://docs.python.org/3/builtins/functions.html#int)]

### falaw.liveness.check_model_liveness(ids=None, , status_of=None)

`{endpoint_id: is_live}` for `ids` (default: every catalogued model).

Only a 404 means dead; any other non-200 answer (rate limit, fal outage)
raises rather than report a live model as dead, which would get it deleted.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`bool`](https://docs.python.org/3/builtins/functions.html#bool)]

### falaw.liveness.dead_models(ids=None, , status_of=None)

The ids from [`check_model_liveness()`](#falaw.liveness.check_model_liveness) that are no longer deployed.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
