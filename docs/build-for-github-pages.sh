#!/bin/bash
# Simple script to build documentation for GitHub Pages

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Building Documentation for GitHub Pages"
echo "========================================"
echo ""

cd "$PROJECT_ROOT"

# Build using Docker
echo "Building documentation..."
docker compose run --rm docs mkdocs build

echo ""
echo "✓ Documentation built successfully!"
echo "  Output: $PROJECT_ROOT/docs/"
echo ""
echo "Next steps:"
echo "  1. git add docs/"
echo "  2. git commit -m 'Build documentation'"
echo "  3. git push"
echo "  4. In GitHub: Settings → Pages → Set branch and folder to '/docs'"
echo ""
echo "Your docs will be at: https://giacomopauletti.github.io/Benchmarking-AI-Factories/"
