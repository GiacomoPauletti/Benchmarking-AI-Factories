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
RUN mkdir -p /app/logs /root/.ssh

# Set proper SSH directory permissions
RUN chmod 700 /root/.ssh

# Expose FastAPI port
EXPOSE 8001

# Set PYTHONPATH so imports work correctly
ENV PYTHONPATH=/app/src

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

COPY entrypoint.sh .

# Run the FastAPI application with SSH key setup and recipe sync in CMD
CMD ["/bin/bash", "entrypoint.sh"]
