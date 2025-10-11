#!/bin/bash -l
# Simple script to launch interactive node and run the server

# Check for --use-current-node flag
if [[ "$1" == "--use-current-node" ]]; then
    echo "Using current node: $(hostname)"
    echo "========================================="
    
    # Load required modules
    module load env/release/2023.1
    module load Apptainer/1.2.4-GCCcore-12.3.0 || { echo "ERROR: Apptainer module not available"; exit 1; }
    
    cd /home/users/u103056/Benchmarking-AI-Factories/services/server
    
    # Build container if it doesn't exist
    if [ ! -f server.sif ]; then
        echo "Building AI Factory Server container..."
        apptainer build server.sif server.def || { echo "ERROR: Container build failed"; exit 1; }
    fi
    
    # Start the server
    SERVER_ENDPOINT="http://$(hostname):8001"
    echo "Starting AI Factory Server on $(hostname):8001"
    echo "========================================="
    echo "API Docs: ${SERVER_ENDPOINT}/docs"
    echo "Health: ${SERVER_ENDPOINT}/health"
    echo "========================================="
    
    # Write endpoint to state file for client discovery
    echo "${SERVER_ENDPOINT}" > /home/users/u103056/Benchmarking-AI-Factories/services/server/.server-endpoint
    echo "Endpoint written to: /home/users/u103056/Benchmarking-AI-Factories/services/server/.server-endpoint"
    
    # Get SLURM JWT token on the compute node
    echo "Getting SLURM JWT token..."
    export SLURM_JWT=$(scontrol token | grep SLURM_JWT | cut -d= -f2)
    echo "Token obtained: ${SLURM_JWT:0:20}..."
    
    echo "Passing SLURM_JWT token to container..."
    apptainer run \
        --env SLURM_JWT="${SLURM_JWT}" \
        --bind /home/users/u103056:/home/users/u103056 \
        --bind /mnt/tier2/users/u103056:/mnt/tier2/users/u103056 \
        --bind $(pwd)/logs:/app/logs \
        server.sif

else
    echo "Requesting interactive compute node..."
    echo ""

salloc -A p200981 -t 00:30:00 -p cpu -q short -N 1 --ntasks-per-node=1 --mem=16G << 'EOF'
    echo "========================================="
    echo "Interactive node allocated: $(hostname)"
    echo "========================================="
    
    # Load required modules
    module load env/release/2023.1
    module load Apptainer/1.2.4-GCCcore-12.3.0 || { echo "ERROR: Apptainer module not available"; exit 1; }
    
    cd /home/users/u103056/Benchmarking-AI-Factories/services/server
    
    # Build container if it doesn't exist
    if [ ! -f server.sif ]; then
        echo "Building AI Factory Server container..."
        apptainer build server.sif server.def || { echo "ERROR: Container build failed"; exit 1; }
    fi
    
    # Start the server
    SERVER_ENDPOINT="http://$(hostname):8001"
    echo "Starting AI Factory Server on $(hostname):8001"
    echo "========================================="
    echo "API Docs: ${SERVER_ENDPOINT}/docs"
    echo "Health: ${SERVER_ENDPOINT}/health"
    echo "========================================="
    
    # Write endpoint to state file for client discovery
    echo "${SERVER_ENDPOINT}" > /home/users/u103056/Benchmarking-AI-Factories/services/server/.server-endpoint
    echo "Endpoint written to: /home/users/u103056/Benchmarking-AI-Factories/services/server/.server-endpoint"
    
    # Get SLURM JWT token on the compute node
    echo "Getting SLURM JWT token..."
    export SLURM_JWT=$(scontrol token | grep SLURM_JWT | cut -d= -f2)
    echo "Token obtained: ${SLURM_JWT:0:20}..."
    
    echo "Passing SLURM_JWT token to container..."
    apptainer run \
        --env SLURM_JWT="${SLURM_JWT}" \
        --bind /home/users/u103056:/home/users/u103056 \
        --bind /mnt/tier2/users/u103056:/mnt/tier2/users/u103056 \
        --bind $(pwd)/logs:/app/logs \
        server.sif
EOF
fi