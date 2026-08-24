> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# fal deploy

<Tip>
  Before deploying, validate your app with [`fal run`](/docs/api-reference/cli/run). It boots your app on a temporary worker — running `setup()` and your endpoints just like production — so import and model-loading errors surface locally instead of as a production crashloop. On a first deploy or after a failed deploy, the CLI reminds you to do this. See [Development vs Production](/docs/documentation/deployment/deploy-to-production#development-vs-production).
</Tip>

```bash theme={null}
Usage: fal deploy [-h] [--output {pretty,json}] [--json] [--team TEAM]
                  [--app-name APP_NAME] [--auth AUTH]
                  [--strategy {recreate,rolling}] [--attach | --detach]
                  [--no-scale] [--reset-scale] [--check] [--yes]
                  [--message MESSAGE] [--annotation KEY=VALUE] [--no-cache]
                  [--env ENV]
                  [app_ref]

Deploy a fal application. If no app reference is provided, the command will look for a pyproject.toml file with a [tool.fal.apps] section and deploy the application specified with the provided app name.

Positional Arguments:
  app_ref               Application reference. Either a file path or a file path and a function name separated by '::'. If no reference is provided, the command will look for a pyproject.toml file with a [tool.fal.apps] section and deploy the application specified with the provided app name.
                        File path example: path/to/myfile.py::MyApp
                        App name example: my-app (configure team in pyproject.toml)

Options:
  -h, --help            show this help message and exit
  --team TEAM           The team to use.
  --app-name APP_NAME   Application name to deploy with.
  --auth AUTH           Application authentication mode (private, public, shared).
  --strategy {recreate,rolling}
                        Deployment strategy.
  --attach              Attach to the deployment process. Only applies when --strategy is rolling (the default).
  --detach              Do not attach to the deployment process. Only applies when --strategy is rolling (the default).
  --no-scale            Use the previous deployment of the application for scale settings. This is the default behavior.
  --reset-scale         Use the application code for scale settings.
  --check               Show a pre-deployment summary before deploying. Prompts for confirmation unless --yes is also set.
  --yes                 Skip interactive deploy confirmation prompts. When combined with --check, the summary is still shown.
  --message MESSAGE     Freeform message to attach to this revision (e.g, 'add feature')
  --annotation KEY=VALUE
                        Custom key=value pair to attach to this revision (e.g, GIT_SHA=1234567890). Can be repeated. Value must be a string.
  --no-cache            Do not use the cache for the environment build.
  --env ENV             Target environment (defaults to main). Can also be set via FAL_ENV environment variable.

Output:
  --output {pretty,json}
                        Modify the command output
  --json                Output in JSON format (same as --output json)

Examples:
  fal deploy
  fal deploy path/to/myfile.py
  fal deploy path/to/myfile.py::MyApp
  fal deploy path/to/myfile.py::MyApp --app-name myapp --auth public
  fal deploy path/to/myfile.py::MyApp --check
  fal deploy path/to/myfile.py::MyApp --check --yes
  fal deploy path/to/myfile.py::MyApp --env staging
  fal deploy my-app
  fal deploy my-app --message "a1b2c3d fix cold-start"
  fal deploy my-app --annotation DEPLOYER_ID=foo-123 --annotation GIT_SHA=1234567890
```
