> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Retries and Error Handling

> How fal retries failed requests, what each status code does to runners, and how to control behavior with response headers.

When a request fails while being processed through the [queue](/docs/documentation/model-apis/inference/queue), fal automatically retries it on a new runner. This covers infrastructure-level failures like runner crashes, network issues, and timeouts. Retries happen transparently, up to 10 attempts, before the request is marked as failed. Direct calls via `run()` and `stream()` (without the queue) are never retried.

The status code your endpoint returns determines whether the runner stays alive, whether the request is retried, and how the platform reacts. Returning the wrong code can kill a healthy runner or prevent a retry that should happen. When a request does fail, the response includes an `error_type` field and `X-Fal-Error-Type` header with a machine-readable category (e.g. `request_timeout`, `runner_disconnected`) that you can use for programmatic retry logic and monitoring. See [Request Error Types](/docs/documentation/model-apis/request-errors) for the full reference.

This page is the complete reference for understanding failures on fal: what triggers retries, what each status code does, how timeouts interact, and how to override default behavior with response headers. For a broader view of how retries fit into the request lifecycle, see [Understanding Requests](/docs/documentation/deployment/requests).

## Status Code Reference

The status code your endpoint returns determines what happens to the [runner](/docs/documentation/deployment/runners) and whether queue-based requests are retried.

| Status Code | Runner Impact              | Retried (queue only) |
| ----------- | -------------------------- | -------------------- |
| **2XX**     | Healthy                    | N/A                  |
| **3XX**     | Healthy                    | No                   |
| **4XX**     | Healthy                    | No                   |
| **500**     | TCP health check triggered | No                   |
| **502**     | TCP health check triggered | No                   |
| **503**     | Immediately terminated     | Yes                  |
| **504**     | TCP health check triggered | Yes                  |

**2XX and 4XX** -- The runner remains healthy and continues serving requests. 4XX responses are treated as client errors and are never retried.

**3XX** -- The redirect is returned to the caller verbatim, including the `Location` header. fal does not follow redirects that your app returns, so the caller is the one that decides whether to follow it, using its own credentials. The runner stays healthy and the request is not retried. If your endpoint redirects to a result file, the caller has to fetch that URL itself.

**500 and 502** -- The platform runs a TCP health check on the runner. If the check passes, the runner stays alive and continues serving requests. If it fails, the runner is terminated and replaced. The request is not automatically retried.

**503** -- The runner is immediately terminated after a single 503 response. Queue-based requests are automatically retried on a new runner (up to 10 times). Use this only when the runner is genuinely broken (e.g., GPU OOM, corrupted state).

**504** -- The platform runs a TCP health check and automatically requeues the request for retry. The runner is not immediately terminated but may be replaced if the health check fails.

<Warning>
  **Never return 503 for normal application errors.** A single 503 immediately kills your runner. Use 500 for application-level errors where the runner is still functional.
</Warning>

### Which Status Code to Use

| Situation                                     | Recommended Code   | Why                                          |
| --------------------------------------------- | ------------------ | -------------------------------------------- |
| Bad user input, validation failure            | **422** or **400** | Client error, runner stays healthy           |
| Model inference failed but runner is fine     | **500**            | Health check runs, runner likely survives    |
| External API or dependency timed out          | **504**            | Request retried, runner not killed           |
| GPU OOM, corrupted model state, runner broken | **503**            | Runner terminated and replaced               |
| Rate limiting the caller                      | **429**            | Client error, runner stays healthy, no retry |

```python theme={null}
import fal
from fastapi.responses import JSONResponse


class MyApp(fal.App):
    @fal.endpoint("/")
    def predict(self, input: dict) -> dict:
        try:
            result = self.model.run(input)
            return result
        except ValueError as e:
            return JSONResponse(
                status_code=422,
                content={"detail": str(e)},
            )
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                return JSONResponse(
                    status_code=503,
                    content={"detail": "GPU out of memory"},
                )
            return JSONResponse(
                status_code=500,
                content={"detail": "Inference failed"},
            )
```

### Connection Errors and Timeouts

Beyond status codes, two additional scenarios affect runner lifecycle:

| Scenario                            | What happens      | Queue requests        | Direct requests |
| ----------------------------------- | ----------------- | --------------------- | --------------- |
| **App crashes** (connection breaks) | Runner terminated | Retried on new runner | Returns 503     |
| **Request timeout** exceeded        | Runner terminated | Retried on new runner | Returns 504     |

In both cases the runner is shut down because it may be in a faulty state. The platform spins up a replacement.

## When Retries Happen

