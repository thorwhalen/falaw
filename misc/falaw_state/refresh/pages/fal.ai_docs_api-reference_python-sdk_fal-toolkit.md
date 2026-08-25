> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# fal.toolkit

> API reference for fal.toolkit

```python theme={null}
from fal.toolkit import (
    Audio,
    CompressedFile,
    FalBaseModel,
    File,
    Image,
    ImageSizeConstraints,
    ImageValidationConfig,
    ImageValidationOptions,
    KVStore,
    Video,
    FalTookitException,
    FileUploadException,
    KVStoreException,
    DownloadError,
    to_xfal,
    Hidden,
    get_image_size,
    clone_repository,
    download_file,
    download_model_weights,
    get_gpu_type,
    load_inductor_cache,
    sync_inductor_cache,
    synchronized_inductor_cache,
)
```

## Classes

### Audio

```python theme={null}
class fal.toolkit.Audio
```

!!! abstract "Usage Documentation" [Models](../concepts/models.md)

A base class for creating Pydantic models.

> **Inherits from:** `File`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name   | Type  | Default | Description |
  | :----- | :---- | :------ | :---------- |
  | `data` | `Any` | -       | -           |
</Accordion>

### CompressedFile

```python theme={null}
class fal.toolkit.CompressedFile
```

!!! abstract "Usage Documentation" [Models](../concepts/models.md)

A base class for creating Pydantic models.

> **Inherits from:** `File`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name   | Type  | Default | Description |
  | :----- | :---- | :------ | :---------- |
  | `data` | `Any` | -       | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name          | Type            | Default | Description |
  | :------------ | :-------------- | :------ | :---------- |
  | `extract_dir` | `Optional[str]` | -       | -           |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### glob

  ```python theme={null}
  def glob(self, pattern: 'str')
  ```

  | Parameter | Type  | Default | Description |
  | :-------- | :---- | :------ | :---------- |
  | `pattern` | `str` | -       | -           |
</Accordion>

### FalBaseModel

```python theme={null}
class fal.toolkit.FalBaseModel
```

Base model for fal applications with field ordering, visibility control, and context binding for error reporting.

Features:

* FIELD\_ORDERS: Control field order in JSON schema, useful for nested
  models.
* Hidden(Field(...)): Mark fields as hidden from OpenAPI schema, useful
  for hidden params.

**Example:**

```python theme={null}
from fal.toolkit.pydantic import FalBaseModel, Field, Hidden

class Input(FalBaseModel):
    FIELD_ORDERS = ["prompt", "image_url"]

    prompt: str = Field(description="Text prompt")
    image_url: str = Field(description="Image URL")
    debug_mode: bool = Hidden(Field(default=False))
```

> **Inherits from:** `BaseModel`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name   | Type  | Default | Description |
  | :----- | :---- | :------ | :---------- |
  | `data` | `Any` | -       | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name             | Type                  | Default | Description |
  | :--------------- | :-------------------- | :------ | :---------- |
  | `SCHEMA_IGNORES` | `ClassVar[Set[str]]`  | `set()` | -           |
  | `FIELD_ORDERS`   | `ClassVar[List[str]]` | `[]`    | -           |
</Accordion>

### File

```python theme={null}
class fal.toolkit.File
```

!!! abstract "Usage Documentation" [Models](../concepts/models.md)

A base class for creating Pydantic models.

