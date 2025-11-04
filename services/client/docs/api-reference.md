````markdown
# AI Factory Client Services - API Reference

## 📋 API Overview

The AI Factory Client Services system exposes three main API sets:

1. **Frontend API** - Client group management and orchestration
2. **Client Registration API** - Client process registration
3. **Monitor API** - Monitoring and observability system

All APIs follow REST standards and use JSON for request/response.

## 🌐 Base URL and Authentication

```
Base URL: http://<client-service-host>:8001/api/v1
Content-Type: application/json
```

**Note**: The system currently does not implement explicit authentication. Access is controlled at network level and Slurm infrastructure.

## 🎯 Frontend API

### Client Group Management

#### Create Client Group

```http
POST /client-group/{benchmark_id}
```

Creates a new client group for a specific benchmark.

**Path Parameters:**
- `benchmark_id` (integer) - Unique benchmark ID

**Request Body:**
```json
{
  "num_clients": 5,
  "time_limit": 10
}
```

**Body Parameters:**
- `num_clients` (integer, required) - Number of clients to create
- `time_limit` (integer, optional, default: 5) - Time limit in minutes for Slurm job

**Response 201 - Success:**
```json
{
  "status": "created",
  "benchmark_id": 123,
  "num_clients": 5
}
```

**Response 409 - Conflict:**
```json
{
  "detail": "Group already exists"
}
```

**cURL Example:**
```bash
curl -X POST http://client-service:8001/api/v1/client-group/123 \
  -H "Content-Type: application/json" \
  -d '{"num_clients": 5, "time_limit": 15}'
```

---

#### Get Client Group Info

```http
GET /client-group/{benchmark_id}
```

Retrieves information about an existing client group.

**Path Parameters:**
- `benchmark_id` (integer) - Benchmark ID

**Response 200 - Success:**
```json
{
  "benchmark_id": 123,
  "info": {
    "num_clients": 5,
    "client_address": "http://compute-node-01:9000",
    "created_at": 1634567890.123
  }
}
```

**Response 404 - Not Found:**
```json
{
  "detail": "Benchmark id not found"
}
```

**cURL Example:**
```bash
curl http://client-service:8001/api/v1/client-group/123
```

---

#### Delete Client Group

```http
DELETE /client-group/{benchmark_id}
```

Removes an existing client group.

**Path Parameters:**
- `benchmark_id` (integer) - Benchmark ID

**Response 200 - Success:**
```json
{
  "status": "deleted",
  "benchmark_id": 123
}
```

**cURL Example:**
```bash
curl -X DELETE http://client-service:8001/api/v1/client-group/123
```

---

#### Execute Benchmark

```http
POST /client-group/{benchmark_id}/run
```

Starts benchmark execution for the specified client group.

**Path Parameters:**
- `benchmark_id` (integer) - Benchmark ID

**Response 200 - Success:**
```json
{
  "status": "dispatched",
  "benchmark_id": 123,
  "results": [
    {
      "client_process": "http://compute-node-01:9000",
      "status_code": 200,
      "body": "started"
    }
  ]
}
```

**Response 404 - Not Found:**
```json
{
  "detail": "Unknown benchmark id 123"
}
```

**Response 500 - Internal Server Error:**
```json
{
  "detail": "Unexpected error while running client group"
}
```

**cURL Example:**
```bash
curl -X POST http://client-service:8001/api/v1/client-group/123/run
```

## 🔗 Client Registration API

### Client Process Registration

#### Connect Client Process

```http
POST /client-group/{benchmark_id}/connect
```

Registers the address of a client process for a benchmark group.

**Path Parameters:**
- `benchmark_id` (integer) - Benchmark ID

**Request Body:**
```json
{
  "client_address": "http://compute-node-01:9000"
}
```

**Body Parameters:**
- `client_address` (string, required) - Complete URL of the client process

**Response 201 - Success:**
```json
{
  "status": "registered",
  "benchmark_id": 123,
  "client_address": "http://compute-node-01:9000"
}
```

**Response 404 - Not Found:**
```json
{
  "detail": "Benchmark id not found"
}
```

**cURL Example:**
```bash
curl -X POST http://client-service:8001/api/v1/client-group/123/connect \
  -H "Content-Type: application/json" \
  -d '{"client_address": "http://compute-node-01:9000"}'
```

## 📊 Monitor API

### Monitoring System

#### Register Observer

```http
POST /observer
```

Registers a monitoring observer to receive notifications from clients.

**Request Body:**
```json
{
  "ip_address": "192.168.1.100",
  "port": "8080",
  "update_preferences": {
    "frequency": "10s",
    "format": "json"
  }
}
```

**Body Parameters:**
- `ip_address` (string, required) - Monitor IP address
- `port` (string, required) - Monitor port
- `update_preferences` (object, optional) - Update preferences

**Response 200 - Success:**
```json
{
  "status": "observer_added"
}
```

**Response 200 - Error:**
```json
{
  "status": "error"
}
```

**cURL Example:**
```bash
curl -X POST http://client-service:8001/api/v1/observer \
  -H "Content-Type: application/json" \
  -d '{
    "ip_address": "192.168.1.100",
    "port": "8080",
    "update_preferences": {
      "frequency": "5s"
    }
  }'
```

