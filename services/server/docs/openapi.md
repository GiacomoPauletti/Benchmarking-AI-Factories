# AI Factory Server Service 1.0.0

SLURM + Apptainer orchestration for AI workloads

## Paths

### `/`

#### GET

**Summary:** Root


Root endpoint with service information.


**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`



### `/api/v1/recipes`

#### GET

**Summary:** List Recipes


List all available recipes.


**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`

    ```json

{
  "items": {
    "$ref": "#/components/schemas/RecipeResponse"
  },
  "type": "array",
  "title": "Response List Recipes Api V1 Recipes Get"
}

    ```



### `/api/v1/recipes/{recipe_name}`

#### GET

**Summary:** Get Recipe


Get details of a specific recipe.


**Parameters:**


| name | in | required | schema | description |

|---|---|---:|---|---|

| recipe_name | path | True | `{<br>  "type": "string",<br>  "title": "Recipe Name"<br>}` |  |



**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/RecipeResponse"
}

    ```

- **422**: Validation Error

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/HTTPValidationError"
}

    ```



### `/api/v1/services`

#### GET

**Summary:** List Services


List all running services.


**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`

    ```json

{
  "items": {
    "$ref": "#/components/schemas/ServiceResponse"
  },
  "type": "array",
  "title": "Response List Services Api V1 Services Get"
}

    ```



#### POST

**Summary:** Create Service


Create and start a new service using SLURM + Apptainer.


**Request Body:**


- Content-Type: `application/json`

```json

{
  "$ref": "#/components/schemas/ServiceRequest"
}

```


**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/ServiceResponse"
}

    ```

- **422**: Validation Error

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/HTTPValidationError"
}

    ```



### `/api/v1/services/{service_id}`

#### DELETE

**Summary:** Stop Service


Stop a running service by cancelling the SLURM job.


**Parameters:**


| name | in | required | schema | description |

|---|---|---:|---|---|

| service_id | path | True | `{<br>  "type": "string",<br>  "title": "Service Id"<br>}` |  |



**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`

- **422**: Validation Error

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/HTTPValidationError"
}

    ```



#### GET

**Summary:** Get Service


Get details of a specific service.


**Parameters:**


| name | in | required | schema | description |

|---|---|---:|---|---|

| service_id | path | True | `{<br>  "type": "string",<br>  "title": "Service Id"<br>}` |  |



**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/ServiceResponse"
}

    ```

- **422**: Validation Error

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/HTTPValidationError"
}

    ```



### `/api/v1/services/{service_id}/logs`

#### GET

**Summary:** Get Service Logs


Get logs from a service.


**Parameters:**


| name | in | required | schema | description |

|---|---|---:|---|---|

| service_id | path | True | `{<br>  "type": "string",<br>  "title": "Service Id"<br>}` |  |



**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`

- **422**: Validation Error

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/HTTPValidationError"
}

    ```



### `/api/v1/services/{service_id}/status`

#### GET

**Summary:** Get Service Status


Get current status of a service.


**Parameters:**


| name | in | required | schema | description |

|---|---|---:|---|---|

| service_id | path | True | `{<br>  "type": "string",<br>  "title": "Service Id"<br>}` |  |



**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`

- **422**: Validation Error

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/HTTPValidationError"
}

    ```



### `/api/v1/vllm/services`

#### GET

**Summary:** List Vllm Services


List all running VLLM services.


**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`



### `/api/v1/vllm/{service_id}/models`

#### GET

**Summary:** Get Vllm Models


Get available models served by a running VLLM service.


**Parameters:**


| name | in | required | schema | description |

|---|---|---:|---|---|

| service_id | path | True | `{<br>  "type": "string",<br>  "title": "Service Id"<br>}` |  |



**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`

- **422**: Validation Error

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/HTTPValidationError"
}

    ```



### `/api/v1/vllm/{service_id}/prompt`

#### POST

**Summary:** Prompt Vllm Service


Send a prompt to a running VLLM service.


**Parameters:**


| name | in | required | schema | description |

|---|---|---:|---|---|

| service_id | path | True | `{<br>  "type": "string",<br>  "title": "Service Id"<br>}` |  |



**Request Body:**


- Content-Type: `application/json`

```json

{
  "type": "object",
  "additionalProperties": true,
  "title": "Request"
}

```


**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`

- **422**: Validation Error

  - Content-Type: `application/json`

    ```json

{
  "$ref": "#/components/schemas/HTTPValidationError"
}

    ```



### `/health`

#### GET

**Summary:** Health


Health check endpoint.


**Responses:**


- **200**: Successful Response

  - Content-Type: `application/json`


