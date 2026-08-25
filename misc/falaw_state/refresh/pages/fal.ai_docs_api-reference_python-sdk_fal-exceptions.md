> ## Documentation Index
> Fetch the complete documentation index at: https://fal.ai/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# fal.exceptions

> API reference for fal.exceptions

```python theme={null}
from fal.exceptions import (
    FalServerlessException,
    AppException,
    FieldException,
    RequestCancelledException,
    FileTooLargeError,
    AppFileUploadException,
    GPUException,
    GPUOutOfMemoryException,
    CUDAOutOfMemoryException,
    UnauthenticatedException,
    catch_gpu_exceptions,
)
```

## Classes

### FalServerlessException

```python theme={null}
class fal.exceptions.FalServerlessException
```

Base exception type for fal Serverless related flows and APIs.

> **Inherits from:** `Exception`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name     | Type | Default | Description |
  | :------- | :--- | :------ | :---------- |
  | `args`   | -    | -       | -           |
  | `kwargs` | -    | -       | -           |
</Accordion>

### AppException

```python theme={null}
class fal.exceptions.AppException
```

Base exception class for application-specific errors.

> **Inherits from:** `FalServerlessException`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name          | Type  | Default | Description                                     |
  | :------------ | :---- | :------ | :---------------------------------------------- |
  | `message`     | `str` | -       | A descriptive message explaining the error.     |
  | `status_code` | `int` | -       | The HTTP status code associated with the error. |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name          | Type  | Default | Description                                     |
  | :------------ | :---- | :------ | :---------------------------------------------- |
  | `message`     | `str` | -       | A descriptive message explaining the error.     |
  | `status_code` | `int` | -       | The HTTP status code associated with the error. |
</Accordion>

### FieldException

```python theme={null}
class fal.exceptions.FieldException
```

Exception raised for errors related to specific fields.

> **Inherits from:** `FalServerlessException`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name             | Type                              | Default         | Description                                                     |
  | :--------------- | :-------------------------------- | :-------------- | :-------------------------------------------------------------- |
  | `field`          | `str`                             | -               | The field that caused the error.                                |
  | `message`        | `str`                             | -               | A descriptive message explaining the error.                     |
  | `status_code`    | `int`                             | `422`           | The HTTP status code associated with the error. Defaults to 422 |
  | `type`           | `str`                             | `'value_error'` | The type of error. Defaults to "value\_error"                   |
  | `billable_units` | `int \| float \| str \| NoneType` | `0`             | -                                                               |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name             | Type                          | Default         | Description                                                     |
  | :--------------- | :---------------------------- | :-------------- | :-------------------------------------------------------------- |
  | `field`          | `str`                         | -               | The field that caused the error.                                |
  | `message`        | `str`                         | -               | A descriptive message explaining the error.                     |
  | `status_code`    | `int`                         | `422`           | The HTTP status code associated with the error. Defaults to 422 |
  | `type`           | `str`                         | `'value_error'` | The type of error. Defaults to "value\_error"                   |
  | `billable_units` | `int \| float \| str \| None` | `0`             | -                                                               |
</Accordion>

<Accordion title="Methods" defaultOpen>
  #### to\_pydantic\_format

  ```python theme={null}
  def to_pydantic_format(self) -> 'dict[str, list[dict]]'
  ```

  **Returns:** `dict[str, list[dict]]`
</Accordion>

### RequestCancelledException

```python theme={null}
class fal.exceptions.RequestCancelledException
```

Exception raised when the request is cancelled by the client.

> **Inherits from:** `FalServerlessException`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name      | Type  | Default                              | Description |
  | :-------- | :---- | :----------------------------------- | :---------- |
  | `message` | `str` | `'Request cancelled by the client.'` | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name      | Type  | Default                              | Description |
  | :-------- | :---- | :----------------------------------- | :---------- |
  | `message` | `str` | `'Request cancelled by the client.'` | -           |
