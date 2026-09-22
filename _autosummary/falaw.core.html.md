# falaw.core

Wrapper over `fal_client.subscribe` with progress events and auto-journaling.

Operations should call `call_fal` rather than `fal_client.subscribe` directly,
so we get one place to:

* publish structured progress events to subscribers (UI, telemetry),
* auto-journal failures (so the next agent learns from them),
* layer retries / backoff later without changing call sites.

See [`falaw.events`](falaw.events.html.md#module-falaw.events) for the event model. `on_log` (a
string-only callback) still works for backward compatibility — when
both `on_log` and `on_event` are given, both fire.

### Functions

| [`call_fal`](#falaw.core.call_fal)(application, arguments, \*[, ...])   | Call a fal model via fal_client.subscribe.                                                                              |
|------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| [`current_fal_key`](#falaw.core.current_fal_key)()                             | The fal API key bound for the current context, or `None`.                                                               |
| [`using_fal_credentials`](#falaw.core.using_fal_credentials)(key)                    | Bind `key` as the fal credential for every [`call_fal()`](#falaw.core.call_fal) in this context. |

### falaw.core.call_fal(application, arguments, , on_log=None, on_event=None, with_logs=True, journal_errors=True, api_key=None)

Call a fal model via fal_client.subscribe.

* **Parameters:**
  * **application** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – fal model id (e.g. `"fal-ai/flux/dev"`).
  * **arguments** ([`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]) – Input arguments. Keys depend on the model.
  * **on_log** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]]) – Legacy log callback — receives raw log lines as strings.
    Defaults to no-op (use `on_event` for structured access).
  * **on_event** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`ProgressEvent`](falaw.events.html.md#falaw.events.ProgressEvent)], [`None`](https://docs.python.org/3/builtins/constants.html#None)]]) – Per-call subscriber for `ProgressEvent`s. Fires
    in addition to the global subscribers registered via
    :func:`falaw.events.subscribe`.
  * **with_logs** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Pass through to fal_client; when True the model streams logs.
  * **journal_errors** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – When True, exceptions are recorded as journal issues
    before being re-raised. The journal entry includes the application
    id and arguments so future agents can recognize the same trap.
  * **api_key** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Explicit fal key for this call. When `None` (default) the
    key bound via [`using_fal_credentials()`](#falaw.core.using_fal_credentials) is used; when that is
    also unset, the fal SDK’s own `FAL_KEY` env-var lookup applies
    (the historical behaviour). A resolved key is used per-call via a
    dedicated `fal_client.SyncClient` — it is never written to a
    global or an env var.
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
* **Returns:**
  The raw response dict from the model.

### falaw.core.current_fal_key()

The fal API key bound for the current context, or `None`.

Resolution order callers should mirror: an explicit `api_key` argument
to [`call_fal()`](#falaw.core.call_fal) wins over this context value, which in turn wins over
the fal SDK’s own `FAL_KEY` env-var lookup.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### falaw.core.using_fal_credentials(key)

Bind `key` as the fal credential for every [`call_fal()`](#falaw.core.call_fal) in this context.

Intended for server-side bring-your-own-key flows: wrap a unit of work
that will make one or more fal calls, and they all authenticate with
`key` instead of the server’s `FAL_KEY` env var — without any
intermediate function needing a credential parameter.

A falsy `key` is a deliberate no-op (the context is left untouched), so
a caller can pass an optional header value straight through without
special-casing “no BYO key — fall back to the server/env key”.

Thread/async safe: backed by a [`contextvars.ContextVar`](https://docs.python.org/3/library/contextvars.html#contextvars.ContextVar), so the
binding is visible only within the entering context (and threads/tasks it
spawns), never to concurrent requests.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`None`](https://docs.python.org/3/builtins/constants.html#None)]
