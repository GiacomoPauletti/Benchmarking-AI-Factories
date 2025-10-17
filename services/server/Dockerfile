FROM python:3.11-slim

WORKDIR /app

# Install SSH client and other necessary tools
RUN apt-get update && apt-get install -y \
    openssh-client \
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

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run the FastAPI application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
