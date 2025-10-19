#!/bin/bash
# Deploy documentation to GitHub Pages using Docker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Deploying Documentation to GitHub Pages"
echo "========================================"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed"
    exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    echo "WARNING: You have uncommitted changes"
    echo ""
    git status --short
    echo ""
    read -p "Continue anyway? [y/N]: " confirm
    if [[ ! $confirm == [yY] ]]; then
        echo "Deployment cancelled"
        exit 1
    fi
fi

echo "Building documentation and deploying to gh-pages branch..."
echo ""

# Run deployment in Docker with git safe directory configured
docker compose run --rm docs bash -c "git config --global --add safe.directory / && mkdocs gh-deploy --force"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "Documentation deployed successfully!"
    echo "=========================================="
    echo ""
    echo "URL: https://giacomopauletti.github.io/Benchmarking-AI-Factories/"
    echo ""
    echo "Note: It may take 1-2 minutes for changes to appear."
    echo ""
else
    echo ""
    echo "Deployment failed. Check the error messages above."
    exit 1
fi
