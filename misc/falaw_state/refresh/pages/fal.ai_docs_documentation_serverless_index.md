> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Introduction to Serverless

> Deploy custom AI models on GPU infrastructure that autoscales from zero to thousands of machines.

fal Serverless lets you deploy your own AI models, pipelines, and applications on GPU infrastructure that scales automatically. You write a Python class, define your hardware requirements, and fal handles provisioning, scaling, networking, and observability. Your code runs on H100s, A100s, or any other [machine type](/docs/documentation/deployment/machine-types) you choose, scaling from zero runners to thousands based on demand, and back to zero when traffic stops.

Every model in the [Model APIs](/docs/documentation/model-apis/overview) marketplace is a `fal.App` running on Serverless. When you deploy your own app, you get the same [queue-based reliability](/docs/documentation/model-apis/inference/queue), the same [analytics dashboard](/docs/documentation/serverless/observability/app-analytics), and the same [client SDKs](/docs/documentation/development/calling-your-endpoints). The difference is that you control the code, the model weights, and the container environment. You can also [publish your app to the marketplace](/docs/documentation/serverless/publishing-to-marketplace) so anyone can call it with their own API key.

<Warning>
  **Enterprise Feature** - Learn more about [fal Serverless](https://fal.ai/serverless) and visit the [Serverless Get Started page](https://fal.ai/dashboard/serverless-get-started) to request access.
</Warning>

## How It Works

The best deployment approach depends on where you are starting from. If you are migrating from another provider, you can be up and running with minimal code changes. If you are starting a new project, fal can build and manage the container for you. All three paths give you the same autoscaling, observability, and [runner](/docs/documentation/getting-started/runners-and-caching) management.

### Migrating an existing server

If you already have a working HTTP server (FastAPI, Flask, or any framework), this is the fastest path. Use Direct Server Mode with `exposed_port`, and fal routes traffic to your server's port with no code changes to your existing application.

```toml theme={null}
[tool.fal.apps.my-server]
auth = "private"
machine_type = "GPU-A100"
exposed_port = 8000

[tool.fal.apps.my-server.image]
dockerfile = "Dockerfile"
```

Direct Server Mode supports the same scaling parameters as `fal.App` (keep\_alive, min\_concurrency, max\_concurrency, and more). See [Migrate a Docker Server](/docs/documentation/development/migrate-external-docker-server) for a complete walkthrough and the [pyproject.toml reference](/docs/api-reference/python-sdk/pyproject-toml) for the full configuration schema. There are also step-by-step guides for [Replicate](/docs/documentation/development/migrate-from-replicate), [Modal](/docs/documentation/development/migrate-from-modal), and [RunPod](/docs/documentation/development/migrate-from-runpod).

### Migrating a custom container

If you have a Docker image with your model and dependencies baked in but not a full HTTP server, you can bring it directly. Use `ContainerImage` to reference your Dockerfile or pull from a registry. You keep full control over the build while using fal's endpoint system and scaling.

```python theme={null}
import fal
from fal.container import ContainerImage

class MyModel(fal.App):
    image = ContainerImage.from_dockerfile_str("""
        FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime
        RUN apt-get update && apt-get install -y ffmpeg
        RUN pip install diffusers transformers
    """)
    machine_type = "GPU-A100"

    def setup(self):
        from diffusers import StableDiffusionXLPipeline
        self.pipe = StableDiffusionXLPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0"
        ).to("cuda")

    @fal.endpoint("/")
    def generate(self, input: dict) -> dict:
        image = self.pipe(input["prompt"]).images[0]
        return {"image": image}
```

You can pull from private registries (Docker Hub, GCP Artifact Registry, AWS ECR, Azure Container Registry). See [Custom Container Images](/docs/documentation/development/use-custom-container-image) for the full guide.

### Starting a new project

If you are building from scratch, use a native `fal.App` with pip requirements. You write a Python class, list your dependencies, and define your endpoints. fal builds the container for you.

```python theme={null}
import fal
from pydantic import BaseModel

class Input(BaseModel):
    prompt: str

class Output(BaseModel):
    result: str

class MyModel(fal.App):
    machine_type = "GPU-H100"
    requirements = ["torch", "transformers"]

    def setup(self):
        from transformers import pipeline
        self.pipe = pipeline("text-generation", model="gpt2", device="cuda")

    @fal.endpoint("/")
    def generate(self, input: Input) -> Output:
        result = self.pipe(input.prompt, max_length=50)[0]["generated_text"]
        return Output(result=result)
```

For the full environment setup options, see [Defining Your Environment](/docs/documentation/development/container-setup).

### Test and deploy

Regardless of which approach you use, the workflow is the same: **validate with `fal run` first, then `fal deploy`.** `fal run` starts your app on a temporary worker and gives you a throwaway URL, running `setup()` and your endpoints exactly as production will — so you catch import errors, missing dependencies, and model-loading failures before they become a production crashloop. Once `fal run` works, `fal deploy` promotes the same app to a persistent URL, a [Playground](/docs/documentation/model-apis/playground) for browser-based testing, and automatic scaling based on incoming traffic. See the [Quick Start](/docs/documentation/development/getting-started/quick-start) to try it in under two minutes.

## Scaling, Observability, and Cost

Once your app is deployed, fal manages the infrastructure for you. [Runners](/docs/documentation/deployment/runners) spin up when requests arrive and shut down when idle. You control the tradeoff between latency and cost with parameters like [keep\_alive](/docs/documentation/deployment/scale-your-application) (how long idle runners stay warm) and [min\_concurrency](/docs/documentation/deployment/scale-your-application) (minimum warm runners). To understand how runners transition between states and how caching reduces [cold starts](/docs/documentation/serverless/optimizations/optimize-cold-starts), see [Runners and Caching](/docs/documentation/getting-started/runners-and-caching).

Observability is built in. [App Analytics](/docs/documentation/serverless/observability/app-analytics) shows request volume, latency percentiles, runner utilization, and startup duration. [Error Analytics](/docs/documentation/serverless/observability/error-analytics) surfaces failing requests with stack traces. You can export metrics to your own stack via the [Prometheus-compatible API](/docs/documentation/serverless/observability/exporting-metrics) or forward logs with [Log Drains](/docs/documentation/serverless/observability/log-drains). For billing, see [Serverless Pricing](/docs/documentation/serverless/pricing) and [Optimizing Costs](/docs/documentation/serverless/optimizations/optimizing-costs).

## Next Steps

If you are new to fal, start with the [Quick Start](/docs/documentation/development/getting-started/quick-start), which walks through building and deploying a Hello World app in under two minutes. The [Deploy Your First Image Generator](/docs/documentation/development/getting-started/deploy-your-first-image-generator) tutorial applies the same workflow to a real Stable Diffusion XL model. Once you are comfortable with the basics, the [App Lifecycle](/docs/documentation/development/app-lifecycle) page explains how apps are structured, where code runs, and how runners start up and shut down.

For more deployment examples covering text-to-image, video, speech, ComfyUI, and custom containers, browse the [Examples](/docs/examples#deploying-models) section. For recent platform updates, check the [Changelog](/docs/changelog) or watch the overview below.

<div className="max-w-4xl mx-auto">
  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          From Alert to Root Cause
        </span>

        <span className="text-xs text-gray-500 dark:text-gray-400">June 2026</span>
      </div>

      <iframe className="w-full aspect-video rounded-lg" srcdoc="<style>*{padding:0;margin:0;overflow:hidden}html,body{height:100%}img,span{position:absolute;width:100%;top:0;bottom:0;margin:auto}span{height:1.5em;text-align:center;font:48px/1.5 sans-serif;color:white;text-shadow:0 0 0.5em black}</style><a href='https://www.youtube.com/embed/Fw1DkM7eNPI?autoplay=1'><img src='https://img.youtube.com/vi/Fw1DkM7eNPI/maxresdefault.jpg' alt='What's New in fal Serverless — From Alert to Root Cause'><span>▶</span></a>" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen />
    </div>

    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Scaling, observability, cold starts & multi-GPU
        </span>

        <span className="text-xs text-gray-500 dark:text-gray-400">January 2026</span>
      </div>

      <iframe className="w-full aspect-video rounded-lg" srcdoc="<style>*{padding:0;margin:0;overflow:hidden}html,body{height:100%}img,span{position:absolute;width:100%;top:0;bottom:0;margin:auto}span{height:1.5em;text-align:center;font:48px/1.5 sans-serif;color:white;text-shadow:0 0 0.5em black}</style><a href='https://www.youtube.com/embed/gDJJ9bppyV8?autoplay=1'><img src='https://img.youtube.com/vi/gDJJ9bppyV8/maxresdefault.jpg' alt='What's New in fal Serverless'><span>▶</span></a>" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen />
    </div>
  </div>
</div>
