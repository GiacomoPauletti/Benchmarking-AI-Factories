#!/bin/bash
# Build and serve MkDocs documentation

set -e

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "AI Factory Documentation Builder"
echo "================================"
echo "Working directory: $SCRIPT_DIR"
echo ""

# Check if mkdocs is installed
if ! command -v mkdocs &> /dev/null; then
    echo "MkDocs not found. Installing dependencies..."
    pip install -r docs-requirements.txt
fi

# Show menu
echo ""
echo "Choose an option:"
echo "1) Serve documentation locally (http://127.0.0.1:8000)"
echo "2) Build documentation (output to site/)"
echo "3) Install dependencies only"
echo "4) Deploy to GitHub Pages"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
    1)
        echo "Starting local server..."
        echo "Documentation will be available at: http://127.0.0.1:8000"
        echo "Press Ctrl+C to stop"
        mkdocs serve
        ;;
    2)
        echo "Building documentation..."
        mkdocs build
        echo ""
        echo "Documentation built successfully!"
        echo "Output directory: ../site/"
        echo "To view: open ../site/index.html in your browser"
        ;;
    3)
        echo "Installing dependencies..."
        pip install -r docs-requirements.txt
        echo "Dependencies installed successfully!"
        ;;
    4)
        echo "Deploying to GitHub Pages..."
        echo "This will push to the gh-pages branch"
        read -p "Are you sure? [y/N]: " confirm
        if [[ $confirm == [yY] ]]; then
            mkdocs gh-deploy
            echo "Documentation deployed!"
        else
            echo "Deployment cancelled"
        fi
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac
