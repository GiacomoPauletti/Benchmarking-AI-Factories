#!/bin/bash
# Build and run the test container

set -e

echo "🔨 Building AI Factory Test Container"
echo "====================================="

# Navigate to the test directory
cd "$(dirname "${BASH_SOURCE[0]}")/tests"

# Build the container
echo "Building test container..."
if apptainer build test-container.sif test-container.def; then
    echo "✅ Container built successfully"
else
    echo "❌ Container build failed"
    exit 1
fi

# Navigate back to project root (two levels up from server folder)
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

echo ""
echo "🧪 Running Tests in Container"
echo "============================="

# Run the container with project directory bound to /app
if apptainer run --bind "$(pwd):/app" services/server/tests/test-container.sif; then
    echo ""
    echo "🎉 All tests passed!"
    echo ""
    echo "You can now:"
    echo "  git add ."
    echo "  git commit -m 'Add comprehensive testing'"
    echo "  git push origin $(git branch --show-current)"
else
    echo ""
    echo "❌ Tests failed!"
    echo ""
    echo "Check the output above for details."
    exit 1
fi