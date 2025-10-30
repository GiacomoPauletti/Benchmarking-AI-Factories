# Server API Reference

The Server Service provides a comprehensive REST API for managing AI services on the MeluXina supercomputer.

## Interactive API Documentation

!!! tip "Live API Explorer"
    The best way to explore the API is through the **interactive Swagger UI**:
    
    **[Open Interactive API Docs](../api/server.md){ .md-button .md-button--primary }**

## Overview

A FastAPI server for orchestrating AI workloads on SLURM clusters using Apptainer containers.

### What it does

- **Service Orchestration**: Deploy and manage AI services via SLURM job submission
- **Recipe System**: Pre-defined configurations for common AI workloads
- **VLLM Integration**: Direct API access to running VLLM inference services
- **REST API**: Operations for service lifecycle management

### Architecture

```
┌─────────────────────────────────────┐
│  Local Laptop (Docker)              │
│  ┌────────────────────────────────┐ │
│  │  FastAPI Server Container      │ │
│  │  - API endpoints               │ │
│  │  - Hot-reload on code changes  │ │
│  │  - SLURM client (via SSH)      │ │
│  └────────────────────────────────┘ │
│           │ SSH Tunnel               │
└───────────┼─────────────────────────┘
            │
            ▼
┌─────────────────────────────────────┐
│  MeluXina HPC Cluster               │
│  ┌────────────────────────────────┐ │
│  │  SLURM Job Submission          │ │
│  │  Apptainer containers          │ │
│  │  GPU nodes                     │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

## Further Reading

- [Service Recipes](recipes.md) - Available service templates
- [Architecture](../architecture/overview.md) - System design
- [Development Guide](../development/guidelines.md) - API development

---
