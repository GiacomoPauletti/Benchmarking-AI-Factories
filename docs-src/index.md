# AI Factory Benchmarking Framework

Welcome to the AI Factory Benchmarking Framework documentation.

## Overview

This framework enables benchmarking of AI Factory components on HPC systems, specifically designed for the MeluXina supercomputer. The application orchestrates AI workloads via SLURM and provides monitoring in real-time, all controlable through a Grafana UI.

## Architecture

The framework consists of multiple microservices working together:

```mermaid
graph TB
    subgraph Frontend["Frontend (localhost)"]
        Grafana[Grafana<br/>:3000]
    end
    
    subgraph APIs["API Services"]
        Server[Server<br/>:8001]
        Client[Client<br/>:8002]
        Logs[Logs<br/>:8004]
        Monitoring[Monitoring<br/>:8005]
    end
    
    subgraph Metrics["Metrics Stack"]
        Prometheus[Prometheus<br/>:9090]
        Pushgateway[Pushgateway<br/>:9091]
        Loki[Loki<br/>:3100]
        Alloy[Alloy]
    end
    
    subgraph HPC["MeluXina HPC"]
        Orchestrator[ServiceOrchestrator]
        SLURM[SLURM]
        Compute[Compute Nodes<br/>vLLM / GPU Exporters]
    end
    
    Grafana --> Prometheus
    Grafana --> Loki
    Server -->|SSH Tunnel| Orchestrator
    Client -->|SSH + SLURM| SLURM
    Orchestrator --> SLURM
    SLURM --> Compute
    Compute -->|Push Metrics| Pushgateway
    Prometheus --> Pushgateway
    Alloy --> Loki
    Logs -->|rsync| HPC
    
    style Grafana fill:#FFE0B2
    style Server fill:#B3E5FC
    style Prometheus fill:#C8E6C9
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| **Server** | 8001 | Core orchestration - manages SLURM jobs and AI workload deployment |
| **Client** | 8002 | Executes distributed load tests against AI services |
| **Logs** | 8004 | Syncs and categorizes SLURM job logs from MeluXina |
| **Monitoring** | 8005 | Manages Prometheus scrape targets and metrics collection |
| **Grafana** | 3000 | Visualization dashboard for metrics and benchmarks |
| **Prometheus** | 9090 | Time-series metrics storage |
| **Pushgateway** | 9091 | Buffers metrics from HPC compute nodes |

## Quick Start

See [Getting Started](getting-started/overview.md) for detailed instructions.


## Documentation

- [Getting Started](getting-started/overview.md) - Setup and installation
- [Architecture](architecture/overview.md) - System design and components
- [Server Service](services/server.md) - Detailed server documentation
- [API Reference](api/server.md) - Interactive API documentation
- [Development](development/guidelines.md) - Development guidelines

## Status

**Current Version**: 1.0.0  
**Last Updated**: January 2026  
**Project**: EUMaster4HPC Challenge 2025-2026