fal retries queue-based requests under three conditions. Each corresponds to a value you can use in `skip_retry_conditions` to disable it.

| Condition            | Value                | What triggers it                                                                                                                      | Runner impact                                        |
| -------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **Server error**     | `"server_error"`     | Runner returned HTTP 503, runner disconnected, runner sent an incomplete response, or runner returned HTTP 504                        | 503: runner terminated. 504: health check triggered. |
| **Timeout**          | `"timeout"`          | Request exceeded the app's [request\_timeout](/docs/documentation/deployment/scale-your-application) and the gateway killed the connection | Runner terminated                                    |
| **Connection error** | `"connection_error"` | The HTTP session between the gateway and the runner was unexpectedly closed                                                           | Runner terminated                                    |

Each condition maps to a different failure mode. Server errors indicate the runner is in a bad state. Timeouts indicate the request took too long. Connection errors indicate a network-level failure between the gateway and the runner.

## Controlling Retry Behavior

### App-Level: skip\_retry\_conditions

Configure your app to skip retries for specific conditions. Pass one or more of the condition values from the table above.

```python theme={null}
class MyApp(fal.App):
    skip_retry_conditions = ["timeout"]
```

This is useful when your model has long-running requests that exceed `request_timeout` for legitimate reasons. Without this setting, fal would retry the request on a new runner, which wastes compute and delays the final failure response.

You can combine multiple conditions:

```python theme={null}
class MyApp(fal.App):
    skip_retry_conditions = ["timeout", "server_error"]
```

### App-Level: retry\_config

