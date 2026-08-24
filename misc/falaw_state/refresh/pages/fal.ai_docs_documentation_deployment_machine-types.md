> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Machine Types

> Available machine types, specifications, and guidance on choosing the right GPU for your workload.

## CPU Machine Types

For lightweight workloads that don't require GPU acceleration -- routing, preprocessing, API proxies.

| Machine Type | RAM    | CPU Cores |
| :----------- | :----- | :-------- |
| **XS**       | 512 MB | 0.5       |
| **S**        | 1 GB   | 1         |
| **M**        | 2 GB   | 2         |
| **L**        | 15 GB  | 4         |
| **XL**       | 30 GB  | 8         |

## GPU Machine Types

| Machine Type                                                                                                     | VRAM   | RAM    | CPU | Bandwidth | Video Enc / Dec |
| :--------------------------------------------------------------------------------------------------------------- | :----- | :----- | :-- | :-------- | :-------------- |
| [**GPU-A100**](https://www.nvidia.com/en-us/data-center/a100/)                                                   | 40 GB  | 60 GB  | 12  | 2.0 TB/s  | -- / 5          |
| [**GPU-L40**](https://www.nvidia.com/en-us/data-center/l40s/)                                                    | 48 GB  | 100 GB | 6   | 0.9 TB/s  | 3 / 3 (AV1)     |
| [**GPU-H100**](https://www.nvidia.com/en-us/data-center/h100/)                                                   | 80 GB  | 112 GB | 12  | 3.4 TB/s  | -- / 7          |
| [**GPU-RTXPRO6000**](https://www.nvidia.com/en-us/products/workstations/professional-desktop-gpus/rtx-pro-6000/) | 96 GB  | 100 GB | 6   | 1.8 TB/s  | 4 / 4 (AV1)     |
| [**GPU-H200**](https://www.nvidia.com/en-us/data-center/h200/)                                                   | 141 GB | 112 GB | 12  | 4.8 TB/s  | -- / 7          |
| [**GPU-B200**](https://www.nvidia.com/en-us/data-center/b200/)                                                   | 192 GB | 210 GB | 19  | 8.0 TB/s  | -- / 7          |

Video encode/decode counts refer to hardware [NVENC/NVDEC](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new) engines -- dedicated hardware units that encode or decode video independently of the GPU's compute cores. GPUs with encoders (RTX PRO 6000, L40) can output video frames without using GPU compute time. GPUs marked `--` for encode have no hardware encoder and require software encoding on the CPU.

### Choosing a GPU

**By VRAM requirement** -- pick the smallest GPU that fits your model:

* **40 GB** (A100): General-purpose training and inference at a lower price point than Hopper GPUs
* **48 GB** (L40): AI inference combined with [video transcoding](https://www.cisco.com/c/dam/en/us/products/collateral/servers-unified-computing/ucs-c-series-rack-servers/nvidia-l40s-ucsc-gpu-l40s.pdf) and graphics rendering
* **80 GB** (H100): LLM inference and training, [NVLink 4.0 at 900 GB/s](https://resources.nvidia.com/en-us-data-center-overview/nvidia-tensor-core-gpu-datasheet) for multi-GPU scaling
* **96 GB** (RTX PRO 6000): Diffusion, large-image, and video generation with [AV1 hardware encode](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new); ample VRAM headroom for high-resolution and batched workloads
* **141 GB** (H200): Large models and long-context workloads on a single GPU -- [76% more memory and 43% more bandwidth than H100](https://resources.nvidia.com/en-us-dgx-systems/dgx-h200-datasheet)
* **192 GB** (B200): Maximum memory and compute for the largest models, [FP4/FP6/FP8 precision support](https://www.techpowerup.com/gpu-specs/b200.c4210)

**By workload type:**

* **Image generation**: L40 or RTX PRO 6000 (good throughput, generous VRAM)
* **Video generation**: RTX PRO 6000 (4 NVENC + 4 NVDEC, AV1 encode, more VRAM) or L40 (3 NVENC + 3 NVDEC)
* **LLM inference**: H100 or H200 (high bandwidth, large VRAM)
* **Training**: A100, H100, or H200 (depending on model size)
* **Largest models**: B200, RTX PRO 6000, or multi-GPU H100/H200

## Configuration

Set the machine type in your application:

```python theme={null}
class MyApp(fal.App):
    machine_type = "GPU-H100"
    num_gpus = 1
```

### Multiple Machine Types

Allow your app to use multiple machine types for a larger pool of available machines:

```python theme={null}
class MyApp(fal.App):
    machine_type = ["GPU-H100", "GPU-A100"]
```

Machine types are tried in order. If the first type has no available capacity, the next is used.

### Multi-GPU

For models that need more than one GPU:

```python theme={null}
class MyApp(fal.App):
    machine_type = "GPU-H100"
    num_gpus = 2
```

<Card title="Multi-GPU Workloads" icon="arrow-right" href="/docs/documentation/serverless/distributed/overview">
  Learn how to distribute inference across multiple GPUs
</Card>

## Changing Machine Types

**Via Code:**

Update `machine_type` and redeploy:

```python theme={null}
class MyApp(fal.App):
    machine_type = "GPU-A100"
```

```bash theme={null}
fal deploy
```

Each `fal deploy` creates a new revision, so this moves your whole app onto the new machine type: the new revision's runners come up on the new type, and fal drains the old revision's runners as part of the deployment. See [Rollout Strategies](/docs/documentation/deployment/deploy-to-production#rollout-strategies) for how that transition is sequenced.

**Via CLI:**

Change the machine type on a running app without creating a revision:

```bash theme={null}
fal apps scale my-model --machine-types GPU-A100
```

This updates the app's configuration right away, but only **new** runners come up on the new machine type. Existing warm runners keep serving on the old type until they shut down -- so if your app keeps runners alive (via `min_concurrency`, `keep_alive`, or steady traffic), they can stay on the old type indefinitely. To move them, see [Rolling Out Existing Runners](#rolling-out-existing-runners) below.

**Via Dashboard:**

You can also change the machine type from your app's configuration panel in the [dashboard](https://fal.ai/dashboard). This behaves like `fal apps scale`: the change applies to the live app without creating a revision, and only new runners use the new type.

Because existing runners would otherwise stay on the old type, fal asks what to do with them as soon as the change is saved (the GPU count and fallback types count as part of the machine type):

* **Yes, roll out** starts a rollout, exactly as if you had run `fal apps rollout`. The cost and capacity notes in [Rolling Out Existing Runners](#rolling-out-existing-runners) apply.
* **No, keep existing** leaves them alone. They keep serving on the old machine type until they shut down.

Declining is not permanent. You can roll out later at any time from the CLI, without changing the machine type again.

<Note>
  `machine_type` is a code-specific parameter -- it always comes from your code and resets on every deploy. A change made with `fal apps scale` or from the dashboard is temporary: the next `fal deploy` resets it to whatever your code specifies. Update your code to match if you want the change to survive redeploys. See [Scaling Configuration](/docs/documentation/deployment/scaling-configuration) for details.
</Note>

### Rolling Out Existing Runners

After changing the machine type with `fal apps scale` or from the dashboard, roll your existing runners onto the new type. From the dashboard, choose **Yes, roll out** on the prompt shown after you save. From the CLI:

```bash theme={null}
fal apps rollout my-model
```

fal starts replacement runners on the new machine type and drains each old runner only once a replacement has finished starting up, so traffic is not interrupted. Pass `--force` to terminate the existing runners immediately instead, dropping their in-flight requests. `fal apps scale` and `fal apps rollout` both target the `main` [environment](/docs/documentation/deployment/manage-environments) unless you pass `--env` or set `FAL_ENV`. See [`fal apps rollout`](/docs/api-reference/cli/apps/rollout) for the full command reference and [Rollouts](/docs/documentation/deployment/rollbacks#rollouts) for the other reasons to roll your runners.

Replacements are started in parallel rather than one at a time, and they are provisioned on top of `max_concurrency` rather than within it, so during the transition your app can run close to double its usual runner count. Each runner is billed at its own actual machine type from the moment it begins `setup()`, so expect a temporary cost increase until the old runners finish draining.

<Note>
  A rollout needs temporary headroom for those extra runners. It stalls while your account's GPU limits are fully consumed -- including by your other apps -- or while none of the app's configured machine types has available capacity. In either case your existing runners keep serving in the meantime.
</Note>

<Note>
  You do not need a rollout after a `fal deploy`. A rollout applies to your app's **current** revision, so running one after a deploy recycles runners that are already on the new machine type and you pay the overlap cost above for no benefit. This is also why a rollout is a separate mechanism from the [rollout strategies](/docs/documentation/deployment/deploy-to-production#rollout-strategies) that `fal deploy` uses to move traffic between revisions.
</Note>
