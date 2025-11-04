# Development Guidelines

## AI Benchmarking Application - Development Reference

This guide provides development standards and best practices for contributing to the AI Factory Benchmarking Framework.

## Development Principles

TODO...


---

## CI & Testing

This project uses a simplified CI pipeline suitable for local development and pre-merge checks:

- Each microservice contains a `tests/` folder that holds unit and integration tests specific to that microservice.
- The `docker-compose.test.yml` file orchestrates running those tests for every microservice. It is intended to be executed before merging changes into the `dev` or `main` branches.

To run the tests locally (or in CI), use:

```bash
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

The test compose will bring up each test container, run the test-suite, and exit. CI should treat any non-zero exit code from the test containers as a failure and block merges until tests pass.

### Local integration / production-like runs

For running the full application locally (a production-like scenario useful for manual testing and local benchmarking), use `docker-compose.yml`:

```bash
docker compose up --build
```

The `docker-compose.yml` setup is intended for local simulation only. For production or realistic large-scale benchmarking, services should be deployed to a proper Kubernetes (K8s) cluster that provides scheduling, scaling, and resilience.


