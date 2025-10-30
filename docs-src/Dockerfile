FROM python:3.11-slim

WORKDIR /docs

# Install git and other dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY docs-requirements.txt .
RUN pip install --no-cache-dir -r docs-requirements.txt

# Copy documentation files
COPY . .

# Expose MkDocs default port
EXPOSE 8000

# Default command: serve documentation
CMD ["mkdocs", "serve", "--dev-addr=0.0.0.0:8000", "--dirtyreload"]
