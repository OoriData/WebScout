WordLoom Contributor Guide

# Quick Reference

## Why We Use `uv pip install -U .`

This project uses a source layout where `pylib/` becomes `wordloom/` during package building. This remapping only happens during wheel building, not in development environments.

**Why not use hatch environments?**
- Hatch's path remapping (`tool.hatch.build.sources`) only applies during wheel building
- Hatch's dev-mode uses editable installs which can't apply the source remapping
- Setting `dev-mode=false` means no install happens at all

**Solution:** We use proper package installation (`uv pip install -U .`) instead of editable/dev-mode installs. This ensures the source remapping is applied correctly and your development environment matches the built package.

## Daily Development

```bash
# Install in current virtualenv
uv pip install -U .

# Run tests
pytest test/ -v

# Run specific test file
pytest test/test_basics.py -v

# Run linting
ruff check .

# Auto-fix linting issues
ruff check --fix .

# Run tests with coverage
pytest test/ --cov=wordloom --cov-report=html
```

## Making Changes

```bash
# After editing any Python files in pylib/
uv pip install -U .

# After editing resources/
uv pip install -U .

# After editing tests only (no reinstall needed)
pytest test/ -v
```

## Useful Commands

```bash
# See package structure after install
python -c "import wordloom, os; print(os.path.dirname(wordloom.__file__))"
ls -la $(python -c "import wordloom, os; print(os.path.dirname(wordloom.__file__))")

# Check what files are in the installed package
pip show -f wordloom

# Check installed version
python -c "import wordloom; print(wordloom.__version__)"

# Compare source version
cat pylib/__about__.py

# Uninstall completely
pip uninstall wordloom -y

# Clean build artifacts
rm -rf build/ dist/ *.egg-info
rm -rf .pytest_cache .ruff_cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
```

## Testing Package Build Locally

```bash
# Build locally
python -m build
python -m build -w  # For some reason needs to need both, in this order. Probably an issue in how we're using hatch

# Test the built wheel
pip install dist/wordloom-0.X.Y-py3-none-any.whl --force-reinstall

# Check package contents
unzip -l dist/wordloom-0.X.Y-py3-none-any.whl
```

# Project Structure

```
WordLoom/
├── pylib/              # Source code (becomes 'wordloom' package)
│   ├── __init__.py
│   ├── __about__.py    # Version info
│   └── wordloom.py     # Main implementation
├── resources/          # Bundled resources
│   └── wordloom/
│       └── sample.toml
├── test/               # Tests
│   ├── test_basics.py
│   ├── test_i18n_integration.py
│   └── test_openai_integration.py
├── pyproject.toml      # Project config
└── README.md

When installed, becomes:
site-packages/
└── wordloom/
    ├── __init__.py
    ├── __about__.py
    ├── wordloom.py
    └── resources/
        └── wordloom/
            └── sample.toml
```

When installed, becomes:

```
site-packages/
└── wordloom/
    ├── __init__.py
    ├── __about__.py
    ├── wordloom.py
    └── resources/
        └── wordloom/
            └── sample.toml
```

## Key Files

- `pylib/__about__.py` - Version number (update for releases)
- `pyproject.toml` - Dependencies, metadata, build config
- `resources/wordloom/sample.toml` - Sample file used by tests
- `README.md` - Main documentation
- `wordloom_spec.md` - Format specification (CC BY 4.0)

# Publishing a Release

Before creating a release:

- [ ] Update version in `pylib/__about__.py`
- [ ] Update CHANGELOG.md
- [ ] Run tests locally: `pytest test/ -v`
- [ ] Run linting: `ruff check .`
- [ ] Commit and push all changes
<!-- 
- [ ] Create git tag: `git tag v0.X.Y`
- [ ] Push tag: `git push origin v0.X.Y`
 -->
