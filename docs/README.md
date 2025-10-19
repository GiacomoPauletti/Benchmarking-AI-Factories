# Documentation Build Instructions

This directory contains the MkDocs-based documentation for the AI Factory Benchmarking Framework.

## Quick Start

### View Documentation Locally

```bash
# Install dependencies
pip install -r docs-requirements.txt

# Serve documentation (live reload)
mkdocs serve

# Open browser to http://127.0.0.1:8000
```

### Build Static Site

```bash
# Build documentation
mkdocs build

# Output will be in site/
# Open site/index.html in your browser
```

### Using the Build Script

```bash
./build-docs.sh
```

The script provides options to:
1. Serve locally
2. Build static site
3. Install dependencies
4. Deploy to GitHub Pages


## FastAPI Documentation Integration

The FastAPI documentation is integrated in two ways:

### 1. Embedded (iframe)

In `docs_site/api/server.md`, the FastAPI docs are embedded via iframe:

```html
<iframe src="http://localhost:8001/docs" width="100%" height="600px"></iframe>
```

**Note**: Users need to replace `localhost:8001` with their actual server endpoint.

---

For more information, visit the [MkDocs Documentation](https://www.mkdocs.org/) and [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).
