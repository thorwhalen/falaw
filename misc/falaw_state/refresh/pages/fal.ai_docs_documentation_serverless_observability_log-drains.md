> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Log Drains

> Forward application logs to Datadog or any HTTPS endpoint.

Log Drains automatically forward your application logs to an external destination in real time. Use the built-in Datadog integration or send NDJSON payloads to a custom HTTPS webhook.

<Frame>
  <iframe className="w-full aspect-video rounded-lg" srcdoc="<style>*{padding:0;margin:0;overflow:hidden}html,body{height:100%}img,span{position:absolute;width:100%;top:0;bottom:0;margin:auto}span{height:1.5em;text-align:center;font:48px/1.5 sans-serif;color:white;text-shadow:0 0 0.5em black}</style><a href='https://www.youtube.com/embed/gDJJ9bppyV8?start=278&end=345&autoplay=1'><img src='/docs/docs/images/video-thumbs/log-drains.jpg' alt='Log Drains - fal Serverless'><span>▶</span></a>" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen />
</Frame>

## Setting Up a Log Drain

1. Go to [**Dashboard > Log Drains**](https://fal.ai/dashboard/drains)
2. Click **Create Log Drain**
3. Choose a destination and configure it:

<Tabs>
  <Tab title="Datadog">
    * **Name** -- A label for this drain (for example, "Production logs")
    * **Site** -- The Datadog site for your organization
    * **API Key** -- A 32-character Datadog API key
    * **Service** -- The service name attached to each log (default: `fal-log-drain`)
    * **Source** -- The source attached to each log (default: `fal`)
    * **Tags** -- Optional comma-separated Datadog tags (for example, `env:production,team:inference`)
    * **Sampling Rate** -- Maximum logs per delivery batch (1-5000, default: 1000)

    fal stores the API key as a credential and sends it in the `DD-API-KEY` header. Never put an API key in an endpoint URL.
  </Tab>

  <Tab title="Webhook">
    * **Name** -- A label for this drain (for example, "Production logs")
    * **Endpoint URL** -- The HTTPS URL that receives the logs
    * **Secret Token** -- A secret of at least 64 characters used to sign payloads
    * **Sampling Rate** -- Maximum logs per delivery batch (1-5000, default: 1000)
  </Tab>
</Tabs>

4. Click **Test** to verify connectivity before saving

<Note>
  Log Drains require **Admin** role in your team. Only one log drain can be active per account.
</Note>

## Log Format

Webhook logs are delivered as [NDJSON](http://ndjson.org/) (newline-delimited JSON) via HTTP POST. Each line is a JSON object:

```json theme={null}
{"timestamp": "2026-02-17T10:30:00.123Z", "message": "Model loaded successfully", "level": "info", "fal_app_name": "my-model", "fal_app_id": "abc123", "fal_request_id": "req-456", "fal_job_id": "job-789", "fal_endpoint": "/", "fal_node_id": "node-1", "fal_worker_id": "worker-42"}
{"timestamp": "2026-02-17T10:30:01.456Z", "message": "Inference completed in 1.2s", "level": "info", "fal_app_name": "my-model", "fal_app_id": "abc123", "fal_request_id": "req-456", "fal_job_id": "job-789", "fal_endpoint": "/", "fal_node_id": "node-1", "fal_worker_id": "worker-42"}
```

### Fields

Every log line contains the core fields plus any available context labels. Fields beyond `timestamp`, `message`, and `level` are included only when the platform has a value for them.

| Field                | Description                                               |
| -------------------- | --------------------------------------------------------- |
| `timestamp`          | ISO 8601 timestamp                                        |
| `message`            | The log message                                           |
| `level`              | Log level (`info`, `warning`, `error`, etc.)              |
| `fal_app_name`       | Your application name                                     |
| `fal_app_id`         | Application identifier                                    |
| `fal_request_id`     | The request that generated this log                       |
| `fal_job_id`         | The fal-internal job identifier for the runner            |
| `fal_endpoint`       | The endpoint path that handled the request (e.g., `/`)    |
| `fal_node_id`        | The unique ID of the infrastructure node the runner is on |
| `fal_worker_id`      | The scheduler-level allocation ID for the runner          |
| `fal_source`         | Log source (e.g., `run`, `gateway`)                       |
| `fal_isolate_source` | Runtime-level log source                                  |

The Datadog integration sends the same fields through Datadog's Logs API as JSON batches. It also adds the configured `service`, `ddsource`, and `ddtags` values and maps platform log levels to Datadog's `status` field.

## Verifying Webhook Signatures

Every webhook delivery includes an `X-Fal-Signature` header containing an HMAC-SHA256 signature of the request body, signed with your secret token. Use this to verify that deliveries are genuinely from fal.

```python theme={null}
import hmac
import hashlib


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
```

Webhook deliveries use the `Content-Type: application/x-ndjson` header. Datadog deliveries use `Content-Type: application/json`.

## Delivery Behavior

* Logs are delivered in batches on a regular schedule
* New drains start delivering logs from the last 30 seconds
* The **sampling rate** controls the maximum number of log lines per batch
* Deliveries time out after 10 seconds

### Failure Handling

If your destination returns an error or is unreachable:

* fal tracks consecutive failures
* After **5 consecutive failures**, the drain is automatically disabled
* You can re-enable it from the dashboard after fixing the endpoint
* The dashboard shows the failure count and last successful delivery time

## Managing Log Drains

Manage your drain from the [Dashboard](https://fal.ai/dashboard/drains). You can enable or disable it, test connectivity, update its destination settings or sampling rate, or delete it entirely.

For a custom webhook, use an HTTPS endpoint you control that accepts NDJSON over HTTP POST. Keep credentials out of the endpoint URL; authenticate requests by verifying the `X-Fal-Signature` header instead.

<Card title="Observability Overview" icon="arrow-right" href="/docs/documentation/serverless/observability/monitor-performance">
  See all monitoring interfaces: dashboard, CLI, and integrations
</Card>
