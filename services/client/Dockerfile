# syntax=docker/dockerfile:1.4
# =============================================================================
# Client Service Dockerfile
# =============================================================================
# Multi-stage build for the AI Factory Client Service
# This service runs locally and orchestrates clients on MeluXina via SSH
# =============================================================================

FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    openssh-client \
    rsync \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY src/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Build-time options to optionally rebuild the remote Apptainer/SIF on MeluXina.
# These are optional and only used when an SSH agent/socket is forwarded during
# the Docker build (BuildKit + `--ssh`), and when the remote host is reachable.
ARG SSH_REMOTE_HOST
ARG SSH_REMOTE_PORT
ARG SSH_REMOTE_USER
ARG REMOTE_BASE_PATH

# If build-time SSH info is provided, attempt a one-time rebuild of the
# `client_container.sif` on the remote host so the remote cache is fresh.
# This step is guarded and will be a no-op when SSH_REMOTE_HOST is empty.
RUN --mount=type=ssh \ 
    if [ -n "${SSH_REMOTE_HOST}" ] && [ -n "${SSH_REMOTE_USER}" ]; then \
        echo "Attempting remote SIF rebuild on ${SSH_REMOTE_USER}@${SSH_REMOTE_HOST}:${SSH_REMOTE_PORT}"; \
        REMOTE_BASE=$(echo "${REMOTE_BASE_PATH}" | sed "s|^~|/home/users/${SSH_REMOTE_USER}|" ); \
        ssh -o StrictHostKeyChecking=no -p ${SSH_REMOTE_PORT} ${SSH_REMOTE_USER}@${SSH_REMOTE_HOST} "mkdir -p ${REMOTE_BASE}/containers && cd ${REMOTE_BASE}/src/client && apptainer build ${REMOTE_BASE}/containers/client_container.sif client_container.def || true"; \
    else \
        echo "No SSH_REMOTE_HOST/USER provided; skipping remote SIF rebuild"; \
    fi

# Set Python path
ENV PYTHONPATH=/app/src

FROM base AS test

COPY tests/requirements.txt requirements-dev.txt
RUN pip install -q --no-cache-dir -r requirements-dev.txt

# Copy source code
COPY src/ ./src/
COPY tests/ ./tests/

CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "--color=yes"]

FROM base AS prod

# Copy source code
COPY src/ ./src/

# Create logs directory
RUN mkdir -p /app/logs

# Expose port for client service API
EXPOSE 8002

# Default command - can be overridden in docker-compose
CMD ["python", "-m", "main", "--host", "0.0.0.0", "--port", "8002"]