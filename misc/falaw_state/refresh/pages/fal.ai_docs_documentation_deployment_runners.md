> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Understanding Runners

> What runners are, how they start, process requests, scale, and shut down.

A runner is a compute instance of your application running on fal's infrastructure. When you [deploy](/docs/documentation/deployment/deploy-to-production) an app, fal creates runners on demand to handle incoming requests. Each runner is tied to a specific [machine type](/docs/documentation/deployment/machine-types) that determines its hardware resources (CPU cores, RAM, GPU type and count). Runners automatically start when requests arrive and shut down when idle, so you only pay for compute you actually use.

Understanding the runner lifecycle is essential for making good decisions about [scaling](/docs/documentation/deployment/scale-your-application), [cold start optimization](/docs/documentation/serverless/optimizations/optimize-cold-starts), and [cost management](/docs/documentation/serverless/optimizations/optimizing-costs). Every scaling parameter, every caching strategy, and every startup optimization ultimately affects how runners behave. This page covers what happens from the moment a runner is scheduled to the moment it shuts down. For how requests flow through the queue and interact with runners, see [Understanding Requests](/docs/documentation/deployment/requests).

## Runner Lifecycle and States

Runners transition through a sequence of states during their lifetime. The startup flow determines your cold start latency, and the shutdown flow determines how gracefully your app handles scale-down events.

<div className="max-w-2xl mx-auto">
  ```mermaid theme={null}
  stateDiagram-v2
      [*] --> PENDING
      PENDING --> DOCKER_PULL: Image not cached
      PENDING --> SETUP: Image cached
      DOCKER_PULL --> SETUP
      SETUP --> IDLE
      CRASH_BACKOFF --> PENDING: Retry
      IDLE --> RUNNING: Request arrives
      RUNNING --> IDLE: Request completes
      RUNNING --> DRAINING: Has in-flight requests
      IDLE --> DRAINING: Has in-flight requests
      IDLE --> TERMINATING: No in-flight requests
      RUNNING --> TERMINATING: No in-flight requests
      IDLE --> TERMINATED: keep_alive expires
      DRAINING --> TERMINATING
      TERMINATING --> TERMINATED
      TERMINATED --> [*]
  ```
</div>

| State              | Description                                                                                                    |
| :----------------- | :------------------------------------------------------------------------------------------------------------- |
| **PENDING**        | Runner is waiting to be scheduled on available hardware                                                        |
| **DOCKER\_PULL**   | Pulling Docker image from registry (skipped when image is [cached](/docs/documentation/deployment/caching))         |
| **SETUP**          | Running [`setup()`](/docs/documentation/development/app-lifecycle) method, loading model and initializing resources |
| **CRASH\_BACKOFF** | Previous runner startup failed; delaying this runner's start before retrying                                   |
| **IDLE**           | Ready and waiting for work, no active requests                                                                 |
| **RUNNING**        | Actively processing one or more [requests](/docs/documentation/deployment/requests)                                 |
| **DRAINING**       | Finishing current requests, won't accept new ones                                                              |
| **TERMINATING**    | Shutting down, running [`teardown()`](/docs/documentation/development/app-lifecycle) if defined                     |
| **TERMINATED**     | Runner has stopped and resources are released                                                                  |

### Startup

When demand increases, fal schedules a new runner. If the runner's Docker image isn't already [cached](/docs/documentation/deployment/caching), it's pulled first (DOCKER\_PULL). Then your [`setup()`](/docs/documentation/development/app-lifecycle) method runs to load models and initialize resources. Once setup completes and the health check passes, the runner enters IDLE and is ready to serve requests. The time from PENDING to IDLE is your cold start latency.

### Startup Failure

If a runner crashes during startup or `setup()` times out, the runner is terminated. To prevent a tight crash loop, the system applies an incremental backoff to all subsequent runner starts for the same app. When a new runner is about to start and previous runners have failed, it enters `CRASH_BACKOFF` -- a holding state where the runner waits before attempting allocation.

The backoff works as follows:

* Each subsequent runner start is delayed by an additional 30 seconds (e.g. 30s, 60s, 90s)
* The delay is capped at 10 minutes
* If any runner succeeds during the delay, all waiting runners are woken up immediately and the backoff resets
* Scheduling failures (when hardware isn't available) also trigger a delay, but use a fixed 20-second wait instead of incremental backoff

After the delay, the runner transitions back to `PENDING` and retries the full startup flow.

When you see runners in `CRASH_BACKOFF`, check your `setup()` method and runner logs for errors. Common causes include missing model files, out-of-memory errors during model loading, and dependency issues.

### Request Processing

When a request arrives, an IDLE runner transitions to RUNNING. After completing all requests, it returns to IDLE. Runners can handle multiple concurrent requests if [`max_multiplexing`](/docs/documentation/deployment/scale-your-application) is set above 1.

### Shutdown

Runners shut down through different paths depending on their state:

* **[`keep_alive`](/docs/documentation/deployment/scale-your-application) expiration:** An idle runner with no in-flight requests is terminated directly. The system sends SIGTERM, runs your [`teardown()` method](/docs/documentation/development/app-lifecycle) for cleanup, and then releases resources.
* **Scale-down with in-flight requests:** The runner enters DRAINING. No new requests are routed, but existing requests continue processing. After requests complete, the runner enters TERMINATING, runs `teardown()`, and is terminated.
* **Scale-down with no in-flight requests:** The runner skips DRAINING and enters TERMINATING immediately.
* **Manual stop/kill:** You can terminate runners manually using [`fal runners stop`](/docs/api-reference/cli/runners#stop) or [`fal runners kill`](/docs/api-reference/cli/runners#kill), or from the dashboard.
* **Host maintenance:** The runner may be terminated if the underlying host is being drained due to a maintenance event (GPU errors, networking issues, or scheduled infrastructure updates).

For details on startup and shutdown hooks (`setup()`, `handle_exit()`, `teardown()`), see [App Lifecycle](/docs/documentation/development/app-lifecycle).

<CardGroup cols={2}>
  <Card title="Understanding Requests" href="/docs/documentation/deployment/requests">
    Request lifecycle, retry interaction, and how requests flow through the queue to runners
  </Card>

  <Card title="Debugging Runners" href="/docs/documentation/deployment/debug-runners">
    Shell into live runners or run one-off commands with the fal CLI
  </Card>

  <Card title="Caching" href="/docs/documentation/deployment/caching">
    How fal's multi-layer cache reduces cold start times
  </Card>

  <Card title="CLI: fal runners" href="/docs/api-reference/cli/runners">
    List runners, filter by state, view history, and get runner details
  </Card>

  <Card title="App Analytics" href="/docs/documentation/serverless/observability/app-analytics">
    Dashboard metrics for requests, runners, and performance
  </Card>
</CardGroup>
