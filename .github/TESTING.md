# Testing Workflow Guide

## Automated Testing Setup

### When Tests Run
✅ **Push to `dev` branch** - Tests run automatically  
✅ **Pull Request to `dev`** - Tests run before merge  
✅ **Only when server code changes** - Efficient, focused testing

### Your Workflow

#### 1. Development on Feature Branch
```bash
# Work on your feature branch
git checkout -b feature/your-feature-name

# Make changes to server code
# Run tests locally (optional but recommended)
cd services/server
python -m pytest tests/test_simple_api.py -v
```

#### 2. Push to Dev Branch
```bash
# When ready, merge to dev and push
git checkout dev
git merge feature/your-feature-name
git push origin dev

# ✅ GitHub Actions automatically runs tests
# ✅ You get email/notification if tests fail
# ✅ GitHub shows test status on the repo
```

#### 3. Check Test Results
- Go to your GitHub repo → **Actions** tab
- See test results in real-time
- Green ✅ = tests passed
- Red ❌ = tests failed (check logs)

### Local Testing (Recommended)
```bash
# Quick test before pushing
cd services/server
python -m pytest tests/test_simple_api.py

# Full test suite
python -m pytest tests/ -v
```

### What the Workflow Does
1. **Triggers**: Only when you push server code to `dev` branch
2. **Environment**: Sets up Python 3.11 on Ubuntu
3. **Dependencies**: Installs your server requirements + test requirements
4. **Tests**: Runs all tests in `services/server/tests/`
5. **Results**: Shows pass/fail status on GitHub

### Benefits
- **Fast feedback**: Know immediately if your code breaks anything
- **Prevents bad merges**: Catches issues before they reach main branch
- **Team coordination**: Everyone sees test status
- **Simple setup**: No complex configuration needed

### If Tests Fail
1. Check the GitHub Actions log for error details
2. Fix the issue locally
3. Push the fix to `dev` branch
4. Tests will run again automatically

### File Structure
```
.github/
└── workflows/
    └── server-tests.yml    # The automation workflow
```

This workflow only tests server changes and only runs when needed - keeping it simple and efficient!