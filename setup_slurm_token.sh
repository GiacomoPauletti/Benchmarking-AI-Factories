#!/bin/bash

# SLURM JWT Token Setup

echo "Setting up SLURM JWT token..."

# Check if token already exists
if [ -n "$SLURM_JWT" ]; then
    echo "Token already set: ${SLURM_JWT:0:20}..."
    exit 0
fi

# Get token using scontrol
if command -v scontrol >/dev/null 2>&1; then
    TOKEN_OUTPUT=$(scontrol token 2>/dev/null)
    
    if echo "$TOKEN_OUTPUT" | grep -q "SLURM_JWT="; then
        TOKEN=$(echo "$TOKEN_OUTPUT" | grep "SLURM_JWT=" | cut -d'=' -f2)
        export SLURM_JWT="$TOKEN"
        echo "Token set successfully"
        echo "Run: ./launch_server.sh"
    else
        echo "Failed to get token. Run manually: scontrol token"
        exit 1
    fi
else
    echo "scontrol not found. Run manually: scontrol token"
    exit 1
fi