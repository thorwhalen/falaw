> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Import Code

> Bring local Python packages, modules, files, and external repositories into your fal app's remote environment.

When your app spans multiple files, uses local utility modules, or depends on code from a private repository, you need a way to include that code in the remote environment where your [runners](/docs/documentation/getting-started/runners-and-caching) execute. This page covers the mechanisms fal provides: local-path `requirements` for installable Python projects, `app_files` for local files and directories, `local_python_modules` for Python modules that should be serialized alongside your app, and `clone_repository` for pulling external Git repos at startup.

These mechanisms work with the [fal Runtime](/docs/documentation/development/fal-runtime) (pip requirements). If your app uses a [custom Docker container](/docs/documentation/development/use-custom-container-image), package or copy your code in the Dockerfile instead.

<Frame>
  <iframe className="w-full aspect-video rounded-lg" srcdoc="<style>*{padding:0;margin:0;overflow:hidden}html,body{height:100%}img,span{position:absolute;width:100%;top:0;bottom:0;margin:auto}span{height:1.5em;text-align:center;font:48px/1.5 sans-serif;color:white;text-shadow:0 0 0.5em black}</style><a href='https://www.youtube.com/embed/gDJJ9bppyV8?start=864&end=923&autoplay=1'><img src='/docs/docs/images/video-thumbs/import-code.jpg' alt='App Files - fal Serverless'><span>▶</span></a>" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen />
</Frame>

<Warning>
  Local-path `requirements`, `app_files`, and `local_python_modules` are only supported with the fal Runtime. If your app uses a custom `ContainerImage`, use `COPY` and `RUN pip install ...` in your Dockerfile to include local code.
</Warning>

## Choosing the Right Mechanism

fal provides several ways to bring code into the remote environment, each suited to a different situation.

Use **local-path `requirements`** when your local code is an installable Python project with a `pyproject.toml`. This is the best choice for projects with dependencies or optional extras such as `.[extra]` or `projects/foo[extra]`. fal builds an sdist locally and uses it in the remote environment.

Use **`app_files`** when you have a multi-file project that is not packaged as an installable Python project, or when you need to include non-Python assets alongside your app. Files are uploaded and placed at the same relative paths, so imports and file reads work identically to local development.

Use **`local_python_modules`** when you have a simple Python module that your app imports at the top level. The module is serialized (pickled) alongside your app class and made available on the remote Python path. This is lighter-weight than `app_files` but only works for importable Python packages.

Use **`clone_repository`** when you need to pull code from an external Git repository at runner startup. The clone happens inside `setup()`, so the code is available before your first request.

## Local Project Requirements

Use local-path entries in `requirements` when your app code or shared library is packaged as a Python project. For entries such as `.`, `.[extra]`, and `projects/foo[extra]`, fal builds an sdist locally and uses it in the remote environment.

```python theme={null}
class MyApp(fal.App):
    requirements = [
        "torch==2.4.0",
        ".[extra]",
    ]

    @fal.endpoint("/")
    def predict(self, input: MyInput) -> MyOutput:
        from my_package.inference import run

        return run(input)
```

The local project must be buildable as an sdist and have a `pyproject.toml` with `[project].name`. Optional extras are preserved, so `.[extra]` becomes an install of your package with that extra on the runner.

For monorepos, either point the requirement at the package directory:

```python theme={null}
class MyApp(fal.App):
    requirements = [
        "projects/foo[extra]",
        "projects/bar",
    ]
```

or set `requirements_context_dir` and use `.` relative to that directory:

```python theme={null}
class MyApp(fal.App):
    requirements_context_dir = "../projects/foo"
    requirements = [".[extra]"]
```

For `fal.function`, pass the same option to the decorator:

```python theme={null}
@fal.function(requirements=[".[extra]"], requirements_context_dir="../projects/foo")
def predict(input: MyInput) -> MyOutput: ...
```

When using `pyproject.toml` app configuration, set the same fields on the app entry:

```toml theme={null}
[tool.fal.apps.image-generator]
ref = "apps/image_generator/app.py::ImageGenerator"
requirements_context_dir = "projects/foo"
requirements = [".[extra]"]
```

Relative paths in `requirements` are resolved from `requirements_context_dir`. When no context directory is set, class-based apps resolve from the app file directory, while `pyproject.toml` app entries resolve from the directory containing `pyproject.toml`. Relative `requirements_context_dir` values in `pyproject.toml` are also resolved from the directory containing `pyproject.toml`.

## Package Entry Points

By default, a `ref` such as `apps/image_generator/app.py::ImageGenerator` loads your app file locally and serializes the `fal.App` class into the deployment payload. Use `python_entry_point` when your app or function is part of an installable Python package and you want the runner to import it by module path instead.

Package entry points are useful when your app is already structured as a package, when you want top-level package code to run in the remote environment, or when your app definition references objects that should be imported normally rather than pickled from your local process.

```text theme={null}
my-project/
|-- pyproject.toml
`-- my_image_app/
    |-- __init__.py
    |-- inference.py
    `-- server.py
```

In `my_image_app/server.py`:

```python theme={null}
import fal
from pydantic import BaseModel


class Input(BaseModel):
    prompt: str


class ImageGenerator(fal.App):
    @fal.endpoint("/")
    def generate(self, input: Input) -> dict:
        from my_image_app.inference import run

        return run(input.prompt)
```

