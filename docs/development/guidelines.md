# Development Guidelines

## AI Benchmarking Application - Development Reference

This guide provides development standards and best practices for contributing to the AI Factory Benchmarking Framework.

## Development Principles

### 1. Single Responsibility
Each service owns one capability and does it well. Don't create monolithic services.

✅ **Good**: Server Service handles service deployment only  
❌ **Bad**: Server Service handles deployment + monitoring + logging

### 2. Decoupled Communication
Services communicate via well-defined REST APIs. No direct database access across services.

✅ **Good**: Client calls Server API to get service list  
❌ **Bad**: Client queries Server's database directly

### 3. Data Independence
Each service manages its own database/storage. No shared databases.

✅ **Good**: Each service has its own data store  
❌ **Bad**: Multiple services write to same database

### 4. Failure Isolation
Service failures don't cascade to others. Implement circuit breakers and timeouts.

✅ **Good**: Server down? Client handles gracefully  
❌ **Bad**: Server down = entire system crashes

### 5. Technology Agnostic
Choose the best tech stack for each service's needs.

✅ **Good**: Server in Python, Logs in Rust  
❌ **Bad**: Force everything into one language

## Git Workflow

### Branch Strategy

```
main (production)
  ↑
dev (integration)
  ↑
feature/server/vllm-improvements (your work)
```

**Branches**:
- `main` - Production-ready, always deployable, protected
- `dev` - Integration branch for team collaboration
- `feature/*` - Individual feature development

### Branch Naming

Use descriptive names:
```bash
feature/service-name/description
feature/server/add-vllm-support
feature/client/benchmark-throughput
feature/monitor/prometheus-exporter

bugfix/service-name/description
bugfix/server/fix-slurm-token
```

### Commit Messages

Follow conventional commits:

```bash
# Format
<type>(<scope>): <subject>

# Examples
feat(server): add vLLM recipe support
fix(client): resolve connection timeout
docs(readme): update installation guide
test(server): add integration tests for recipes
refactor(monitor): improve metrics collection
```

**Types**:
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `test` - Tests
- `refactor` - Code refactoring
- `chore` - Maintenance tasks

### Pull Request Workflow

1. **Create feature branch**
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feature/server/my-feature
   ```

2. **Make changes and commit**
   ```bash
   git add .
   git commit -m "feat(server): add my feature"
   git push origin feature/server/my-feature
   ```

3. **Create Pull Request**
   - Feature branch → `dev` (for integration testing)
   - Include description of changes
   - Add reviewers
   - Link related issues

4. **Code Review**
   - Address reviewer comments
   - Update PR
   - Get approval

5. **Merge**
   - Squash and merge to `dev`
   - Delete feature branch
   - Later: `dev` → `main` for production release

### Branch Protection

Both `main` and `dev` branches require:
- ✅ Code review approval
- ✅ Automated tests pass
- ✅ No merge conflicts
- ❌ No direct commits

## Code Standards

### Python (Server, Client, Monitor)

**Style Guide**: PEP 8

```python
# Good
def create_service(recipe_name: str, config: dict) -> Service:
    """Create and start a new service.
    
    Args:
        recipe_name: Name of the recipe to use
        config: Service configuration
        
    Returns:
        Service object with job ID and status
    """
    pass

# Bad
def createService(recipeName,config):
    pass
```

**Type Hints**: Always use type hints

```python
# Good
from typing import List, Dict, Optional

def get_services() -> List[Dict[str, Any]]:
    pass

# Bad
def get_services():
    pass
```

**Error Handling**: Explicit and informative

```python
# Good
try:
    service = load_recipe(recipe_name)
except RecipeNotFoundError as e:
    logger.error(f"Recipe not found: {recipe_name}")
    raise HTTPException(status_code=404, detail=str(e))

# Bad
try:
    service = load_recipe(recipe_name)
except:
    pass
```

### Rust (Logs Service)

**Style Guide**: Rustfmt + Clippy

```rust
// Good
pub fn collect_logs(job_id: &str) -> Result<Vec<String>, LogError> {
    // Implementation
}

// Bad
pub fn collect_logs(job_id:&str)->Vec<String>{
    // Implementation
}
```

### API Design

**RESTful Conventions**:

```bash
# Good
GET    /api/v1/services          # List all
POST   /api/v1/services          # Create
GET    /api/v1/services/{id}     # Get one
DELETE /api/v1/services/{id}     # Delete
GET    /api/v1/services/{id}/status  # Sub-resource

# Bad
GET    /api/v1/get-services
POST   /api/v1/create-service
GET    /api/v1/service?id=123
```

**Response Format**:

```json
// Good - Consistent structure
{
  "id": "3614523",
  "name": "vllm-3614523",
  "status": "running",
  "created_at": "2025-10-14T12:00:00"
}

// Bad - Inconsistent
{
  "jobID": 3614523,
  "ServiceName": "vllm",
  "State": 1
}
```

## Testing

### Test Structure

```
tests/
├── unit/           # Unit tests (fast, isolated)
├── integration/    # Integration tests (API endpoints)
└── e2e/           # End-to-end tests (full workflows)
```

### Unit Tests

Test individual functions in isolation:

```python
def test_load_recipe():
    """Test recipe loading from YAML."""
    recipe = load_recipe("inference/vllm")
    assert recipe.name == "vllm"
    assert recipe.resources.gpu == 1
