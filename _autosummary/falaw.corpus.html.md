# falaw.corpus

Extract model records from `misc/docs/llms-full.txt`.

The fal.ai llms-full.txt has a regular structure:

> ## <Section heading>
> <paragraph>

> ### <Model name>

> - **Model**: `fal-ai/<id>`
> - **Purpose**: <one-liner>
> - **Features**: <details>

We map the section to a category, infer a quality tier from the model
name, and emit ModelRecord-shaped dicts the registry can consume. The
`refresh_models_from_corpus` tool merges these into `data/models.json`,
adding new models without overwriting hand-curated entries.

### Functions

| [`extract_models_from_corpus`](#falaw.corpus.extract_models_from_corpus)(path)              | Yield ModelRecord-shaped dicts parsed from llms-full.txt.   |
|------------------------------------------------------------------------------------------------|-------------------------------------------------------------|
| [`refresh_models_from_corpus`](#falaw.corpus.refresh_models_from_corpus)(\*[, path, write]) | Merge corpus-discovered models into models.json (additive). |

### falaw.corpus.extract_models_from_corpus(path)

Yield ModelRecord-shaped dicts parsed from llms-full.txt.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### falaw.corpus.refresh_models_from_corpus(, path=None, write=False)

Merge corpus-discovered models into models.json (additive).

Returns `{added, total, from_corpus, write}` summary. Setting
`write=False` (the default) reports what *would* change without
touching the file.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
