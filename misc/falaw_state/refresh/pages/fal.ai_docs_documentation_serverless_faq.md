> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# FAQ

Common questions about deploying and running your own apps on fal Serverless. For questions about calling pre-trained models, see the [Model APIs FAQ](/docs/documentation/model-apis/faq).

<AccordionGroup>
  <Accordion title="How easy is it to migrate from another platform?">
    If you already have a working Docker container or a Python inference server, migrating to fal is straightforward. You can bring your existing Dockerfile directly with [custom container images](/docs/documentation/development/use-custom-container-image), or wrap your model in a `fal.App` class with `setup()` and endpoint methods. fal has step-by-step migration guides for [Replicate](/docs/documentation/development/migrate-from-replicate), [Modal](/docs/documentation/development/migrate-from-modal), [RunPod](/docs/documentation/development/migrate-from-runpod), and [generic Docker servers](/docs/documentation/development/migrate-external-docker-server).
  </Accordion>

  <Accordion title="Can I export metrics to my own monitoring stack?">
    Yes. fal exposes a Prometheus-compatible [metrics endpoint](/docs/documentation/serverless/observability/exporting-metrics) that you can scrape with Grafana, Datadog, or any tool that reads Prometheus format. Metrics include request counts, queue depth, runner states, and latency percentiles, broken down by app and endpoint. You can also forward logs to external services with [log drains](/docs/documentation/serverless/observability/log-drains).
  </Accordion>

  <Accordion title="How do I improve runner utilization?">
    The two most impactful settings are `keep_alive` and `scaling_delay`. Lowering `keep_alive` reduces idle time by shutting down runners sooner after they finish processing, which avoids paying for runners that are waiting for requests that never come. Increasing `scaling_delay` prevents fal from spinning up new runners too quickly during short traffic bursts, giving existing runners a chance to absorb the load first. Together these help you avoid over-provisioning. For further tuning, `max_multiplexing` lets a single runner handle multiple requests concurrently, and `concurrency_buffer` pre-warms runners ahead of demand. See [Optimizing Costs](/docs/documentation/serverless/optimizations/optimizing-costs) for the full set of strategies.
  </Accordion>

  <Accordion title="How do I control retry behavior?">
    fal automatically [retries](/docs/documentation/serverless/reliability/retries) failed queue requests up to 10 times for server errors, timeouts, and connection failures. You can disable retries for specific conditions by setting `skip_retry_conditions` on your app (e.g., `skip_retry_conditions=["timeout"]` if your model legitimately takes a long time). You can also disable retries for individual responses by setting the `X-Fal-Needs-Retry: 0` header from your endpoint, or per-request by the caller with the `X-Fal-No-Retry: 1` header.
  </Accordion>

  <Accordion title="How am I billed for Serverless?">
    You are billed per-second for the total time your runners are alive, at the rate for your chosen [machine type](/docs/documentation/deployment/machine-types). This includes `setup()`, idle time (including `keep_alive`), active request processing, draining, and teardown. You are not billed for pending time or container image pulls. See [Serverless Pricing](/docs/documentation/serverless/pricing) for the full breakdown by runner state.
  </Accordion>

  <Accordion title="Am I billed for idle runners?">
    Yes. Runners in the `IDLE` state are billed at the same per-second rate as running requests. The `keep_alive` setting controls how long a runner stays alive after finishing its last request. Set `keep_alive = 0` to shut down immediately after each request, or use `min_concurrency` to keep warm runners available. See [Optimizing Costs](/docs/documentation/serverless/optimizations/optimizing-costs) for strategies to balance cost and cold starts.
  </Accordion>

  <Accordion title="What GPU types are available?">
    fal offers CPU instances (XS through L) and GPU instances including RTX 4090, RTX 5090, A100, L40, H100, H200, and B200. Multi-GPU configurations are available for distributed workloads. See [Machine Types](/docs/documentation/deployment/machine-types) for full specs and guidance on choosing the right GPU.
  </Accordion>

  <Accordion title="How do I reduce cold start times?">
    Cold starts happen when no warm runner is available and a new one must be provisioned. You can reduce them by setting `min_concurrency` to keep runners warm, using [FlashPack](/docs/documentation/serverless/optimizations/flashpack) for faster container pulls, storing model weights on [persistent storage](/docs/documentation/development/use-persistent-storage) (`/data`) to avoid re-downloads, and optimizing your container image. See [Optimizing Cold Starts](/docs/documentation/serverless/optimizations/optimize-cold-starts) for the full guide.
  </Accordion>

  <Accordion title="What is the /data volume?">
    Every runner has access to a shared [persistent storage](/docs/documentation/development/use-persistent-storage) volume mounted at `/data`. Files written to `/data` persist across requests, runner restarts, and deployments. It is backed by a multi-layer cache (local NVMe, datacenter cache, global object store) and is the recommended place to store model weights, datasets, and configuration files.
  </Accordion>

  <Accordion title="Can I use my own Docker image?">
    Yes. You can specify a Dockerfile or reference a pre-built image from any container registry, including private registries. See [Using a Custom Container Image](/docs/documentation/development/use-custom-container-image) for setup instructions.
  </Accordion>

  <Accordion title="How does autoscaling work?">
    fal automatically scales runners up and down based on incoming request volume. You control the behavior with `min_concurrency` (minimum warm runners), `max_concurrency` (maximum runners), `max_multiplexing` (requests per runner), and `keep_alive` (idle timeout). See [Scaling Your Application](/docs/documentation/deployment/scale-your-application) for details.
  </Accordion>

  <Accordion title="What is the maximum request timeout?">
    The default request timeout is 3600 seconds (1 hour). You can configure this per-app with the `request_timeout` setting in your app class. Callers can also set a client-side [`start_timeout`](/docs/documentation/model-apis/inference/queue#start_timeout) to limit how long they wait before processing begins.
  </Accordion>

  <Accordion title="Can I run multiple models on one endpoint?">
    Yes. You can load multiple models in `setup()` and route between them based on request input, or use [multi-app routing](/docs/documentation/development/multi-app-routing) to serve different models from different endpoints within a single deployment. You can also use [runner hints](/docs/documentation/serverless/optimizations/optimize-routing-behavior) to pin requests to runners with specific models loaded.
  </Accordion>

  <Accordion title="How do I rollback a bad deployment?">
    Every deployment creates a new revision. You can roll back to any previous revision from the dashboard or CLI. See [Rollbacks](/docs/documentation/deployment/rollbacks) for instructions.
  </Accordion>

  <Accordion title="Can I access logs from my running app?">
    Yes. Logs from your app are available in the dashboard, via the CLI (`fal apps runners`), and through the [Platform APIs](/docs/api-reference/platform-apis/for-serverless). You can also configure [log drains](/docs/documentation/serverless/observability/log-drains) to forward logs to external services. See [Logging](/docs/documentation/development/logging) for how to emit structured logs from your app.
  </Accordion>

  <Accordion title="Do concurrency limits apply to my own endpoints?">
    No. When you call your own Serverless endpoints, [concurrency limits](/docs/documentation/model-apis/concurrency-limits) are not enforced. Your throughput is limited by your `max_concurrency` scaling configuration, not by the platform-level account concurrency limit.
  </Accordion>
</AccordionGroup>
