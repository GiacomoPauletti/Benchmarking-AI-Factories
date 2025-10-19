# EU AI Factories Benchmark Project
EUMaster4HPC challenge a.y. 2025-2026

**Objective**: Develop a framework to evaluate performance of AI Factory components in the MeluXina HPC.

## Documentation

**[View Full Documentation →](https://giacomopauletti.github.io/Benchmarking-AI-Factories/)** *(Coming soon)*

For hosting documentation locally:

```bash
# Build and serve documentation locally
cd docs
./build-docs.sh
# Choose option 1, then visit http://127.0.0.1:8000
```

# Docker Setup Guide

This project uses Docker Compose for local development and production. The microservices run in containers and connect to MeluXina HPC via SSH to submit SLURM jobs.

## Project Structure

```
Benchmarking-AI-Factories/
├── docker-compose.yml           # Production server
├── docker-compose.test.yml      # Isolated test environment
├── .env                         # Main configuration
└── services/                    # Microservices
    |── server/
    |    ├── Dockerfile
    |── client/  
    |    ├── Dockerfile
    |── monitor/   
    |    ├── Dockerfile
    |── logs/   
         ├── Dockerfile
```

---

## Quick Start

### 1. First-Time Setup

```bash
# 1. Edit with your credentials
nano .env
```

**Required settings in `.env`:**
```bash
SSH_HOST=login.lxp.lu              # MeluXina login node
SSH_PORT=8822                       # MeluXina SSH port
SSH_USER=u123456                    # Your MeluXina username
SSH_KEY_PATH=~/.ssh/id_ed25519     # Path to your SSH key
REMOTE_BASE_PATH=/project/home/p200981/u123456/path/to/temp/generated/files
```

### 2. Launch the Microservice(s)

```bash
docker compose up <specific microservice or leave it out for all>
```

### 3. Verify It's Working

Open in your browser:
- **API Docs**: http://localhost:8001/docs
- **Health Check**: http://localhost:8001/health

---

## Running Tests

The project has an isolated test environment that doesn't require MeluXina access.
To run the tests on some microservice or all, use 

```bash
docker compose -f docker-compose.test.yml up <specific microservices or leave it out for all> --build
```
---

## Configuration Details

### Environment Files

**`.env` (project root)**
- Main configuration loaded by docker-compose
- Contains SSH credentials and remote paths
- **Never commit this file!** (listed in .gitignore)

### SSH Key Setup

The container needs access to your SSH key to connect to MeluXina:

```bash
# Your key should be accessible at the path specified in .env
ls -l ~/.ssh/id_ed25519

# Ensure proper permissions
chmod 600 ~/.ssh/id_ed25519
```

The Dockerfile automatically:
1. Copies your SSH key into the container
2. Sets correct permissions (600)
3. Configures SSH client for MeluXina

---

## Troubleshooting

### "SSH connection failed"
- Check `SSH_USER`, `SSH_HOST`, and `SSH_PORT` in `.env`
- Verify your SSH key path is correct
- Test SSH manually: `ssh -i ~/.ssh/id_ed25519 -p 8822 u123456@login.lxp.lu`

### "Permission denied (publickey)"
- Ensure SSH key has correct permissions: `chmod 600 ~/.ssh/id_ed25519`
- Verify the key is registered with MeluXina
- Check `SSH_KEY_PATH` points to the correct key

### "Port 8001 already in use"
- Stop other containers: `docker compose down`
- Check for other processes: `lsof -i :8001`
- Kill process: `kill -9 <PID>`

### "Container exits immediately"
- Check logs: `docker compose logs`
- Verify all required env vars are set in `.env`
- Look for syntax errors in configuration files

### Tests failing
- Ensure you're using the test compose file: `docker-compose.test.yml`
- Rebuild test container: `docker compose -f docker-compose.test.yml build --no-cache`
- Check test output for specific failures

---



# Architecture
The project must run on the MeluXina supercomputer. The various components are:
 - A server: the server must take care of running the services that need to be benchmarked (databases, LLMs, etc.).
 - A client: the client must take care of testing the services that are being benchmarked (ex: running prompts, etc.).
 - A monitor: the monitor must take care of ingesting various metrics about both the running benchmarks' application and the underlying computer system, then store it into a Prometheus database for real-time and later analysis.
 - A log ingester: the log ingester must take care of ingesting the logs produced both by the running benchmark's application and the underlying infrastructure. It then stores it into a Grafana Loki database for real-time and later observability into the benchmarks.
 - A UI: the UI is based upon a Grafana dashboard. It fetches data from the logs' & metrics's respective databases, then displays it for analysis. During a benchmark, a live view is available. Post-mortem, aggregates & trends can also be viewed in dedicated pages. Logs are of course present in those views. Lastly, the UI must also be able to interact with the infrastructure to control it (startup and shutdown of the components, startup and shutdown of benchmarks).

To ease development, a microservice architecture has been chosen, where each part of the application is started as a separate process.

## Core modules
The various modules / processes that will be needed and their respective tasks is highlighted below:
 - Slurm: runs the various jobs on the physical MeluXina system. Controlled by the Server.
 - Server: interacts with Slurm via the REST API to start up services, and keep monitoring them. The process is developed by the team in Python.
 - Client: interacts with an AI server to benchmark it. The process is developed by the team in Spark.
 - Service monitor: runs with the service, and responsible for ingesting various metrics and sending it to Prometheus. Developed by the team in Python.
 - Prometheus: time-series database. Interface between the metrics ingesters and the UI. Configured by the team.
 - Service log ingester: runs with the service. Forwards the slurm logs to the Grafana Loki database. Developed by the team in Rust.
 - Grafana Loki: logs database. Interface between the log ingesters and the UI. Configured by the team.
 - Grafana: dashboard frontend. Configured & extended by the team.
 - K8s: to ease the deployment of the various components & to provide automatic restart, the infrastructure will be deployed in docker containers for a K8s setup.

## Interfaces between modules
The interface between the modules is as follow:
 - Service and client: service-dependent, depending on the benchmark. HTTP-based.
 - Service and monitor: through the linux system (proc, top, etc.)
 - Service and log ingester: through the filesystem (.out and .err files)
 - Server and Slurm: through the REST API
 - Server and monitor: through the linux system (proc, top, etc.) and through a custom REST API
 - Server and log ingester: through the filesystem (dedicated log files)
 - Monitor and Prometheus: through the REST API
 - Prometheus and Grafana: through the REST API; handled automatically by Grafana
 - Log ingester and Loki: through the REST API
 - Loki and Grafana: through the REST API; handled automatically by Grafana