Configure the named app in `pyproject.toml` with `python_entry_point`:

```toml theme={null}
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "my-image-app"
version = "0.1.0"
dependencies = ["fal", "pydantic"]

[tool.setuptools.packages.find]
include = ["my_image_app*"]

[tool.fal.apps.image-generator]
python_entry_point = "my_image_app.server:ImageGenerator"
requirements = ["."]
auth = "private"
machine_type = "GPU-H100"
```

Then run or deploy the app by its configured name:

```bash theme={null}
fal run image-generator
fal deploy image-generator
```

`python_entry_point` must use `<module>:<symbol>` format. The symbol can be a `fal.App` subclass or a `@fal.function`, and `python_entry_point` is mutually exclusive with `ref`.

When you use `python_entry_point`, put runtime and deployment settings in the `[tool.fal.apps.<app-name>]` entry. fal uses the options from `pyproject.toml`, such as `machine_type`, `requirements`, `auth`, scaling settings, and image configuration, instead of reading those settings from the imported app class or function decorator.

When you use the fal Runtime, include the package through local-path `requirements` such as `.`, `.[serverless]`, or `projects/foo[serverless]`. For monorepos, use `requirements_context_dir` the same way as with local project requirements:

```toml theme={null}
[tool.fal.apps.image-generator]
python_entry_point = "my_image_app.server:ImageGenerator"
requirements_context_dir = "projects/image-app"
requirements = [".[serverless]"]
```

If the app uses a custom container image, install or copy the package in the Dockerfile instead of using local-path `requirements`. The entry point can still point at the installed package:

```toml theme={null}
[tool.fal.apps.image-generator]
python_entry_point = "my_image_app.server:ImageGenerator"
machine_type = "GPU-H100"

[tool.fal.apps.image-generator.image]
dockerfile = "Dockerfile"
```

## App Files

The `app_files` attribute includes local files and directories in the remote environment, mirroring your local file layout exactly. Imports and file paths work the same way they do on your machine.

```python theme={null}
class MyApp(fal.App):
    app_files = [
        "utils/helper.py",
        "models",
        "checkpoint.pt",
    ]

    @fal.endpoint("/")
    def predict(self, input: MyInput) -> MyOutput:
        from utils.helper import process_data
        from models.classifier import MyModel

        result = process_data(input)
        model = MyModel.load_checkpoint("checkpoint.pt")
        return model.predict(result)
```

If your local project looks like this:

```
project/
├── my_fal_app.py
├── utils/
│   └── helper.py
└── models/
    └── classifier.py
```

Then on the runner, `from utils.helper import process_data` and `from models.classifier import MyModel` work exactly as they do locally. Files are placed relative to your app file location.

### Context Directory

By default, all file paths are resolved relative to the directory containing your fal app file. You can change this base directory with `app_files_context_dir`, which is useful for monorepos or when you need to include files from a parent directory:

```python theme={null}
class MyApp(fal.App):
    app_files_context_dir = "../"
    app_files = [
        "src/data_processing",
        "src/models",
        "weights",
        "utils",
    ]
```

All paths must be relative and within the context directory. Absolute paths and paths that escape the context directory (e.g., `../../outside`) are rejected. Included files are read-only on the runner.

### Ignoring Files

Use `app_files_ignore` to exclude files using regex patterns. fal excludes `.pyc`, `__pycache__/`, `.git/`, and `.DS_Store` by default.

```python theme={null}
class MyApp(fal.App):
    app_files = ["my_project/"]
    app_files_ignore = [
        r"\.pyc$",
        r"__pycache__/",
        r"\.git/",
        r"\.env$",
        r"test_.*\.py$",
    ]
```

Only include the files your app actually needs. Smaller deployments mean faster uploads and faster runner startup.

## Local Python Modules

The `local_python_modules` attribute ships a Python module alongside your app by serializing it into the deployment payload. This is a simpler mechanism than `app_files` - it adds the specified modules to the remote Python path so they can be imported directly. Use it when you have a small utility module that your app imports at the top level.

```python theme={null}
from mymodule import myfunction


class MyApp(fal.App):
    local_python_modules = ["mymodule"]

    @fal.endpoint("/")
    def predict(self, input: MyInput) -> MyOutput:
        myfunction(input)
        ...
```

For projects with multiple files, directories, or non-Python assets (configs, weights), `app_files` is the better choice because it preserves the full directory structure and supports ignore patterns.

## Git Repositories

Use `clone_repository` to pull code from a Git repository at runner startup. The clone happens inside `setup()`, so the repository is available before any requests are processed. Pin to a specific commit hash for reproducibility.

```python theme={null}
from fal.toolkit import clone_repository


class MyApp(fal.App):
    def setup(self):
        path = clone_repository(
            "https://github.com/myorg/myrepo",
            commit_hash="1418c53bcfaf4efc1034207dcb39d093d5fff645",
            include_to_path=True,
        )

        import myproject

        ...
```

Setting `include_to_path=True` adds the cloned directory to `PYTHONPATH`, so you can import modules from the repository directly. For private repositories, include a personal access token in the URL: `https://YOUR_TOKEN@github.com/myorg/private-repo.git`.
