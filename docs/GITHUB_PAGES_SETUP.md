# GitHub Pages Deployment Guide

This guide explains how to deploy the documentation to GitHub Pages.

## Automatic Deployment (Recommended)

The repository is configured with GitHub Actions to automatically deploy documentation when changes are pushed to the `main` branch.

### Setup Steps

1. **Enable GitHub Pages** (one-time setup):
   - Go to your repository on GitHub: https://github.com/GiacomoPauletti/Benchmarking-AI-Factories
   - Navigate to **Settings** → **Pages**
   - Under **Source**, select **Deploy from a branch**
   - Under **Branch**, select `gh-pages` and `/ (root)`
   - Click **Save**

2. **Grant Workflow Permissions** (one-time setup):
   - Go to **Settings** → **Actions** → **General**
   - Scroll to **Workflow permissions**
   - Select **Read and write permissions**
   - Check **Allow GitHub Actions to create and approve pull requests**
   - Click **Save**

3. **Push your changes to main**:
   ```bash
   git add .
   git commit -m "Update documentation"
   git push origin main
   ```

4. **Monitor deployment**:
   - Go to **Actions** tab in your repository
   - Watch the "Deploy Documentation" workflow run
   - Once complete (green checkmark), your docs are live!

5. **Access your documentation**:
   - URL: https://giacomopauletti.github.io/Benchmarking-AI-Factories/
   - Changes may take 1-2 minutes to appear

### When Automatic Deployment Triggers

The workflow automatically deploys when:
- Changes are pushed to `main` branch
- Changes affect files in `docs/` directory
- Changes to `mkdocs.yml` configuration
- Changes to the workflow file itself

You can also manually trigger deployment:
- Go to **Actions** → **Deploy Documentation**
- Click **Run workflow** → **Run workflow**

## Manual Deployment

If you prefer to deploy manually or from your local machine:

### Option 1: Using the Build Script

```bash
cd docs
./build-docs.sh
# Choose option 4: Deploy to GitHub Pages
```

This will:
1. Build the documentation using Docker
2. Create/update the `gh-pages` branch
3. Push the built site to GitHub
4. Make it available at the GitHub Pages URL

### Option 2: Direct Command

```bash
# Using Docker
docker compose run --rm docs mkdocs gh-deploy --force

# Or without Docker (requires local Python environment)
mkdocs gh-deploy --force
```

### Prerequisites for Manual Deployment

- Git configured with push access to the repository
- Committed all changes (clean working directory)
- On a branch that you want to deploy from (typically `main`)

## Troubleshooting

### Pages not showing up

1. **Check GitHub Pages settings**:
   - Settings → Pages
   - Ensure source is set to `gh-pages` branch

2. **Check workflow status**:
   - Go to Actions tab
   - Look for failed deployments (red X)
   - Click on the workflow to see error details

3. **Check branch exists**:
   ```bash
   git fetch origin
   git branch -r | grep gh-pages
   ```
   Should show `origin/gh-pages`

### 404 Error on GitHub Pages

- Wait 2-3 minutes after deployment
- Check if `gh-pages` branch was created
- Verify GitHub Pages is enabled in repository settings
- Clear browser cache and try again

### Workflow Permission Denied

If you see "Permission denied" in Actions:
- Settings → Actions → General → Workflow permissions
- Enable "Read and write permissions"
- Re-run the workflow

### Build Fails in GitHub Actions

Check the Actions log for specific errors:
- Missing dependencies: Already handled in workflow
- Invalid markdown: Check `docs/` files for syntax errors
- Invalid mkdocs.yml: Validate YAML syntax

### Local Deployment Fails

```bash
# Ensure you're in the project root
cd /path/to/Benchmarking-AI-Factories

# Ensure Docker is running
docker compose ps

# Try rebuilding the docs image
docker compose build docs

# Try deploying again
docker compose run --rm docs mkdocs gh-deploy --force
```

## Custom Domain (Optional)

If you want to use a custom domain instead of `giacomopauletti.github.io`:

1. Add a `CNAME` file to `docs/` directory:
   ```bash
   echo "your-custom-domain.com" > docs/CNAME
   ```

2. Configure DNS with your domain provider:
   - Add a CNAME record pointing to `giacomopauletti.github.io`

3. In GitHub repository settings:
   - Settings → Pages → Custom domain
   - Enter your domain and save

## Deployment Workflow Details

The GitHub Actions workflow (`.github/workflows/deploy-docs.yml`) does:

1. **Checkout code**: Gets the latest repository content
2. **Setup Python**: Installs Python 3.11
3. **Install dependencies**: Installs MkDocs and plugins
4. **Configure Git**: Sets up git identity for commits
5. **Deploy**: Runs `mkdocs gh-deploy` to build and push to `gh-pages`

The workflow runs on:
- Push to `main` branch
- Changes to `docs/**`, `mkdocs.yml`, or workflow file
- Manual trigger via Actions tab

## Directory Structure After Deployment

```
Repository branches:
├── main (or feature branches)
│   ├── docs/           # Source markdown files
│   ├── mkdocs.yml      # MkDocs configuration
│   └── ...             # Other project files
│
└── gh-pages (auto-generated)
    ├── index.html      # Built documentation
    ├── assets/         # CSS, JS, images
    ├── api/            # API documentation pages
    └── ...             # All built HTML files
```

**Important**: Never manually edit the `gh-pages` branch. It's automatically generated and overwritten on each deployment.

## Best Practices

1. **Always commit before deploying**:
   ```bash
   git add docs/
   git commit -m "Update documentation"
   ```

2. **Test locally first**:
   ```bash
   ./docs/build-docs.sh
   # Choose option 1 to serve locally
   # Verify changes at http://localhost:8000
   ```

3. **Update OpenAPI schemas** before deploying:
   ```bash
   ./docs/generate-openapi.sh
   git add docs/api/*.json
   git commit -m "Update OpenAPI schemas"
   ```

4. **Use feature branches** for documentation changes:
   ```bash
   git checkout -b docs/update-api-examples
   # Make changes
   git push origin docs/update-api-examples
   # Create PR to main
   ```

5. **Let CI handle deployment** - Push to main and let GitHub Actions deploy automatically

## URLs

- **Documentation**: https://giacomopauletti.github.io/Benchmarking-AI-Factories/
- **Repository**: https://github.com/GiacomoPauletti/Benchmarking-AI-Factories
- **GitHub Pages Settings**: https://github.com/GiacomoPauletti/Benchmarking-AI-Factories/settings/pages
- **Actions**: https://github.com/GiacomoPauletti/Benchmarking-AI-Factories/actions

## Next Steps

After deployment is working:

1. Add a documentation badge to README.md:
   ```markdown
   [![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://giacomopauletti.github.io/Benchmarking-AI-Factories/)
   ```

2. Link to docs in repository description
3. Share the documentation URL with team members
4. Set up branch protection rules to require docs updates with code changes
