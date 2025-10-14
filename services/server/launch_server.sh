#!/bin/bash -l
# Simple script to launch interactive node and run the server

# Get the directory where the script is located (must be done BEFORE salloc)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check for --use-current-node flag
if [[ "$1" == "--use-current-node" ]]; then
    echo "Using current node: $(hostname)"
    echo "========================================="
    
    # Load required modules
    module load env/release/2023.1
    module load Apptainer/1.2.4-GCCcore-12.3.0 || { echo "ERROR: Apptainer module not available"; exit 1; }
    
    cd "${SCRIPT_DIR}"
    
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
    echo "${SERVER_ENDPOINT}" > "${SCRIPT_DIR}/.server-endpoint"
    echo "Endpoint written to: ${SCRIPT_DIR}/.server-endpoint"
    
    # Get SLURM JWT token on the compute node
    echo "Getting SLURM JWT token..."
    export SLURM_JWT=$(scontrol token | grep SLURM_JWT | cut -d= -f2)
    echo "Token obtained: ${SLURM_JWT:0:20}..."
    
    echo "Passing SLURM_JWT token to container..."
    apptainer run \
        --env SLURM_JWT="${SLURM_JWT}" \
        --env SERVER_BASE_PATH="${SCRIPT_DIR}" \
        --bind /home/users/${USER}:/home/users/${USER} \
        --bind /mnt/tier2/users/${USER}:/mnt/tier2/users/${USER} \
        --bind $(pwd)/logs:/app/logs \
        server.sif

else
    echo "Requesting interactive compute node..."
    echo ""

salloc -A p200981 -t 00:30:00 -p cpu -q short -N 1 --ntasks-per-node=1 --mem=16G << EOF
    echo "========================================="
    echo "Interactive node allocated: \$(hostname)"
    echo "========================================="
    
    # Load required modules
    module load env/release/2023.1
    module load Apptainer/1.2.4-GCCcore-12.3.0 || { echo "ERROR: Apptainer module not available"; exit 1; }
    
    # Use SCRIPT_DIR from parent shell
    cd "${SCRIPT_DIR}"
    
    # Build container if it doesn't exist
    if [ ! -f server.sif ]; then
        echo "Building AI Factory Server container..."
        apptainer build server.sif server.def || { echo "ERROR: Container build failed"; exit 1; }
    fi
    
    # Start the server
    SERVER_ENDPOINT="http://\$(hostname):8001"
    echo "Starting AI Factory Server on \$(hostname):8001"
    echo "========================================="
    echo "API Docs: \${SERVER_ENDPOINT}/docs"
    echo "Health: \${SERVER_ENDPOINT}/health"
    echo "========================================="
    
    # Write endpoint to state file for client discovery
    echo "\${SERVER_ENDPOINT}" > "${SCRIPT_DIR}/.server-endpoint"
    echo "Endpoint written to: ${SCRIPT_DIR}/.server-endpoint"
    
    # Get SLURM JWT token on the compute node
    echo "Getting SLURM JWT token..."
    export SLURM_JWT=\$(scontrol token | grep SLURM_JWT | cut -d= -f2)
    echo "Token obtained: \${SLURM_JWT:0:20}..."
    
    echo "Passing SLURM_JWT token to container..."
    apptainer run \\
        --env SLURM_JWT="\${SLURM_JWT}" \\
        --env SERVER_BASE_PATH="${SCRIPT_DIR}" \\
        --bind /home/users/\${USER}:/home/users/\${USER} \\
        --bind /mnt/tier2/users/\${USER}:/mnt/tier2/users/\${USER} \\
        --bind \$(pwd)/logs:/app/logs \\
        server.sif
EOF
fi