- [ ] [Create GitHub release](https://github.com/OoriData/WordLoom/releases/new) (triggers publish workflow)
- [ ] Verify package update on PyPI: https://pypi.org/project/wordloom/

## Testing the Package

After publishing, test the installation:

```bash
# Create a fresh virtual environment
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate

# Install from PyPI
pip install wordloom

# Test import
python -c "import wordloom; print(wordloom.__version__)"

# Test basic functionality
python -c "
import wordloom
import io

toml_data = b'''
lang = 'en'
[test]
_ = 'Hello'
'''

loom = wordloom.load(io.BytesIO(toml_data))
print(loom['test'])
"
```

# Initial Project Setup

Historical, and to inform maintenance. GitHub Actions & PyPI publishing.

## GitHub Actions Setup

The repository includes two workflows:

### 1. CI Workflow (`.github/workflows/main.yml`)

Runs automatically on every push and pull request. It:
- Tests on Python 3.12 and 3.13
- Runs ruff linting
- Runs pytest test suite

### 2. Publish Workflow (`.github/workflows/publish.yml`)

Runs when you create a new GitHub release. It builds and publishes to PyPI.

## PyPI Trusted Publishing Setup

###  PyPI Setup

- Login your [PyPI](https://pypi.org) account
- For new package:
    - Go to: https://pypi.org/manage/account/publishing/
    - Click "Add a new pending publisher"
    - Fill in:
    - **PyPI Project Name**: `wordloom` (must match `name` in `pyproject.toml`, with case)
    - **Owner**: `OoriData`
    - **Repository name**: `WordLoom`
    - **Workflow name**: `publish.yml`
    - **Environment name**: `pypi` (PyPI's recommended name)
- If the package already exists on PyPI:
    - Go to the project page: https://pypi.org/manage/project/wordloom/settings/publishing/
    - Add the publisher configuration as above

### GitHub Setup
- Go to: https://github.com/OoriData/WordLoom/settings/environments
- Click "New environment"
- Name: `pypi`
- Click "Configure environment"
- (Optional) Add protection rules:
    - Required reviewers: Add yourself to require manual approval before publishing
    - Wait timer: Add a delay (e.g., 5 minutes) before publishing
- Click "Save protection rules"

### Note on using the environment name

Using an environment name (`pypi`) adds an extra layer of protection, with rules such as required reviewers (manual approval before publishing), wait timers (delay before publishing) and branch restrictions. Without an environment stipulation the workflow runs automatically when a release is created.

## First Time Publishing

Option on the very first release to PyPI: may want to do a manual publish to ensure everything is set up correctly:

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# For some reason, the wheel only seems to work if you build first without then with `-w`
python -m build -w

# Basic build check
twine check dist/*

# Extra checking
VERSION=0.10.0 pip install --force-reinstall -U dist/wordloom-$VERSION-py3-none-any.whl
python -c "from wordloom import load"

# Upload to Test PyPI first (optional but recommended)
twine upload --repository testpypi dist/*
# Username: __token__
# Password: your-test-pypi-token

# If test looks good, upload to real PyPI
twine upload dist/*
# Username: __token__
# Password: your-pypi-token
```

After the first manual upload, you can use trusted publishing for all future releases.

## Troubleshooting

### "Project name 'wordloom' is not valid"
- Check that the name in `pyproject.toml` matches exactly
- Names are case-insensitive but must match what you registered on PyPI

### "Invalid or non-existent authentication information"
- For trusted publishing: Double-check the repository name, owner, and workflow name
- For token auth: Make sure the token is saved as `PYPI_API_TOKEN` in GitHub secrets

### Workflow fails with "Resource not accessible by integration"
- Make sure the workflow has `id-token: write` permission
- Check that the repository settings allow GitHub Actions

### Package version already exists
- You can't overwrite versions on PyPI
- Increment the version in `pylib/__about__.py` and create a new release

## Additional Resources

- [PyPI Trusted Publishing Guide](https://docs.pypi.org/trusted-publishers/)
- [GitHub Actions for Python](https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-python)
- [Python Packaging Guide](https://packaging.python.org/en/latest/)
