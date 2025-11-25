# AI Factory Server Service

A FastAPI server for orchestrating AI workloads on SLURM clusters using Apptainer containers.

## Documentation

For comprehensive documentation about the Server service, including architecture, API reference, available recipes, quick start guide, and development guidelines, please visit:

**[Server Service Documentation](https://giacomopauletti.github.io/Benchmarking-AI-Factories/services/server/)**

## Quick Links

- [Architecture & Infrastructure](https://giacomopauletti.github.io/Benchmarking-AI-Factories/services/server/#orchestration-infrastructure)
- [Interactive API Docs](https://giacomopauletti.github.io/Benchmarking-AI-Factories/api/server/)
- [Development Guidelines](https://giacomopauletti.github.io/Benchmarking-AI-Factories/development/guidelines/#adding-a-new-service-to-the-server)
- [Recipe System](https://giacomopauletti.github.io/Benchmarking-AI-Factories/getting-started/overview/)

## Environment Configuration

All server-side defaults now come from the repository-level `.env` file (loaded by Docker Compose). Key settings include:

- `MELUXINA_ENV_MODULE`, `APPTAINER_MODULE` – module versions loaded before each SLURM job builds or runs Apptainer images.
- `ORCHESTRATOR_*` – port, account, partition, QoS, nodes/tasks, CPUs per task, and time limit for the orchestrator job as well as downstream service submissions.
- `SLURM_REST_*` – remote host/port and local forwarding port used when bootstrapping the SLURM REST tunnel from the server container.
- `APPTAINER_TMPDIR_BASE`, `APPTAINER_CACHEDIR_BASE`, `REMOTE_FAKE_HOME_BASE`, `REMOTE_HF_CACHE_DIRNAME` – remote filesystem locations used for temporary build space, cache directories, fake home directories, and Hugging Face cache bindings.

Update `.env` to match the target cluster instead of editing Python or shell scripts. The server container automatically propagates these values to SLURM job scripts and the orchestrator runtime.