> **Inherits from:** `BaseModel`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name   | Type  | Default | Description |
  | :----- | :---- | :------ | :---------- |
  | `data` | `Any` | -       | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name           | Type              | Default | Description |
  | :------------- | :---------------- | :------ | :---------- |
  | `url`          | `str`             | -       | -           |
  | `content_type` | `Optional[str]`   | -       | -           |
  | `file_name`    | `Optional[str]`   | -       | -           |
  | `file_size`    | `Optional[int]`   | -       | -           |
  | `file_data`    | `Optional[bytes]` | -       | -           |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### as\_bytes

  ```python theme={null}
  def as_bytes(self) -> 'bytes'
  ```

  **Returns:** `bytes`

  #### from\_bytes

  ```python theme={null}
  def from_bytes(cls, data: 'bytes', content_type: 'Optional[str]' = None, file_name: 'Optional[str]' = None, repository: 'FileRepository | RepositoryId' = 'fal_v3', fallback_repository: 'Optional[FileRepository | RepositoryId | list[FileRepository | RepositoryId]]' = ['fal'], request: 'Optional[Request]' = None, save_kwargs: 'Optional[dict]' = None, fallback_save_kwargs: 'Optional[dict]' = None) -> 'File'
  ```

  | Parameter              | Type                                                                                                                                                                                   | Default    | Description |
  | :--------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------- | :---------- |
  | `data`                 | `bytes`                                                                                                                                                                                | -          | -           |
  | `content_type`         | `Optional[str]`                                                                                                                                                                        | `None`     | -           |
  | `file_name`            | `Optional[str]`                                                                                                                                                                        | `None`     | -           |
  | `repository`           | `FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn]`                                                                                                      | `'fal_v3'` | -           |
  | `fallback_repository`  | `FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn] \| list[FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn]] \| NoneType` | `['fal']`  | -           |
  | `request`              | `Optional[Request]`                                                                                                                                                                    | `None`     | -           |
  | `save_kwargs`          | `Optional[dict]`                                                                                                                                                                       | `None`     | -           |
  | `fallback_save_kwargs` | `Optional[dict]`                                                                                                                                                                       | `None`     | -           |

  **Returns:** `File`

  #### from\_bytes\_async

  ```python theme={null}
  async def from_bytes_async(cls, data: 'bytes', content_type: 'Optional[str]' = None, file_name: 'Optional[str]' = None, repository: 'FileRepository | RepositoryId' = 'fal_v3', fallback_repository: 'Optional[FileRepository | RepositoryId | list[FileRepository | RepositoryId]]' = ['fal'], request: 'Optional[Request]' = None, save_kwargs: 'Optional[dict]' = None, fallback_save_kwargs: 'Optional[dict]' = None) -> 'File'
  ```

  | Parameter              | Type                                                                                                                                                                                   | Default    | Description |
  | :--------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------- | :---------- |
  | `data`                 | `bytes`                                                                                                                                                                                | -          | -           |
  | `content_type`         | `Optional[str]`                                                                                                                                                                        | `None`     | -           |
  | `file_name`            | `Optional[str]`                                                                                                                                                                        | `None`     | -           |
  | `repository`           | `FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn]`                                                                                                      | `'fal_v3'` | -           |
  | `fallback_repository`  | `FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn] \| list[FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn]] \| NoneType` | `['fal']`  | -           |
  | `request`              | `Optional[Request]`                                                                                                                                                                    | `None`     | -           |
  | `save_kwargs`          | `Optional[dict]`                                                                                                                                                                       | `None`     | -           |
  | `fallback_save_kwargs` | `Optional[dict]`                                                                                                                                                                       | `None`     | -           |

  **Returns:** `File`

  #### from\_path

  ```python theme={null}
  def from_path(cls, path: 'str | Path', content_type: 'Optional[str]' = None, repository: 'FileRepository | RepositoryId' = 'fal_v3', multipart: 'bool | None' = None, fallback_repository: 'Optional[FileRepository | RepositoryId | list[FileRepository | RepositoryId]]' = ['fal'], request: 'Optional[Request]' = None, save_kwargs: 'Optional[dict]' = None, fallback_save_kwargs: 'Optional[dict]' = None) -> 'File'
  ```

  | Parameter              | Type                                                                                                                                                                                   | Default    | Description |
  | :--------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------- | :---------- |
  | `path`                 | `str \| Path`                                                                                                                                                                          | -          | -           |
  | `content_type`         | `Optional[str]`                                                                                                                                                                        | `None`     | -           |
  | `repository`           | `FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn]`                                                                                                      | `'fal_v3'` | -           |
  | `multipart`            | `Optional[bool]`                                                                                                                                                                       | `None`     | -           |
  | `fallback_repository`  | `FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn] \| list[FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn]] \| NoneType` | `['fal']`  | -           |
  | `request`              | `Optional[Request]`                                                                                                                                                                    | `None`     | -           |
  | `save_kwargs`          | `Optional[dict]`                                                                                                                                                                       | `None`     | -           |
  | `fallback_save_kwargs` | `Optional[dict]`                                                                                                                                                                       | `None`     | -           |

  **Returns:** `File`

  #### from\_path\_async

  ```python theme={null}
  async def from_path_async(cls, path: 'str | Path', content_type: 'Optional[str]' = None, repository: 'FileRepository | RepositoryId' = 'fal_v3', multipart: 'bool | None' = None, fallback_repository: 'Optional[FileRepository | RepositoryId | list[FileRepository | RepositoryId]]' = ['fal'], request: 'Optional[Request]' = None, save_kwargs: 'Optional[dict]' = None, fallback_save_kwargs: 'Optional[dict]' = None) -> 'File'
  ```

  | Parameter              | Type                                                                                                                                                                                   | Default    | Description |
  | :--------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------- | :---------- |
  | `path`                 | `str \| Path`                                                                                                                                                                          | -          | -           |
  | `content_type`         | `Optional[str]`                                                                                                                                                                        | `None`     | -           |
  | `repository`           | `FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn]`                                                                                                      | `'fal_v3'` | -           |
  | `multipart`            | `Optional[bool]`                                                                                                                                                                       | `None`     | -           |
  | `fallback_repository`  | `FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn] \| list[FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn]] \| NoneType` | `['fal']`  | -           |
  | `request`              | `Optional[Request]`                                                                                                                                                                    | `None`     | -           |
  | `save_kwargs`          | `Optional[dict]`                                                                                                                                                                       | `None`     | -           |
  | `fallback_save_kwargs` | `Optional[dict]`                                                                                                                                                                       | `None`     | -           |

  **Returns:** `File`

  #### save

  ```python theme={null}
  def save(self, path: 'str | Path', overwrite: 'bool' = False) -> 'Path'
  ```

  | Parameter   | Type          | Default | Description |
  | :---------- | :------------ | :------ | :---------- |
  | `path`      | `str \| Path` | -       | -           |
  | `overwrite` | `bool`        | `False` | -           |

  **Returns:** `Path`

  #### save\_async

  ```python theme={null}
  async def save_async(self, path: 'str | Path', overwrite: 'bool' = False) -> 'Path'
  ```

  | Parameter   | Type          | Default | Description |
  | :---------- | :------------ | :------ | :---------- |
  | `path`      | `str \| Path` | -       | -           |
  | `overwrite` | `bool`        | `False` | -           |

  **Returns:** `Path`
