# Monitoring Service

## Overview

The Monitoring Service collects and aggregates performance metrics from deployed AI services and the HPC infrastructure. It integrates with Prometheus, Pushgateway, and Grafana to provide real-time visibility into GPU utilization, power consumption, and service health.

!!! tip "Live API Explorer"
    The best way to explore the API is here:
    
    **[Open Interactive API Docs](../../api/monitoring){ .md-button .md-button--primary }**

## What It Does

- **Metrics Collection**: Gathers GPU metrics (utilization, memory, power, temperature) from compute nodes
- **Pushgateway Integration**: Buffers metrics when direct scraping isn't possible (network isolation)
- **Target Registration**: Dynamically registers services and exporters for Prometheus scraping
- **Session Management**: Create monitoring sessions with configurable time windows
- **Artifact Generation**: Export collected metrics as CSV/JSON for analysis

## Architecture

```mermaid
graph TB
    subgraph Local["Local Machine"]
        Monitoring["Monitoring API<br/>localhost:8005"]
        Prometheus["Prometheus<br/>localhost:9090"]
        Pushgateway["Pushgateway<br/>localhost:9091"]
        Grafana["Grafana<br/>localhost:3000"]
    end
    
    subgraph MeluXina["MeluXina Compute Nodes"]
        GPUExporter["GPU Exporter<br/>(nvidia-smi metrics)"]
        vLLM["vLLM Service"]
    end
    
    GPUExporter -->|"Push metrics"| Pushgateway
    Prometheus -->|"Scrape"| Pushgateway
    Prometheus -->|"Proxy via Server"| vLLM
    Grafana -->|"Query"| Prometheus
    Monitoring -->|"Configure targets"| Prometheus
    
    style Monitoring fill:#C8E6C9,stroke:#388E3C,stroke-width:2px
    style Prometheus fill:#FFE0B2,stroke:#F57C00,stroke-width:2px
    style Grafana fill:#B3E5FC,stroke:#0288D1,stroke-width:2px
```

## API Reference

See [Monitoring API Documentation](../api/monitoring.md) for the interactive API reference.
