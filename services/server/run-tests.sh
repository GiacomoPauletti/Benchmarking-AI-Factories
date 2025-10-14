#!/bin/bash
# Build and run the test container

set -e

echo "Building AI Factory Test Container"
echo "====================================="

# Get the directory where the script is located (must be done BEFORE salloc)
SERVER_BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Navigate to the test directory
cd "${SERVER_BASE_DIR}/tests"

# Request resources 
salloc -A p200981 -t 00:30:00 -p cpu -q short -N 1 --ntasks-per-node=1 --mem=8G << EOF

module load env/release/2023.1
module load Apptainer/1.2.4-GCCcore-12.3.0 || { echo "ERROR: Apptainer module not available"; exit 1; }
    
# Build the container
echo "Building test container..."
if apptainer build --fakeroot --force test-container.sif test-container.def; then
    echo "Container built successfully"
else
    echo "Container build failed"
    exit 1
fi

# Navigate back to project root (from tests/ directory, go up 3 levels: tests -> server -> services -> root)
cd ../../..

# Debug: Show current directory and files
echo "Current directory: $(pwd)"
echo "Looking for container at: $(pwd)/services/server/tests/test-container.sif"
ls -la services/server/tests/test-container.sif

echo ""
echo "Running Tests in Container"
echo "============================="


# Get SLURM JWT token on the compute node
echo "Getting SLURM JWT token..."
export SLURM_JWT=\$(scontrol token | grep SLURM_JWT | cut -d= -f2)
echo "Token obtained: \${SLURM_JWT:0:20}..."

# Run the container with project directory bound to /app and pass environment variables
if apptainer run \\
    --env SLURM_JWT="\${SLURM_JWT}" \\
    --env SERVER_BASE_PATH="${SERVER_BASE_DIR}" \\
    --bind "\$(pwd):/app" \\
    services/server/tests/test-container.sif; then
    echo ""
    echo "All tests passed!"
    echo ""
    echo "You can now push your changes to your feature branch and create a pull request."
else
    echo ""
    echo "Tests failed!"
    echo ""
    echo "Check the output above for details."
    exit 1
fi

EOF