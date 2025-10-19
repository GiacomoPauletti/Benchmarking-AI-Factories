#!/bin/bash
# Build and serve MkDocs documentation using Docker

set -e

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "AI Factory Documentation Builder (Docker)"
echo "========================================"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed or not in PATH"
    echo ""
    echo "Please install Docker:"
    echo "  https://docs.docker.com/engine/install/"
    echo ""
    exit 1
fi

# Check if docker compose is available
if ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose is not available"
    echo ""
    echo "Please install Docker Compose:"
    echo "  https://docs.docker.com/compose/install/"
    echo ""
    exit 1
fi

# Show menu
echo "Choose an option:"
echo "1) Serve documentation locally (http://localhost:8000)"
echo "2) Build documentation (output to site/)"
echo "3) Generate OpenAPI schemas"
echo "4) Deploy to GitHub Pages"
echo "5) Build Docker image only"
echo "6) Stop documentation server"
echo "7) View logs"
echo ""
read -p "Enter choice [1-7]: " choice

case $choice in
    1)
        echo "Starting documentation server..."
        docker compose up -d docs
        echo ""
        echo "Documentation is now available at: http://localhost:8000"
        echo "The server will auto-reload when you edit files."
        echo ""
        echo "To stop the server, run:"
        echo "  docker compose down docs"
        echo "or choose option 5 from this menu"
        ;;
    2)
        echo "Building documentation..."
        docker compose run --rm docs mkdocs build
        echo ""
        echo "Documentation built successfully!"
        echo "Output directory: $PROJECT_ROOT/site/"
        echo "To view: open $PROJECT_ROOT/site/index.html in your browser"
        ;;
    3)
        echo "Generating OpenAPI schemas..."
        "$SCRIPT_DIR/generate-openapi.sh"
        echo ""
        echo "OpenAPI schemas generated successfully!"
        echo "Location: $SCRIPT_DIR/api/"
        echo ""
        echo "You can now serve or build the documentation to see the updated API docs."
        ;;
    4)
        echo "Deploying to GitHub Pages..."
        echo ""
        echo "This will:"
        echo "  1. Build the documentation"
        echo "  2. Push to the gh-pages branch"
        echo "  3. Make it available at: https://giacomopauletti.github.io/Benchmarking-AI-Factories/"
        echo ""
        read -p "Are you sure you want to deploy? [y/N]: " confirm
        if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
            echo "Building and deploying..."
            docker compose run --rm docs bash -c "git config --global --add safe.directory / && mkdocs gh-deploy --force"
            echo ""
            echo "Documentation deployed successfully!"
            echo "URL: https://giacomopauletti.github.io/Benchmarking-AI-Factories/"
            echo ""
            echo "Note: It may take a few minutes for changes to appear."
        else
            echo "Deployment cancelled"
        fi
        ;;
    5)
        echo "Building Docker image..."
        docker compose build docs
        echo "Docker image built successfully!"
        ;;
    6)
        echo "Stopping documentation server..."
        docker compose down docs
        echo "Documentation server stopped"
        ;;
    7)
        echo "Showing documentation server logs..."
        echo "Press Ctrl+C to exit"
        docker compose logs -f docs
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

