Bootstrap: docker
From: python:3.11-slim

%help
    This container runs the AI Factory Client.
    
    Usage:
        apptainer run client_container.sif <server_address> <benchmark_id> [slurm_config_file]
    
    Example:
        apptainer run client_container.sif http://server:8000 17



%files
    # Copy the client source code
    main.py                 /app/src/client/

%environment
    # Set Python path and other environment variables
    export PYTHONPATH="/app:$PYTHONPATH"
    export PYTHONUNBUFFERED=1

%post
    # Update system and install dependencies
    apt-get update && apt-get install -y \
        curl \
        netcat-openbsd \
        procps \
        && rm -rf /var/lib/apt/lists/*
    
    # Install required Python packages for async load testing
    pip install --no-cache-dir aiohttp prometheus-client

%runscript
    # Default runscript - starts the client
    cd /app/src
    exec python3 -m client.main "$@"

%startscript
    # Alternative start method
    cd /app/src
    exec python3 -m client.main "$@"