</Accordion>

### Image

```python theme={null}
class fal.toolkit.Image
```

Represents an image file.

> **Inherits from:** `File`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name   | Type  | Default | Description |
  | :----- | :---- | :------ | :---------- |
  | `data` | `Any` | -       | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name     | Type            | Default | Description |
  | :------- | :-------------- | :------ | :---------- |
  | `width`  | `Optional[int]` | -       | -           |
  | `height` | `Optional[int]` | -       | -           |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### from\_bytes

  ```python theme={null}
  def from_bytes(cls, data: 'bytes', format: 'ImageFormat', size: 'ImageSize | None' = None, file_name: 'str | None' = None, repository: 'FileRepository | RepositoryId' = 'fal_v3', fallback_repository: 'Optional[FileRepository | RepositoryId | list[FileRepository | RepositoryId]]' = ['fal'], request: 'Optional[Request]' = None, save_kwargs: 'Optional[dict]' = None, fallback_save_kwargs: 'Optional[dict]' = None) -> 'Image'
  ```

  | Parameter              | Type                                                                                                                                                                                   | Default    | Description |
  | :--------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------- | :---------- |
  | `data`                 | `bytes`                                                                                                                                                                                | -          | -           |
  | `format`               | `Literal[png, jpeg, jpg, webp, gif]`                                                                                                                                                   | -          | -           |
  | `size`                 | `Optional[ImageSize]`                                                                                                                                                                  | `None`     | -           |
  | `file_name`            | `Optional[str]`                                                                                                                                                                        | `None`     | -           |
  | `repository`           | `FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn]`                                                                                                      | `'fal_v3'` | -           |
  | `fallback_repository`  | `FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn] \| list[FileRepository \| Literal[fal, fal_v2, fal_v3, in_memory, gcp_storage, r2, cdn]] \| NoneType` | `['fal']`  | -           |
  | `request`              | `Optional[Request]`                                                                                                                                                                    | `None`     | -           |
  | `save_kwargs`          | `Optional[dict]`                                                                                                                                                                       | `None`     | -           |
  | `fallback_save_kwargs` | `Optional[dict]`                                                                                                                                                                       | `None`     | -           |

  **Returns:** `Image`

  #### from\_pil

  ```python theme={null}
  def from_pil(cls, pil_image: 'PILImage.Image', format: 'ImageFormat | None' = None, file_name: 'str | None' = None, repository: 'FileRepository | RepositoryId' = 'fal_v3', fallback_repository: 'Optional[FileRepository | RepositoryId | list[FileRepository | RepositoryId]]' = ['fal'], request: 'Optional[Request]' = None, save_kwargs: 'Optional[dict]' = None, fallback_save_kwargs: 'Optional[dict]' = None) -> 'Image'
  ```

  | Parameter              | Type                                                                               | Default    | Description |
  | :--------------------- | :--------------------------------------------------------------------------------- | :--------- | :---------- |
  | `pil_image`            | `PILImage.Image`                                                                   | -          | -           |
  | `format`               | `ImageFormat \| None`                                                              | `None`     | -           |
  | `file_name`            | `str \| None`                                                                      | `None`     | -           |
  | `repository`           | `FileRepository \| RepositoryId`                                                   | `'fal_v3'` | -           |
  | `fallback_repository`  | `Optional[FileRepository \| RepositoryId \| list[FileRepository \| RepositoryId]]` | `['fal']`  | -           |
  | `request`              | `Optional[Request]`                                                                | `None`     | -           |
  | `save_kwargs`          | `Optional[dict]`                                                                   | `None`     | -           |
  | `fallback_save_kwargs` | `Optional[dict]`                                                                   | `None`     | -           |

  #### to\_pil

  ```python theme={null}
  def to_pil(self, mode: 'str' = 'RGB') -> 'PILImage.Image'
  ```

  | Parameter | Type  | Default | Description |
  | :-------- | :---- | :------ | :---------- |
  | `mode`    | `str` | `'RGB'` | -           |
