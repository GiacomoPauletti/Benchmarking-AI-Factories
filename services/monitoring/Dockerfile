FROM python:3.11-slim

WORKDIR /app

# Install SSH client, rsync, and other necessary tools
RUN apt-get update && apt-get install -y \
    openssh-client \
    rsync \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Create necessary directories
RUN mkdir -p /app/logs /app/state /root/.ssh

# Set proper SSH directory permissions
RUN chmod 700 /root/.ssh

# Expose FastAPI port
EXPOSE 8002

# Set PYTHONPATH so imports work correctly
ENV PYTHONPATH=/app/src

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Run the FastAPI application with SSH key setup
CMD ["/bin/bash", "-c", "\
if [ -d /tmp/host-ssh ]; then \
  echo 'Setting up SSH keys...'; \
  cp /tmp/host-ssh/id_* /root/.ssh/ 2>/dev/null || true; \
  cp /tmp/host-ssh/known_hosts /root/.ssh/ 2>/dev/null || true; \
  chmod 700 /root/.ssh; \
  chmod 600 /root/.ssh/id_* 2>/dev/null || true; \
  chmod 644 /root/.ssh/*.pub 2>/dev/null || true; \
  echo 'SSH keys ready'; \
fi && \
exec uvicorn src.main:app --host 0.0.0.0 --port 8002 --reload"]
