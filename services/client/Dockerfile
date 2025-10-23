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
COPY requirements.txt .
COPY src/requirements.txt ./src/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r src/requirements.txt

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Set Python path
ENV PYTHONPATH=/app/src

# Create logs directory
RUN mkdir -p /app/logs

# Make scripts executable
RUN chmod +x scripts/*.sh

# Expose port for client service API
EXPOSE 8002

# Default command - can be overridden in docker-compose
CMD ["python", "-m", "main", "--host", "0.0.0.0", "--port", "8002"]