</Accordion>

### ImageSizeConstraints

```python theme={null}
class fal.toolkit.ImageSizeConstraints
```

Advisory limits on the image size a model can generate. Attach to an `image_size` field via :func:`fal.toolkit.ImageSizeField` to
surface the model's size envelope in the OpenAPI schema (under the `x-fal`
extension), so clients and UIs can validate sizes before a request. These are
documentation hints and are not enforced by the SDK.

<Accordion title="Constructor Parameters" defaultOpen>
  | Name               | Type              | Default | Description |
  | :----------------- | :---------------- | :------ | :---------- |
  | `min_width`        | `Optional[int]`   | `None`  | -           |
  | `min_height`       | `Optional[int]`   | `None`  | -           |
  | `max_width`        | `Optional[int]`   | `None`  | -           |
  | `max_height`       | `Optional[int]`   | `None`  | -           |
  | `min_area`         | `Optional[int]`   | `None`  | -           |
  | `max_area`         | `Optional[int]`   | `None`  | -           |
  | `multiple_of`      | `Optional[int]`   | `None`  | -           |
  | `min_aspect_ratio` | `Optional[float]` | `None`  | -           |
  | `max_aspect_ratio` | `Optional[float]` | `None`  | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name               | Type              | Default | Description |
  | :----------------- | :---------------- | :------ | :---------- |
  | `min_width`        | `Optional[int]`   | `None`  | -           |
  | `min_height`       | `Optional[int]`   | `None`  | -           |
  | `max_width`        | `Optional[int]`   | `None`  | -           |
  | `max_height`       | `Optional[int]`   | `None`  | -           |
  | `min_area`         | `Optional[int]`   | `None`  | -           |
  | `max_area`         | `Optional[int]`   | `None`  | -           |
  | `multiple_of`      | `Optional[int]`   | `None`  | -           |
  | `min_aspect_ratio` | `Optional[float]` | `None`  | -           |
  | `max_aspect_ratio` | `Optional[float]` | `None`  | -           |
