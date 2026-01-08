# Getting Started

This guide will help you set up and run the AI Factory Benchmarking Framework on the MeluXina supercomputer.

## Overview

The AI Factory Benchmarking Framework is a distributed system for deploying, benchmarking, and monitoring AI inference services on HPC clusters. Unlike simple tools that run sequentially, our framework lets you launch an arbitrary number of benchmarks in parallel, allowing you to scale your experiments without being limited to one benchmark at a time.

**Features:**

- Deploy dozens of vLLM replicas via SLURM with GPU allocation, automatically load balanced
- Run distributed load tests with hundreds of clients performing load on the vLLM services
- Collect GPU metrics (utilization, power, temperature) in real-time
- Visualize performance through Grafana dashboards
- Aggregate and query SLURM job logs

All this through a simple, intuitive Grafana UI.

## Installation

To install and set up the framework, see the [Installation Guide](installation.md).

## Getting Help

- Check API documentations
- **GitHub Issues**: [Report a bug](https://github.com/GiacomoPauletti/Benchmarking-AI-Factories/issues)

---

Continue to [Installation Guide](installation.md) for setup instructions!