## 🤖 Client Process API

APIs exposed by individual client processes on compute nodes.

### Client Execution

#### Start Client

```http
POST /run
```

Starts execution of all clients in the current process.

**Response 200 - Success:**
```json
{
  "status": "started",
  "num_clients": 3
}
```

**Response 200 - Error:**
```json
{
  "status": "error",
  "num_clients": 0
}
```

---

#### Get Client Status

```http
GET /status
```

Retrieves the current status of the local client group.

**Response 200 - Success:**
```json
{
  "benchmark_id": 123,
  "num_clients": 3,
  "server_addr": "http://ai-server:8000",
  "client_service_addr": "http://client-service:8001",
  "local_address": "http://compute-node-01:9000",
  "created_at": 1634567890.123
}
```

### Monitor Integration

#### Add Observer

```http
POST /observer
```

Adds an observer to the local client group.

**Request Body:**
```json
{
  "ip_address": "192.168.1.100",
  "port": "8080",
  "update_preferences": {}
}
```

**Response 200 - Success:**
```json
{
  "status": "observer_added"
}
```

## 📝 Data Models

### AddGroupPayload
```typescript
interface AddGroupPayload {
  num_clients: number;      // Number of clients to create
  time_limit?: number;      // Time limit in minutes (default: 5)
}
```

### ConnectPayload
```typescript
interface ConnectPayload {
  client_address: string;   // Complete URL of the client process
}
```

### ObserverPayload
```typescript
interface ObserverPayload {
  ip_address: string;                    // Monitor IP
  port: string;                         // Monitor port
  update_preferences?: {[key: string]: any}; // Update preferences
}
```

### RunResponse
```typescript
interface RunResponse {
  status: "started" | "error";  // Operation status
  num_clients: number;          // Number of started clients
}
```

### StatusResponse
```typescript
interface StatusResponse {
  benchmark_id: number;           // Benchmark ID
  num_clients: number;           // Number of clients in the group
  server_addr: string;           // AI server URL
  client_service_addr: string;   // Client service URL
  local_address: string;         // Local process address
  created_at: number;            // Creation timestamp
}
```

## 🔄 Typical API Workflow

### 1. Complete Setup

```bash
# 1. Create client group
curl -X POST http://client-service:8001/api/v1/client-group/123 \
  -H "Content-Type: application/json" \
  -d '{"num_clients": 5, "time_limit": 10}'

# 2. Wait for client registration (automatic via Slurm)
sleep 30

# 3. Verify registration
curl http://client-service:8001/api/v1/client-group/123

# 4. Start benchmark
curl -X POST http://client-service:8001/api/v1/client-group/123/run

# 5. Cleanup (optional)
curl -X DELETE http://client-service:8001/api/v1/client-group/123
```

### 2. Monitoring Setup

```bash
# 1. Register global observer
curl -X POST http://client-service:8001/api/v1/observer \
  -H "Content-Type: application/json" \
  -d '{
    "ip_address": "monitor.local",
    "port": "8080"
  }'

# 2. System automatically propagates observer to clients
```

## ⚠️ Error Codes

| Code | Description | Resolution |
|--------|-------------|-------------|
| 200 | Success | - |
| 201 | Created | - |
| 400 | Bad Request | Check request format |
| 404 | Not Found | Verify that benchmark_id exists |
| 409 | Conflict | Group already exists, use different ID |
| 422 | Unprocessable Entity | Parameter validation failed |
| 500 | Internal Server Error | Check service logs |

## 🛠️ API Testing

### With curl

```bash
# Test endpoint health
curl -f http://client-service:8001/docs

# Test group creation
curl -X POST http://client-service:8001/api/v1/client-group/999 \
  -H "Content-Type: application/json" \
  -d '{"num_clients": 1}' \
  -w "\nStatus: %{http_code}\n"
```

### With Python requests

```python
import requests

base_url = "http://client-service:8001/api/v1"

# Create group
response = requests.post(
    f"{base_url}/client-group/123",
    json={"num_clients": 3, "time_limit": 5}
)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

# Get info
response = requests.get(f"{base_url}/client-group/123")
print(f"Info: {response.json()}")

# Execute benchmark
response = requests.post(f"{base_url}/client-group/123/run")
print(f"Run result: {response.json()}")
```

## 📚 OpenAPI/Swagger

The system automatically exposes interactive documentation:

- **Swagger UI**: `http://client-service:8001/docs`
- **ReDoc**: `http://client-service:8001/redoc`
- **OpenAPI JSON**: `http://client-service:8001/openapi.json`

These interfaces allow you to:
- Explore all available endpoints
- Test APIs directly from the browser
- Download OpenAPI specifications for code generation

## 🔍 API Troubleshooting

### Common Issues

**Timeout on /run endpoint**
- Verify that client process is registered
- Check network connectivity
- Increase HTTP client timeout

**404 on existing benchmark_id**
- Verify that group was created
- Check that Slurm job was started
- Verify ClientManager logs

**Observer not receiving notifications**
- Verify monitor endpoint reachability
- Check that clients are running
- Verify firewall configuration

This API documentation provides a complete guide for integration and use of the AI Factory Client Services system.