</Accordion>

### ImageValidationConfig

```python theme={null}
class fal.toolkit.ImageValidationConfig
```

Limits applied to an input image. Surfaced in the schema (`x-fal`); the SDK does not enforce them.

<Accordion title="Constructor Parameters" defaultOpen>
  | Name               | Type              | Default | Description |
  | :----------------- | :---------------- | :------ | :---------- |
  | `max_file_size`    | `Optional[int]`   | `None`  | -           |
  | `min_width`        | `Optional[int]`   | `None`  | -           |
  | `min_height`       | `Optional[int]`   | `None`  | -           |
  | `max_width`        | `Optional[int]`   | `None`  | -           |
  | `max_height`       | `Optional[int]`   | `None`  | -           |
  | `min_aspect_ratio` | `Optional[float]` | `None`  | -           |
  | `max_aspect_ratio` | `Optional[float]` | `None`  | -           |
  | `timeout`          | `float`           | `20.0`  | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name               | Type              | Default | Description |
  | :----------------- | :---------------- | :------ | :---------- |
  | `max_file_size`    | `Optional[int]`   | `None`  | -           |
  | `min_width`        | `Optional[int]`   | `None`  | -           |
  | `min_height`       | `Optional[int]`   | `None`  | -           |
  | `max_width`        | `Optional[int]`   | `None`  | -           |
  | `max_height`       | `Optional[int]`   | `None`  | -           |
  | `min_aspect_ratio` | `Optional[float]` | `None`  | -           |
  | `max_aspect_ratio` | `Optional[float]` | `None`  | -           |
  | `timeout`          | `float`           | `20.0`  | -           |
</Accordion>

### ImageValidationOptions

```python theme={null}
class fal.toolkit.ImageValidationOptions
```

Validation options accepted by input-image helpers.

> **Inherits from:** `dict`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name     | Type | Default | Description |
  | :------- | :--- | :------ | :---------- |
  | `args`   | -    | -       | -           |
  | `kwargs` | -    | -       | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name               | Type                                                                                                                    | Default | Description |
  | :----------------- | :---------------------------------------------------------------------------------------------------------------------- | :------ | :---------- |
  | `max_file_size`    | `ForwardRef('Optional[int]', module='fal.toolkit.constraints', owner=fal.toolkit.constraints.ImageValidationOptions)`   | -       | -           |
  | `min_width`        | `ForwardRef('Optional[int]', module='fal.toolkit.constraints', owner=fal.toolkit.constraints.ImageValidationOptions)`   | -       | -           |
  | `min_height`       | `ForwardRef('Optional[int]', module='fal.toolkit.constraints', owner=fal.toolkit.constraints.ImageValidationOptions)`   | -       | -           |
  | `max_width`        | `ForwardRef('Optional[int]', module='fal.toolkit.constraints', owner=fal.toolkit.constraints.ImageValidationOptions)`   | -       | -           |
  | `max_height`       | `ForwardRef('Optional[int]', module='fal.toolkit.constraints', owner=fal.toolkit.constraints.ImageValidationOptions)`   | -       | -           |
  | `min_aspect_ratio` | `ForwardRef('Optional[float]', module='fal.toolkit.constraints', owner=fal.toolkit.constraints.ImageValidationOptions)` | -       | -           |
  | `max_aspect_ratio` | `ForwardRef('Optional[float]', module='fal.toolkit.constraints', owner=fal.toolkit.constraints.ImageValidationOptions)` | -       | -           |
  | `timeout`          | `ForwardRef('Optional[float]', module='fal.toolkit.constraints', owner=fal.toolkit.constraints.ImageValidationOptions)` | -       | -           |
</Accordion>

### KVStore

```python theme={null}
class fal.toolkit.KVStore
```

A key-value store client for interacting with the FAL KV service.

<Accordion title="Constructor Parameters" defaultOpen>
  | Name      | Type  | Default | Description                                                  |
  | :-------- | :---- | :------ | :----------------------------------------------------------- |
  | `db_name` | `str` | -       | The name of the database/namespace to use for this KV store. |
