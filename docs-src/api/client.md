# Client API Documentation

## Overview

The Client API (port `8002`) manages distributed load testing against AI inference services. It creates client groups on HPC compute nodes that generate concurrent workloads.

## Interactive API Reference

<swagger-ui src="client-openapi.json"/>

## Quick Start

### Create a Client Group

```bash
curl -X POST http://localhost:8002/api/v1/client-groups \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "3652098",
    "num_clients": 10,
    "requests_per_second": 2.0,
    "duration_seconds": 60,
    "prompts": ["Write a poem about AI", "Explain machine learning"],
    "max_tokens": 100,
    "time_limit": 10
  }'
```

### List Client Groups

```bash
curl http://localhost:8002/api/v1/client-groups
```

### Get Client Group Status

```bash
curl http://localhost:8002/api/v1/client-groups/{group_id}
```

### Stop a Client Group

```bash
curl -X DELETE http://localhost:8002/api/v1/client-groups/{group_id}
```

## See Also

- [Client Service Overview](../services/client.md) - Architecture and concepts
- [Server API](server.md) - Create vLLM services to benchmark
