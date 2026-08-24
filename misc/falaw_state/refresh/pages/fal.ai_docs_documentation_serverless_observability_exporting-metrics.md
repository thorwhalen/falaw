> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Exporting Metrics

> Export Prometheus-compatible metrics to Grafana, Datadog, or any monitoring tool.

fal exposes a Prometheus-compatible metrics endpoint that you can scrape with any monitoring tool. Use it to build custom dashboards, set up alerts on queue depth or error rates, and feed fal metrics into the same observability stack you use for the rest of your infrastructure.

The endpoint returns metrics in [Prometheus exposition format](https://prometheus.io/docs/instrumenting/exposition_formats/), so it works with Grafana, Datadog, New Relic, Splunk, or any tool that can scrape a Prometheus target. Responses are cached for 10 seconds, so set your scrape interval accordingly.

## Endpoint

```bash theme={null}
curl -H "Authorization: Key $FAL_KEY" \
  https://api.fal.ai/v1/serverless/metrics
```

## Available Metrics

| Metric                                   | Labels                                 | Description                                            |
| ---------------------------------------- | -------------------------------------- | ------------------------------------------------------ |
| `fal_app_runners`                        | `application`, `state`, `machine_type` | Number of runners currently allocated                  |
| `fal_app_queue_size`                     | `application`                          | Requests waiting in queue                              |
| `fal_app_concurrent_requests`            | `application`                          | Requests being actively processed                      |
| `fal_app_requests_completed`             | `application`, `method`, `status`      | Requests completed in the last minute                  |
| `fal_app_requests_received`              | `application`, `method`                | Requests received in the last minute                   |
| `fal_app_request_latency`                | `application`, `le`                    | Completed requests bucketed by latency                 |
| `fal_app_runner_cpu_usage_percent`       | `application`                          | CPU usage percent, summed across the app's runners     |
| `fal_app_runner_memory_usage_bytes`      | `application`                          | Memory usage in bytes, summed across the app's runners |
| `fal_app_runner_gpu_utilization_percent` | `application`                          | GPU utilization percent, summed across the app's GPUs  |
| `fal_app_runner_vram_usage_percent`      | `application`                          | VRAM usage percent, summed across the app's GPUs       |
| `fal_app_runner_gpu_count`               | `application`                          | Number of GPUs across the app's runners                |

The `state` label tracks whether a runner's container is up: `pending` while starting, `running` once up, and `dead` briefly after it exits.

<Warning>
  `state` is coarser than the runner status in `fal runners list`. A runner the CLI shows as `IDLE` (alive, not processing) and one it shows as `RUNNING` both report `state="running"`, so `fal_app_runners{state="running"}` counts runners that are up, not runners that are busy.
</Warning>

### Resource Metrics

The `fal_app_runner_*` metrics report resource usage **summed across an app's runners**, not averaged. An app with four busy GPUs reports `fal_app_runner_gpu_utilization_percent` around `400`, so these values scale with the size of your app — normalize before alerting on a threshold. Divide the GPU and VRAM percentages by `fal_app_runner_gpu_count` for a per-GPU average, and the CPU percentage by the app's runner count.

Apps running on CPU-only machine types report no GPU or VRAM samples.

## Integration

Add the endpoint as a Prometheus data source in your monitoring tool. The only requirement is passing your API key in the `Authorization: Key ...` header. Set the scrape interval to at least 10 seconds since responses are cached at that frequency.

### Example PromQL Queries

```promql theme={null}
# Runners currently up, by app
fal_app_runners{state="running"}

# Queue depth across all apps
sum(fal_app_queue_size) by (application)

# Request rate (completed per minute)
fal_app_requests_completed

# P99 latency estimation
histogram_quantile(0.99, fal_app_request_latency)

# Average GPU utilization per GPU
fal_app_runner_gpu_utilization_percent / fal_app_runner_gpu_count

# Average VRAM usage per GPU
fal_app_runner_vram_usage_percent / fal_app_runner_gpu_count

# Average CPU usage per runner
# on(application) is required — the aggregated right side drops the
# job/instance labels your scrape attaches to the left side
fal_app_runner_cpu_usage_percent
  / on(application) sum(fal_app_runners) by (application)

# Memory usage in GiB
fal_app_runner_memory_usage_bytes / 1024^3
```

<Note>
  All metrics are gauges. The `fal_app_request_latency` metric uses histogram-style buckets (labeled by `le`) for latency distribution analysis.
</Note>

<Card title="Platform API Reference" icon="arrow-right" href="/docs/api-reference/platform-apis/for-serverless">
  Full API specification for the metrics endpoint
</Card>
