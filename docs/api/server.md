# Server API

The Server Service API documentation is automatically generated from the FastAPI application using OpenAPI specifications.

## Live API Documentation

!!! info "Interactive API Docs"
    The Server Service provides **three** auto-generated API documentation interfaces:

### 1. Swagger UI (Recommended)

**Best for**: Interactive exploration and testing

<iframe src="http://localhost:8001/docs" width="100%" height="600px" style="border: 1px solid #ddd; border-radius: 4px;"></iframe>

**Direct Link**: [http://localhost:8001/docs](http://localhost:8001/docs)

!!! tip "Replace `localhost:8001`"
    Change `localhost:8001` to your actual server endpoint (e.g., `mel2106:8001`)

### 2. ReDoc

**Best for**: Reading documentation and reference

<iframe src="http://localhost:8001/redoc" width="100%" height="600px" style="border: 1px solid #ddd; border-radius: 4px;"></iframe>

**Direct Link**: [http://localhost:8001/redoc](http://localhost:8001/redoc)

### 3. OpenAPI JSON

**Best for**: Generating client SDKs, importing to tools

**Direct Link**: [http://localhost:8001/openapi.json](http://localhost:8001/openapi.json)

## Quick Start

### Access the Documentation

1. **Start the server**:
   ```bash
   cd services/server
   ./launch_server.sh
   ```

2. **Get the endpoint**:
   ```bash
   # The script will output something like:
   # API Docs: http://mel2106:8001/docs
   ```

3. **Open in browser**:
   - Visit the URL shown in the terminal
   - Try the interactive examples

### Features

The interactive API documentation provides:

✅ **Try It Out** - Execute requests directly from the browser  
✅ **Schema Validation** - See required fields and data types  
✅ **Example Values** - Pre-filled request bodies  
✅ **Authentication** - Test with credentials (when implemented)  
✅ **Response Codes** - See all possible responses  
✅ **Download** - Export OpenAPI spec for tooling  

## Using the OpenAPI Specification

### Generate Client SDK

```bash
# Python client
pip install openapi-generator-cli
openapi-generator generate \
  -i http://mel2106:8001/openapi.json \
  -g python \
  -o ./ai-factory-client

# TypeScript/JavaScript client
openapi-generator generate \
  -i http://mel2106:8001/openapi.json \
  -g typescript-fetch \
  -o ./ai-factory-client-ts
```

### Import to Postman

1. Open Postman
2. Click "Import"
3. Enter URL: `http://mel2106:8001/openapi.json`
4. Click "Import"

### Import to Insomnia

1. Open Insomnia
2. Click "Create" → "Import"
3. Enter URL: `http://mel2106:8001/openapi.json`
4. Click "Fetch and Import"

## API Overview

For a comprehensive guide with examples, see the [API Reference](../services/server/api-reference.md).

### Endpoint Categories

| Category | Description | Endpoints |
|----------|-------------|-----------|
| **Health** | Health checks | `/health` |
| **Services** | Service lifecycle | `/api/v1/services/*` |
| **Recipes** | Template management | `/api/v1/recipes/*` |
| **vLLM** | LLM operations | `/api/v1/vllm/*` |

### Quick Examples

**Create a Service:**
```bash
curl -X POST "http://mel2106:8001/api/v1/services" \
  -H "Content-Type: application/json" \
  -d '{"recipe_name": "inference/vllm"}'
```

**Check Status:**
```bash
curl "http://mel2106:8001/api/v1/services/3614523/status"
```

**Send Prompt:**
```bash
curl -X POST "http://mel2106:8001/api/v1/vllm/3614523/prompt" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello, AI!"}'
```

## Updating Documentation

The API documentation is **automatically generated** from code annotations. To update:

1. **Update docstrings** in `services/server/src/api/routes.py`
2. **Restart the server**
3. **Refresh** the `/docs` page

Example:
```python
@router.post("/services", response_model=ServiceResponse)
async def create_service(request: ServiceRequest):
    """Create and start a new service.
    
    This endpoint submits a job to SLURM using a recipe template.
    
    Args:
        request: Service configuration with recipe name and config
        
    Returns:
        Service object with job ID and status
        
    Raises:
        HTTPException: If recipe not found or SLURM error
    """
    ...
```

## Troubleshooting

### Docs Not Loading

**Issue**: iframe shows "Connection refused"

**Solution**: 
1. Verify server is running: `curl http://mel2106:8001/health`
2. Update iframe src to correct endpoint
3. Check browser console for CORS errors

### Embedded Docs Not Working

If the embedded iframes don't work (CORS/network restrictions):

**Use Direct Links Instead:**
- Swagger UI: http://&lt;server&gt;:8001/docs
- ReDoc: http://&lt;server&gt;:8001/redoc
- OpenAPI: http://&lt;server&gt;:8001/openapi.json

## Additional Resources

- [Full API Reference](../services/server/api-reference.md) - Detailed endpoint documentation
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - FastAPI framework docs
- [OpenAPI Specification](https://swagger.io/specification/) - OpenAPI standard

---

!!! note "Auto-Generated"
    This documentation is auto-generated from the FastAPI application.
    It's always up-to-date with the latest code changes.