</Accordion>

### FileTooLargeError

```python theme={null}
class fal.exceptions.FileTooLargeError
```

Exception raised when the file is too large.

> **Inherits from:** `FalServerlessException`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name      | Type  | Default                | Description |
  | :-------- | :---- | :--------------------- | :---------- |
  | `message` | `str` | `'File is too large.'` | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name      | Type  | Default                | Description |
  | :-------- | :---- | :--------------------- | :---------- |
  | `message` | `str` | `'File is too large.'` | -           |
</Accordion>

### AppFileUploadException

```python theme={null}
class fal.exceptions.AppFileUploadException
```

Raised when file upload fails

> **Inherits from:** `FalServerlessException`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name            | Type  | Default | Description |
  | :-------------- | :---- | :------ | :---------- |
  | `message`       | `str` | -       | -           |
  | `relative_path` | `str` | -       | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name            | Type  | Default | Description |
  | :-------------- | :---- | :------ | :---------- |
  | `message`       | `str` | -       | -           |
  | `relative_path` | `str` | -       | -           |
</Accordion>

### GPUException

```python theme={null}
class fal.exceptions.GPUException
```

Base exception for GPU-related errors.

> **Inherits from:** `AppException`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name          | Type  | Default       | Description |
  | :------------ | :---- | :------------ | :---------- |
  | `message`     | `str` | `'GPU error'` | -           |
  | `status_code` | `int` | `503`         | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name          | Type  | Default       | Description |
  | :------------ | :---- | :------------ | :---------- |
  | `message`     | `str` | `'GPU error'` | -           |
  | `status_code` | `int` | `503`         | -           |
</Accordion>

### GPUOutOfMemoryException

```python theme={null}
class fal.exceptions.GPUOutOfMemoryException
```

Exception raised when a GPU operation runs out of memory.

> **Inherits from:** `GPUException`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name          | Type  | Default       | Description |
  | :------------ | :---- | :------------ | :---------- |
  | `message`     | `str` | `'GPU error'` | -           |
  | `status_code` | `int` | `503`         | -           |
</Accordion>

### CUDAOutOfMemoryException

```python theme={null}
class fal.exceptions.CUDAOutOfMemoryException
```

Exception raised when a CUDA operation runs out of memory.

> **Inherits from:** `GPUOutOfMemoryException`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name          | Type  | Default                       | Description |
  | :------------ | :---- | :---------------------------- | :---------- |
  | `message`     | `str` | `'CUDA error: out of memory'` | -           |
  | `status_code` | `int` | `503`                         | -           |
</Accordion>

<Accordion title="Class Variables" defaultOpen>
  | Name      | Type  | Default                       | Description |
  | :-------- | :---- | :---------------------------- | :---------- |
  | `message` | `str` | `'CUDA error: out of memory'` | -           |
</Accordion>

### UnauthenticatedException

```python theme={null}
class fal.exceptions.UnauthenticatedException
```

Base exception type for fal Serverless related flows and APIs.

> **Inherits from:** `FalServerlessException`

### catch\_gpu\_exceptions

```python theme={null}
class fal.exceptions.catch_gpu_exceptions
```

Catch GPU/CUDA exceptions and convert them to HTTP 503 responses. Works as both a context manager and a decorator. Any caught GPU
exception (CUDA OOM, cuDNN errors, NVML failures, etc.) is
re-raised as a GPU exception with HTTP status 503.

**Example:**

```python theme={null}
from fal.exceptions import catch_gpu_exceptions

with catch_gpu_exceptions():
    run_inference()


@catch_gpu_exceptions()
def run_inference(): ...
```

> **Inherits from:** `ContextDecorator`

<Accordion title="Constructor Parameters" defaultOpen>
  | Name     | Type | Default | Description |
  | :------- | :--- | :------ | :---------- |
  | `args`   | -    | -       | -           |
  | `kwargs` | -    | -       | -           |
</Accordion>