Set a default retry budget per [retry condition](#when-retries-happen) for all queue-based requests to your app. The format is the same as the [`X-Fal-Retry-Config` header](#per-request-client-side-control): a mapping from condition (`server_error`, `timeout`, or `connection_error`) to an object with a `retries` count.

```python theme={null}
class MyApp(fal.App):
    retry_config = {
        "timeout": {"retries": 0},
        "server_error": {"retries": 3},
    }
```

Or in `pyproject.toml` when [deploying from a config file](/docs/api-reference/python-sdk/pyproject-toml):

```toml theme={null}
[tool.fal.apps.my-app]
retry_config = { timeout = { retries = 0 }, server_error = { retries = 3 } }
```

The config is applied per retry decision with this precedence:

1. Per-request `X-Fal-Retry-Config` header -- the app owner can override the app default for a single request (on shared apps, the header is honored only for the owner, not other callers)
2. App-level `retry_config` set at deploy time
3. Platform default

The same semantics as the header apply: `retries` counts additional attempts after the first, each condition has an independent budget, an omitted condition falls back to the platform default, and the overall ceiling of 10 total attempts is always enforced. Only the `{"retries": N}` object form is accepted per condition -- shorthand like `"server_error": 3` is ignored.

### Per-Response: X-Fal-Needs-Retry

Override the default retry behavior on a per-response basis by returning the `X-Fal-Needs-Retry` header from your endpoint. The header is honored only on the statuses fal already treats as retryable, which are **5XX and 429**. On those, it takes precedence over both the status-code-based retry logic and `skip_retry_conditions`.

| Header Value | Behavior                                                                                                                    |
| ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `1`          | Force a retry of a 5XX or 429 response, even when the status code or `skip_retry_conditions` would not normally trigger one |
| `0`          | Prevent a retry of a 5XX or 429 response, even if the status code would normally trigger one                                |

<Warning>
  On any other status, including 2XX, 3XX, and 4XX, fal strips this header and ignores it. Returning `X-Fal-Needs-Retry: 1` with a 200 or a custom 4XX does not retry the request, and you get no error to tell you it was dropped. To ask for a retry, return a 5XX status, such as the 500 in the example below.
</Warning>

```python theme={null}
import fal
from fastapi.responses import JSONResponse


class MyApp(fal.App):
    @fal.endpoint("/")
    def run(self, input: Input) -> Output:
        try:
            result = self.model.run(input)
            return result
        except TransientError:
            return JSONResponse(
                status_code=500,
                headers={"X-Fal-Needs-Retry": "1"},
                content={"detail": "Transient error, please retry"},
            )
        except NonRetryableError:
            return JSONResponse(
                status_code=503,
                headers={"X-Fal-Needs-Retry": "0"},
                content={"detail": "Non-retryable error"},
            )
```

### Per-Response: x-fal-stop-runner

Control whether the runner is terminated after a response, independent of the status code. This header is stripped from the response before it reaches the caller.

| Header Value  | Behavior                                                                               |
| ------------- | -------------------------------------------------------------------------------------- |
| `1` / `true`  | Force runner termination (same effect as a 503, but works with any status code)        |
| `0` / `false` | Prevent runner termination (allows returning 503 for retry without killing the runner) |

Use this when you want to decouple retry behavior from runner termination. For example, you might want to trigger a retry (`X-Fal-Needs-Retry: 1`) but keep the runner alive (`x-fal-stop-runner: false`), or terminate a runner (`x-fal-stop-runner: true`) without triggering a retry (`X-Fal-Needs-Retry: 0`).

```python theme={null}
from fastapi.responses import JSONResponse


@fal.endpoint("/")
def predict(self, input: dict) -> dict:
    try:
        return self.model.run(input)
    except CorruptedStateError:
        return JSONResponse(
            status_code=500,
            headers={
                "x-fal-stop-runner": "true",
                "X-Fal-Needs-Retry": "1",
            },
            content={"detail": "Runner state corrupted, retrying on fresh runner"},
        )
```

### Per-Request: Client-Side Control

When calling your app (or any model) from client code, you can control retry behavior per-request using headers.

Pass the `x-fal-no-retry` header to prevent fal from retrying a specific request:

<Tabs>
  <Tab title="Python">
    ```python theme={null}
    import fal_client

    result = fal_client.subscribe(
        "your-username/your-app-name",
        arguments={"prompt": "a sunset"},
        headers={"x-fal-no-retry": "1"},
    )
    ```
  </Tab>

  <Tab title="JavaScript">
    ```javascript theme={null}
    import { fal } from "@fal-ai/client";

    const result = await fal.subscribe("your-username/your-app-name", {
      input: { prompt: "a sunset" },
      headers: { "x-fal-no-retry": "1" },
    });
    ```
  </Tab>
</Tabs>

For finer control, pass `X-Fal-Retry-Config` to set a **separate retry limit for each retry condition** instead of an all-or-nothing switch -- for example, to retry transient server errors a few times but never retry timeouts. The value is a JSON object that maps a [retry condition](#when-retries-happen) (`server_error`, `timeout`, or `connection_error`) to an object with a `retries` count:

<Tabs>
  <Tab title="Python">
    ```python theme={null}
    import json
    import fal_client

    result = fal_client.subscribe(
        "your-username/your-app-name",
        arguments={"prompt": "a sunset"},
        headers={
            "X-Fal-Retry-Config": json.dumps(
                {"timeout": {"retries": 0}, "server_error": {"retries": 3}}
            )
        },
    )
    ```
  </Tab>

  <Tab title="JavaScript">
    ```javascript theme={null}
    const result = await fal.subscribe("your-username/your-app-name", {
      input: { prompt: "a sunset" },
      headers: {
        "X-Fal-Retry-Config": JSON.stringify({
          timeout: { retries: 0 },
          server_error: { retries: 3 },
        }),
      },
    });
    ```
  </Tab>
</Tabs>

`retries` is the number of **additional** attempts after the first, so `retries: 3` allows up to 4 total attempts for that condition:

| Value             | Behavior                                            |
| ----------------- | --------------------------------------------------- |
| `{"retries": 0}`  | No retries for that condition (1 attempt only)      |
| `{"retries": N}`  | Up to N retries for that condition (N + 1 attempts) |
| condition omitted | Use the platform default                            |

Key behaviors:

* **This header only works on your apps.** On shared or public model APIs that you do not own, it is ignored.
* **This header overrides the app-level [`retry_config`](#app-level-retry_config)** for the request it is sent with.
* **Each condition has its own independent budget.** Exhausting the `timeout` budget does not consume retries reserved for `server_error`, and vice versa.
* **The platform's overall ceiling of 10 total attempts still applies.** A request is never tried more than 10 times in total, even if a condition's `retries` is set higher.
* **`x-fal-no-retry` takes precedence.** If both headers are present, `x-fal-no-retry` wins and all retries are disabled, regardless of this config.
* **Invalid JSON or unrecognized condition names are ignored silently** -- the request falls back to default retry behavior.

For supported models, fal may route failed requests to equivalent fallback endpoints. To disable this per-request, pass `x-app-fal-disable-fallback`:

<Tabs>
  <Tab title="Python">
    ```python theme={null}
    result = fal_client.subscribe(
        "your-username/your-app-name",
        arguments={"prompt": "a sunset"},
        headers={"x-app-fal-disable-fallback": "1"},
    )
    ```
  </Tab>

  <Tab title="JavaScript">
    ```javascript theme={null}
    const result = await fal.subscribe("your-username/your-app-name", {
      input: { prompt: "a sunset" },
      headers: { "x-app-fal-disable-fallback": "1" },
    });
    ```
  </Tab>
</Tabs>

## Timeouts and Retries

fal has four timeout mechanisms, each operating at a different stage of the request lifecycle. They interact with retries differently.

The **app-level `request_timeout`** controls how long a single request can execute on a runner. If your endpoint handler exceeds this limit, the gateway kills the connection, terminates the runner, and retries the request (unless you set `skip_retry_conditions = ["timeout"]`).

```python theme={null}
class MyApp(fal.App):
    request_timeout = 600  # 10 minutes per request
```

The **app-level `startup_timeout`** controls how long a new runner has to complete `setup()` and open its HTTP port. If setup takes longer, the runner is terminated and replaced. This is not a retry condition because the request has not started processing yet. The request stays in the queue and waits for a healthy runner.

```python theme={null}
class MyApp(fal.App):
    startup_timeout = 600  # 10 minutes for setup
```

The **caller-level `start_timeout`** (sent as `X-Fal-Request-Timeout`) is set by the caller and defines an absolute wall-clock deadline for the request. The server checks this deadline before processing begins -- if it has passed, fal returns a 504 with no retry and the runner is not terminated. Once a runner begins processing, the deadline is not enforced and the request runs to completion. However, if processing fails and triggers a retry, all elapsed time (including the failed attempt) counts against the same original deadline.

```python theme={null}
result = fal_client.subscribe(
    "fal-ai/nano-banana-2",
    arguments={"prompt": "a sunset"},
    start_timeout=30,
)
```

The **client-level `client_timeout`** (Python SDK only) is enforced entirely on the client side. The client stops polling and raises an exception locally. The request may still be processing on the server.

```python theme={null}
result = fal_client.subscribe(
    "fal-ai/nano-banana-2",
    arguments={"prompt": "a sunset"},
    client_timeout=60,
)
```

| Timeout                                   | Set by               | When it applies                                            | Retries                      | Runner impact           |
| ----------------------------------------- | -------------------- | ---------------------------------------------------------- | ---------------------------- | ----------------------- |
| `request_timeout`                         | App developer        | During request processing                                  | Yes (condition: `"timeout"`) | Terminated              |
| `startup_timeout`                         | App developer        | During runner startup / `setup()`                          | No (request stays queued)    | Terminated and replaced |
| `start_timeout` / `X-Fal-Request-Timeout` | Caller (server-side) | Entire request lifecycle (enforced before processing only) | Never                        | Not affected            |
| `client_timeout`                          | Caller (client-side) | Total time client waits                                    | N/A (client stops polling)   | Not affected            |

See [Scale Your Application](/docs/documentation/deployment/scale-your-application) for configuring `request_timeout` and `startup_timeout`. The caller-level parameters are documented on the [Async Inference](/docs/documentation/model-apis/inference/queue#submit-parameters) page.

## Request Error Types

When a request fails, the response body includes a `detail` string and an `error_type` field identifying the failure category. The same value is available in the `X-Fal-Error-Type` response header.

```json theme={null}
{
  "detail": "Request timed out",
  "error_type": "request_timeout"
}
```

Use `error_type` to build programmatic retry logic and monitor failure patterns. Runner and timeout errors are typically transient and worth retrying. Client errors (`client_disconnected`, `bad_request`) should not be retried.

| Error Type                   | Description                                                    | Typical Status Code |
| :--------------------------- | :------------------------------------------------------------- | :------------------ |
| `request_timeout`            | The request exceeded the allowed processing time.              | 504                 |
| `startup_timeout`            | The runner did not start within the allowed time.              | 504                 |
| `runner_scheduling_failure`  | No runner could be allocated to handle the request.            | 503                 |
| `runner_connection_timeout`  | The connection to the runner timed out.                        | 503                 |
| `runner_disconnected`        | The runner disconnected unexpectedly during processing.        | 503                 |
| `runner_connection_refused`  | The runner refused the connection.                             | 503                 |
| `runner_connection_error`    | A general connection error occurred with the runner.           | 503                 |
| `runner_incomplete_response` | The runner sent an incomplete response payload.                | 502                 |
| `runner_server_error`        | The runner encountered an internal server error.               | 500                 |
| `client_disconnected`        | The client closed the connection before the response was sent. | 499                 |
| `client_cancelled`           | The request was cancelled by the client.                       | 499                 |
| `bad_request`                | The request was malformed (e.g., invalid timeout header).      | 400                 |
| `internal_error`             | An unexpected internal error occurred.                         | 500                 |

<Note>
  This error format is different from [model validation errors](/docs/documentation/model-apis/errors), which return a `detail` array of typed error objects. Request errors return a flat object with `detail` as a string.
</Note>
