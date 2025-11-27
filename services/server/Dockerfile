FROM python:3.11-slim

WORKDIR /app

# Install SSH client, rsync, and other necessary tools
RUN apt-get update && apt-get install -y \
    openssh-client \
    rsync \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Build-time args (SSH info passed from docker-compose/.env)
ARG SSH_USER
ARG SSH_HOST
ARG SSH_PORT=22
ARG REMOTE_BASE_PATH
ARG REBUILD_ORCHESTRATOR=false

# Conditionally remove remote orchestrator.sif during image build to force rebuild.
# Set REBUILD_ORCHESTRATOR=true in .env or via docker-compose build --build-arg to enable.
# If SSH_USER/SSH_HOST are not set, the step is skipped. This runs at build-time so the orchestrator
# will be rebuilt on the cluster the next time it's started.
# Note: BuildKit SSH forwarding is recommended so the build can use your SSH agent securely.
RUN if [ "${REBUILD_ORCHESTRATOR}" = "true" ] && [ -n "${SSH_USER}" ] && [ -n "${SSH_HOST}" ]; then \
      echo "REBUILD_ORCHESTRATOR=true: Deleting remote orchestrator.sif on ${SSH_USER}@${SSH_HOST}:${SSH_PORT}"; \
      ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} \"rm -f ${REMOTE_BASE_PATH}/src/service_orchestration/orchestrator.sif || true\" || true; \
    else \
      echo "Skipping remote orchestrator.sif deletion (REBUILD_ORCHESTRATOR=${REBUILD_ORCHESTRATOR})"; \
    fi

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=300 --retries=5 -r requirements.txt

# Copy source code
COPY src/ ./src/

# Copy .server-endpoint if it exists (optional file)
RUN touch .server-endpoint

# Create necessary directories
RUN mkdir -p /root/.ssh

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
# ============================================================================
# SSH Key Setup
# ============================================================================
setup_ssh_keys() { \
  if [ -d /tmp/host-ssh ]; then \
    echo 'Setting up SSH keys...'; \
    cp /tmp/host-ssh/id_* /root/.ssh/ 2>/dev/null || true; \
    cp /tmp/host-ssh/known_hosts /root/.ssh/ 2>/dev/null || true; \
    chmod 700 /root/.ssh; \
    chmod 600 /root/.ssh/id_* 2>/dev/null || true; \
    chmod 644 /root/.ssh/*.pub 2>/dev/null || true; \
    echo 'SSH keys ready'; \
  fi; \
}; \
\
# ============================================================================
# Build SSH Options
# ============================================================================
build_ssh_opts() { \
  local SSH_OPTS=\"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null\"; \
  \
  if [ -n \"$SSH_KEY_PATH\" ]; then \
    SSH_KEY_EXPANDED=$(eval echo $SSH_KEY_PATH); \
    if [ -f \"/root/.ssh/$(basename $SSH_KEY_EXPANDED)\" ]; then \
      SSH_OPTS=\"$SSH_OPTS -i /root/.ssh/$(basename $SSH_KEY_EXPANDED)\"; \
    fi; \
  fi; \
  \
  if [ \"$SSH_PORT\" != \"22\" ] && [ -n \"$SSH_PORT\" ]; then \
    SSH_OPTS=\"$SSH_OPTS -p $SSH_PORT\"; \
  fi; \
  \
  echo \"$SSH_OPTS\"; \
}; \
\
# ============================================================================
# Create Remote Directories
# ============================================================================
create_remote_dirs() { \
  local SSH_OPTS=\"$1\"; \
  echo 'Creating remote directories...'; \
  ssh $SSH_OPTS $SSH_USER@$SSH_HOST \
    \"mkdir -p $REMOTE_BASE_PATH/src/recipes $REMOTE_BASE_PATH/src/service_orchestration\" \
    2>/dev/null || true; \
}; \
\
# ============================================================================
# Sync Recipes
# ============================================================================
sync_recipes() { \
  local SSH_OPTS=\"$1\"; \
  echo 'Syncing recipes...'; \
  rsync -avz --delete \
    -e \"ssh $SSH_OPTS\" \
    --exclude='logs/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='*.sif' \
    /app/src/recipes/ \
    $SSH_USER@$SSH_HOST:$REMOTE_BASE_PATH/src/recipes/; \
}; \
\
# ============================================================================
# Sync Service Orchestration
# ============================================================================
sync_orchestration() { \
  local SSH_OPTS=\"$1\"; \
  echo 'Syncing service orchestration code...'; \
  rsync -avz --delete \
    -e \"ssh $SSH_OPTS\" \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='*.sif' \
    /app/src/service_orchestration/ \
    $SSH_USER@$SSH_HOST:$REMOTE_BASE_PATH/src/service_orchestration/; \
}; \
\
# ============================================================================
# Main Sync Process
# ============================================================================
sync_to_meluxina() { \
  if [ -z \"$SSH_USER\" ] || [ -z \"$SSH_HOST\" ] || [ -z \"$REMOTE_BASE_PATH\" ]; then \
    echo 'Skipping sync (SSH config not set)'; \
    return 0; \
  fi; \
  \
  echo 'Syncing code to MeluXina...'; \
  local SSH_OPTS=$(build_ssh_opts); \
  \
  create_remote_dirs \"$SSH_OPTS\" && \
  sync_recipes \"$SSH_OPTS\" && \
  sync_orchestration \"$SSH_OPTS\" && \
  echo 'Sync complete' || \
  echo 'Warning: Sync failed (server will still start)'; \
}; \
\
# ============================================================================
# Startup Sequence
# ============================================================================
setup_ssh_keys && \
sync_to_meluxina && \
echo 'http://localhost:8001' > /app/.server-endpoint && \
exec uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload"]
