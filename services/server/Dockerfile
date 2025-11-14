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

# Copy .server-endpoint if it exists (optional file)
RUN touch .server-endpoint

# Create necessary directories
RUN mkdir -p /app/logs /app/huggingface_cache /root/.ssh

# Set proper SSH directory permissions
RUN chmod 700 /root/.ssh

# Expose FastAPI port
EXPOSE 8001

# Set PYTHONPATH so imports work correctly
ENV PYTHONPATH=/app/src

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run the FastAPI application with SSH key setup and recipe sync in CMD
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
if [ -n \"$SSH_USER\" ] && [ -n \"$SSH_HOST\" ] && [ -n \"$REMOTE_BASE_PATH\" ]; then \
  echo 'Syncing recipes to MeluXina...'; \
  SSH_OPTS=\"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null\"; \
  if [ -n \"$SSH_KEY_PATH\" ]; then \
    SSH_KEY_EXPANDED=$(eval echo $SSH_KEY_PATH); \
    if [ -f \"/root/.ssh/$(basename $SSH_KEY_EXPANDED)\" ]; then \
      SSH_OPTS=\"$SSH_OPTS -i /root/.ssh/$(basename $SSH_KEY_EXPANDED)\"; \
    fi; \
  fi; \
  if [ \"$SSH_PORT\" != \"22\" ] && [ -n \"$SSH_PORT\" ]; then \
    SSH_OPTS=\"$SSH_OPTS -p $SSH_PORT\"; \
  fi; \
  ssh $SSH_OPTS $SSH_USER@$SSH_HOST \"mkdir -p $REMOTE_BASE_PATH/src/recipes\" 2>/dev/null || true; \
  rsync -avz --delete \
    -e \"ssh $SSH_OPTS\" \
    --exclude='logs/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='*.sif' \
    /app/src/recipes/ \
    $SSH_USER@$SSH_HOST:$REMOTE_BASE_PATH/src/recipes/ && \
  echo 'Recipe sync complete' || \
  echo 'Warning: Recipe sync failed (server will still start)'; \
else \
  echo 'Skipping recipe sync (SSH config not set)'; \
fi && \
echo 'http://localhost:8001' > /app/.server-endpoint && \
exec uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload"]