</Accordion>

<Accordion title="Properties" defaultOpen>
  | Name           | Type             | Description |
  | :------------- | :--------------- | :---------- |
  | `auth_headers` | `dict[str, str]` | -           |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### delete

  ```python theme={null}
  def delete(self, key: str) -> None
  ```

  Delete a value from the key-value store. The operation is idempotent and succeeds whether or not the key
  existed.

  | Parameter | Type  | Default | Description        |
  | :-------- | :---- | :------ | :----------------- |
  | `key`     | `str` | -       | The key to delete. |

  **Returns:** `NoneType`

  #### get

  ```python theme={null}
  def get(self, key: str) -> str | None
  ```

  Retrieve a value from the key-value store.

  | Parameter | Type  | Default | Description                        |
  | :-------- | :---- | :------ | :--------------------------------- |
  | `key`     | `str` | -       | The key to retrieve the value for. |

  **Returns:** `Optional[str]`

  #### set

  ```python theme={null}
  def set(self, key: str, value: str, ttl: int | None = None) -> None
  ```

  Store a value in the key-value store.

  | Parameter | Type            | Default | Description                                                                                                   |
  | :-------- | :-------------- | :------ | :------------------------------------------------------------------------------------------------------------ |
  | `key`     | `str`           | -       | The key to store the value under.                                                                             |
  | `value`   | `str`           | -       | The value to store.                                                                                           |
  | `ttl`     | `Optional[int]` | `None`  | Optional time-to-live in seconds. Must be between 60 and 2592000 (30 days). Defaults to 30 days when omitted. |

  **Returns:** `NoneType`
</Accordion>

### Video

```python theme={null}
class fal.toolkit.Video
```

!!! abstract "Usage Documentation" [Models](../concepts/models.md)

A base class for creating Pydantic models.

> **Inherits from:** `File`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name   | Type  | Default | Description |
  | :----- | :---- | :------ | :---------- |
  | `data` | `Any` | -       | -           |
</Accordion>

### FalTookitException

```python theme={null}
class fal.toolkit.FalTookitException
```

Base exception for all toolkit exceptions

> **Inherits from:** `Exception`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name     | Type | Default | Description |
  | :------- | :--- | :------ | :---------- |
  | `args`   | -    | -       | -           |
  | `kwargs` | -    | -       | -           |
</Accordion>

### FileUploadException

```python theme={null}
class fal.toolkit.FileUploadException
```

Raised when file upload fails

> **Inherits from:** `FalTookitException`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name     | Type | Default | Description |
  | :------- | :--- | :------ | :---------- |
  | `args`   | -    | -       | -           |
  | `kwargs` | -    | -       | -           |
</Accordion>

### KVStoreException

```python theme={null}
class fal.toolkit.KVStoreException
```

Raised when KV store operation fails

> **Inherits from:** `FalTookitException`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name     | Type | Default | Description |
  | :------- | :--- | :------ | :---------- |
  | `args`   | -    | -       | -           |
  | `kwargs` | -    | -       | -           |
</Accordion>

### DownloadError

```python theme={null}
class fal.toolkit.DownloadError
```

Common base class for all non-exit exceptions.

> **Inherits from:** `Exception`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name     | Type | Default | Description |
  | :------- | :--- | :------ | :---------- |
  | `args`   | -    | -       | -           |
  | `kwargs` | -    | -       | -           |
</Accordion>

***

## Functions

### to\_xfal

```python theme={null}
def to_xfal(config: 'ImageSizeConstraints | ImageValidationConfig') -> 'dict[str, Any]'
```

Return a config's set (non-None) limits as the `x-fal` schema payload.

| Parameter | Type                                            | Default | Description |
| :-------- | :---------------------------------------------- | :------ | :---------- |
| `config`  | `ImageSizeConstraints \| ImageValidationConfig` | -       | -           |

**Returns:** `dict[str, Any]`

### Hidden

```python theme={null}
def Hidden(field: '_T') -> '_T'
```

Wrapper that marks a Field as hidden in the UI. The field MUST have a default or default\_factory set since hidden
fields cannot be required inputs in the UI.