```

### Integration Tests

Test API endpoints:

```python
def test_create_service_endpoint(client):
    """Test POST /api/v1/services endpoint."""
    response = client.post("/api/v1/services", json={
        "recipe_name": "inference/vllm"
    })
    assert response.status_code == 200
    assert "id" in response.json()
```

### Test Coverage

Aim for:
- ✅ 80%+ unit test coverage
- ✅ All API endpoints have integration tests
- ✅ Critical paths have e2e tests

Run tests before committing:

```bash
cd services/server
./run-tests.sh
```

## Documentation

### Code Documentation

**Docstrings**: All public functions

```python
def start_service(recipe_name: str, config: dict) -> Service:
    """Create and start a new service using SLURM + Apptainer.
    
    This function loads a recipe template, merges user configuration,
    submits a SLURM job, and returns the service object.
    
    Args:
        recipe_name: Path to recipe (e.g., "inference/vllm")
        config: User configuration to override recipe defaults
        
    Returns:
        Service object containing:
        - id: SLURM job ID
        - name: Service name
        - status: Current status
        - config: Merged configuration
        
    Raises:
        RecipeNotFoundError: If recipe doesn't exist
        SlurmError: If job submission fails
        
    Example:
        >>> service = start_service("inference/vllm", {
        ...     "environment": {"VLLM_MODEL": "gpt2"}
        ... })
        >>> print(service.id)
        3614523
    """
    pass
```

**API Documentation**: FastAPI auto-generates from docstrings

```python
@router.post("/services", response_model=ServiceResponse)
async def create_service(request: ServiceRequest):
    """Create and start a new service.
    
    This endpoint submits a job to SLURM using a recipe template.
    
    **Request Body:**
    - recipe_name: Recipe path
    - config: Configuration overrides
    
    **Returns:**
    - Service object with job ID and status
    """
    pass
```

### README Files

Each service should have:
- `README.md` - Overview and usage
- `docs/` - Detailed documentation

## CI/CD Pipeline

### Automated Checks

On every pull request:
1. ✅ Linting (pylint, flake8)
2. ✅ Type checking (mypy)
3. ✅ Unit tests
4. ✅ Integration tests
5. ✅ Build containers

### Deployment Pipeline

```mermaid
graph LR
    PR[Pull Request] --> Tests[Run Tests]
    Tests --> Review[Code Review]
    Review --> Merge[Merge to dev]
    Merge --> Build[Build Containers]
    Build --> Deploy[Deploy to Dev]
    Deploy --> E2E[E2E Tests]
    E2E --> Prod[Release to Main]
```

## Team Collaboration

### Service Ownership

Each team member owns a primary service:

| Member | Service | Responsibilities |
|--------|---------|------------------|
| TBD | Server | API, SLURM integration, recipes |
| TBD | Client | Benchmarks, workload generation |
| TBD | Monitor | Metrics, Prometheus |
| TBD | Logs | Log aggregation, Loki |

### Cross-Training

- Weekly knowledge sharing sessions
- Rotate code reviews across services
- Pair programming for complex features

### Communication

- **Daily**: Async updates in team chat
- **Weekly**: Sync meeting for blockers
- **Bi-weekly**: Architecture reviews

## Development Setup

### Local Environment

```bash
# Clone repo
git clone https://github.com/GiacomoPauletti/Benchmarking-AI-Factories.git
cd Benchmarking-AI-Factories

# Set up Python environment
python -m venv venv
source venv/bin/activate
pip install -r services/server/requirements.txt

# Run tests
cd services/server
./run-tests.sh
```

### MeluXina Setup

```bash
# Load modules
module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0

# Set environment
export SERVER_BASE_PATH="$(pwd)/services/server"

# Build containers
cd services/server
apptainer build server.sif server.def
```

## Best Practices

### Security

- ✅ Never commit secrets or tokens
- ✅ Use environment variables for config
- ✅ Validate all API inputs
- ✅ Sanitize user-provided data

### Performance

- ✅ Use async/await for I/O operations
- ✅ Implement caching where appropriate
- ✅ Profile before optimizing
- ✅ Monitor resource usage

### Error Handling

- ✅ Fail fast with clear error messages
- ✅ Log errors with context
- ✅ Return appropriate HTTP status codes
- ✅ Don't expose internal errors to users

### Logging

```python
# Good - Structured logging
logger.info("Service created", extra={
    "service_id": service.id,
    "recipe": recipe_name,
    "user": user_id
})

# Bad - Unstructured
print(f"Created service {service.id}")
```

## Resources

- [Project README](../../README.md)
- [Architecture Overview](../architecture/overview.md)
- [API Reference](../services/server/api-reference.md)
- [Testing Guide](testing.md)

---

**Remember**: Start simple, iterate fast, and maintain service boundaries. Focus on getting the basics right before optimizing!
