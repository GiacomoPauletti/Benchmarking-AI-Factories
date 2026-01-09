# Documentation Source

This directory contains the **source files** for the project documentation.

## Quick Start

### View Documentation Locally

```bash
# From project root
docker compose up -d docs
# Visit http://localhost:8000
```

The local server auto-reloads when you edit Markdown files in `docs-src/`.

### Rebuild Documentation

If you need to rebuild (e.g., after changing mkdocs.yml or adding plugins):

```bash
# Stop the server
docker compose down docs

# Rebuild the Docker image
docker compose build docs

# Start again
docker compose up -d docs
```

### Build for GitHub Pages

```bash
# From project root
./docs-src/build-for-github-pages.sh
```

This will build the HTML files to the `docs/` directory.

### Publish to GitHub Pages

1. Build the documentation:
   ```bash
   ./docs-src/build-for-github-pages.sh
   ```

2. Commit and push:
   ```bash
   git add docs/
   git commit -m "Update documentation"
   git push
   ```

3. **One-time GitHub setup:**
   - Go to: https://github.com/janmarxen/Benchmarking-AI-Factories/settings/pages
   - Under **Source**, select the branch (`main` or `dev`)
   - Under **Folder**, select `/docs`
   - Click **Save**

4. Documentation will be live at:
   **https://janmarxen.github.io/Benchmarking-AI-Factories/**

## Generate OpenAPI Schemas

Before building, update the API schemas:

```bash
./docs-src/generate-openapi.sh
```

## File Organization

- **docs-src/** - Edit these Markdown files
- **docs/** - Don't edit! Auto-generated HTML (committed to git for GitHub Pages)
- **mkdocs.yml** - MkDocs configuration (in project root)

## Scripts

- `build-for-github-pages.sh` - Build HTML to docs/ folder
- `generate-openapi.sh` - Generate OpenAPI schemas from services