Usage:
class Input(FalBaseModel):
prompt: str = Field(...)
hidden\_flag: bool = Hidden(Field(default=False))

| Parameter | Type | Default | Description                                          |
| :-------- | :--- | :------ | :--------------------------------------------------- |
| `field`   | `_T` | -       | A pydantic FieldInfo instance (result of Field(...)) |

**Returns:** `_T`

**Raises:**

* `ValueError`: If field has no default or default\_factory

### get\_image\_size

```python theme={null}
def get_image_size(source: 'ImageSizeInput') -> 'ImageSize'
```

| Parameter | Type                                                                                                  | Default | Description |
| :-------- | :---------------------------------------------------------------------------------------------------- | :------ | :---------- |
| `source`  | `ImageSize \| Literal[square_hd, square, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9]` | -       | -           |

**Returns:** `ImageSize`

### clone\_repository

```python theme={null}
def clone_repository(https_url: 'str', *, commit_hash: 'str | None' = None, target_dir: 'str | Path | None' = None, repo_name: 'str | None' = None, force: 'bool' = False, include_to_path: 'bool' = False) -> 'Path'
```

Clones a Git repository from the specified HTTPS URL into a local directory.

This function clones a Git repository from the specified HTTPS URL into a local
directory. It can also checkout a specific commit if the `commit_hash` is provided.

If a custom `target_dir` or `repo_name` is not specified, a predefined directory is
used for the target directory, and the repository name is determined from the URL.

| Parameter         | Type                      | Default | Description                                                                                                                                      |
| :---------------- | :------------------------ | :------ | :----------------------------------------------------------------------------------------------------------------------------------------------- |
| `https_url`       | `str`                     | -       | The HTTPS URL of the Git repository to be cloned.                                                                                                |
| `commit_hash`     | `Optional[str]`           | `None`  | The commit hash to checkout after cloning.                                                                                                       |
| `target_dir`      | `str \| Path \| NoneType` | `None`  | The directory where the repository will be saved. If not provided, a predefined directory is used.                                               |
| `repo_name`       | `Optional[str]`           | `None`  | The name to be used for the cloned repository directory. If not provided, the repository's name from the URL is used.                            |
| `force`           | `bool`                    | `False` | If `True`, the repository is cloned even if it already exists locally and its commit hash matches the provided commit hash. Defaults to `False`. |
| `include_to_path` | `bool`                    | `False` | If `True`, the cloned repository is added to the `sys.path`. Defaults to `False`.                                                                |

**Returns:** `Path`

### download\_file

```python theme={null}
def download_file(url: 'str', target_dir: 'str | Path', *, force: 'bool' = False, request_headers: 'dict[str, str] | None' = None, filesize_limit: 'int | None' = None) -> 'Path'
```

Downloads a file from the specified URL to the target directory. The function downloads the file from the given URL and saves it in the specified
target directory, provided it is below the given filesize limit.

If the downloaded response resolves to an existing local file whose content length
matches the downloaded file, the existing file is kept.

If the file needs to be downloaded or if an existing file's content length does not
match the expected length, the function proceeds to download and save the file. It
ensures that the target directory exists and handles any errors that may occur
during the download process, raising a `DownloadError` if necessary.

| Parameter         | Type                       | Default | Description                                                                                                                                      |
| :---------------- | :------------------------- | :------ | :----------------------------------------------------------------------------------------------------------------------------------------------- |
| `url`             | `str`                      | -       | The URL of the file to be downloaded.                                                                                                            |
| `target_dir`      | `str \| Path`              | -       | The directory where the downloaded file will be saved. If it's not an absolute path, it's treated as a relative directory to "/data".            |
| `force`           | `bool`                     | `False` | If `True`, the file is downloaded even if it already exists locally and its content length matches the downloaded response. Defaults to `False`. |
| `request_headers` | `Optional[dict[str, str]]` | `None`  | A dictionary containing additional headers to be included in the HTTP request. Defaults to `None`.                                               |
| `filesize_limit`  | `Optional[int]`            | `None`  | An integer specifying the maximum downloadable size, in megabytes. Defaults to `None`.                                                           |

**Returns:** `Path`

**Raises:**

* `DownloadError`: If an error occurs during the download process.

