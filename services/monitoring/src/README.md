# Monitoring Service - Source Code

This directory contains the refactored monitoring service following the same architecture pattern as the server service.

## Structure

```
src/
├── main.py                 # FastAPI application entry point
├── monitoring_service.py   # Core MonitoringService class
├── api/
│   ├── __init__.py
│   ├── routes.py          # API route definitions
│   └── schemas.py         # Pydantic models for requests/responses
├── config/                # Prometheus config rendering
├── core/                  # Core utilities (state store, etc.)
├── managers/              # External service managers (SLURM, Prometheus)
├── metrics/               # Metrics collection and aggregation
└── registry/              # Target registry for exporters and services
```

## Architecture

The monitoring service follows the same pattern as the server service:

1. **main.py** - FastAPI application with:
   - Application initialization
   - Middleware configuration
   - Route registration
   - Shutdown handlers

2. **monitoring_service.py** - Core business logic with:
   - Session lifecycle management
   - Target registration
   - Metrics collection

3. **api/** - FastAPI-specific code:
   - **routes.py** - Endpoint definitions with OpenAPI documentation
   - **schemas.py** - Pydantic models for validation and serialization

## Running the Service

### Development Mode

```bash
cd services/monitoring/src
python main.py
```

The service will start on port 8005 with:
- API documentation at http://localhost:8005/docs
- ReDoc at http://localhost:8005/redoc
- Health check at http://localhost:8005/health

### Production Mode

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8005
```

## API Endpoints

### Session Lifecycle
- `POST /api/v1/sessions` - Create a new monitoring session
- `POST /api/v1/sessions/{session_id}/start` - Start Prometheus via SLURM
- `GET /api/v1/sessions/{session_id}/status` - Get session status
- `POST /api/v1/sessions/{session_id}/stop` - Stop a monitoring session
- `DELETE /api/v1/sessions/{session_id}` - Delete a session

### Target Registration
- `POST /api/v1/clients` - Register a client with exporters
- `POST /api/v1/services` - Register a service endpoint

### Metrics Collection
- `POST /api/v1/sessions/{session_id}/collect` - Collect metrics for a time window

## Migration from Old Structure

The old `main.py` in the parent directory has been deprecated. Update imports:

```python
# Old
from services.monitoring.main import MonitoringService

# New
from services.monitoring.src.monitoring_service import MonitoringService
```

## Dependencies

The service depends on:
- FastAPI for the REST API
- Pydantic for request/response validation
- Prometheus for metrics collection
- SLURM for job orchestration