### download\_model\_weights

```python theme={null}
def download_model_weights(url: 'str', force: 'bool' = False, request_headers: 'dict[str, str] | None' = None) -> 'Path'
```

Downloads model weights from the specified URL and saves them to a predefined directory.

This function is specifically designed for downloading model weights and stores
them in a predefined directory.

It calls the `download_file` function with the provided
URL and the target directory set to a pre-defined location for model weights.
The downloaded model weights are saved in this directory, and the function returns
the full path to the downloaded weights file.

| Parameter         | Type                       | Default | Description                                                                                                                                                                            |
| :---------------- | :------------------------- | :------ | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `url`             | `str`                      | -       | The URL from which the model weights will be downloaded.                                                                                                                               |
| `force`           | `bool`                     | `False` | If `True`, the model weights are downloaded even if they already exist locally and their content length matches the expected content length from the remote file. Defaults to `False`. |
| `request_headers` | `Optional[dict[str, str]]` | `None`  | A dictionary containing additional headers to be included in the HTTP request. Defaults to `None`.                                                                                     |

**Returns:** `Path`

### get\_gpu\_type

```python theme={null}
def get_gpu_type() -> 'str'
```

Detect the GPU type using nvidia-smi.

**Example:**

```python theme={null}
>>> gpu_type = get_gpu_type()
>>> print(f"Running on: {gpu_type}")
Running on: H100
```

**Returns:** `str`

### load\_inductor\_cache

```python theme={null}
def load_inductor_cache(cache_key: 'str') -> 'str'
```

Load PyTorch Inductor compilation cache from global storage. This function:

1. Sets TORCHINDUCTOR\_CACHE\_DIR environment variable
2. Looks for cached compiled kernels in GPU-specific global storage
3. Unpacks the cache to local temporary directory
4. Returns a hash of the unpacked directory for change detection

**Example:**

```python theme={null}
>>> dir_hash = load_inductor_cache("flux/2")
Found compilation cache at /data/inductor-caches/H100/flux/2.zip, unpacking...
Cache unpacked successfully.
```

| Parameter   | Type  | Default | Description                                                     |
| :---------- | :---- | :------ | :-------------------------------------------------------------- |
| `cache_key` | `str` | -       | Unique identifier for this cache (e.g., "flux/2", "mymodel/v1") |

**Returns:** `str`

### sync\_inductor\_cache

```python theme={null}
def sync_inductor_cache(cache_key: 'str', unpacked_dir_hash: 'str') -> 'None'
```

Sync updated PyTorch Inductor cache back to global storage. This function:

1. Checks if the local cache has changed (by comparing hashes)
2. If changed, creates a zip archive of the new cache
3. Saves it to GPU-specific global storage

**Example:**

```python theme={null}
>>> sync_inductor_cache("flux/2", dir_hash)
No changes in the cache dir, skipping sync.
# or
Changes detected in the cache dir, syncing...
```

| Parameter           | Type  | Default | Description                                                              |
| :------------------ | :---- | :------ | :----------------------------------------------------------------------- |
| `cache_key`         | `str` | -       | Unique identifier for this cache (same as used in load\_inductor\_cache) |
| `unpacked_dir_hash` | `str` | -       | Hash returned from load\_inductor\_cache (for change detection)          |

**Returns:** `NoneType`

### synchronized\_inductor\_cache

```python theme={null}
def synchronized_inductor_cache(cache_key: 'str') -> 'Iterator[None]'
```

Context manager to automatically load and sync PyTorch Inductor cache. This wraps load\_inductor\_cache and sync\_inductor\_cache for convenience.
The cache is loaded on entry and synced on exit (even if an exception occurs).

**Example:**

```python theme={null}
>>> with synchronized_inductor_cache("mymodel/v1"):
...     self.model = torch.compile(self.model)
...     self.warmup()  # Compilation happens here
# Cache is automatically synced after the with block
```

| Parameter   | Type  | Default | Description                                                     |
| :---------- | :---- | :------ | :-------------------------------------------------------------- |
| `cache_key` | `str` | -       | Unique identifier for this cache (e.g., "flux/2", "mymodel/v1") |

**Returns:** `Iterator[]`
