# ai-config development tasks

default:
    @just --list

# Install all dependencies
setup:
    uv sync --all-extras

# Run all code quality checks
check: lint ty test

# Lint source code
lint:
    uv run ruff check src/

# Format source code
format:
    uv run ruff format src/

# Fix linting issues
fix:
    uv run ruff check src/ --fix

# Type check with ty
ty:
    uv run ty check src/

# Run tests
test:
    uv run pytest tests/ -v

# Run tests with coverage
test-cov:
    uv run pytest tests/ -v --cov=src/ai_config --cov-report=term-missing

# Run specific test file
test-file file:
    uv run pytest {{file}} -v

# Clean build artifacts
clean:
    rm -rf .ruff_cache .ty_cache .pytest_cache site/ dist/ build/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Build package
build:
    uv build

# Install in development mode
dev:
    uv pip install -e .

# Serve documentation locally
docs-serve:
    uv run mkdocs serve

# Build documentation
docs-build:
    uv run mkdocs build

# Install pre-commit hooks
hooks:
    uv run pre-commit install

# Run pre-commit on all files
pre-commit:
    uv run pre-commit run --all-files

# Docker dev shells (no local pollution)
docker-shell:
    uv run python tests/docker/test_in_docker.py --shell

docker-shell-claude:
    uv run python tests/docker/test_in_docker.py --shell --claude-only

# Persistent Docker dev container (attachable)
docker-dev-up:
    uv run python tests/docker/test_in_docker.py --build-only
    docker rm -f ai-config-dev 2>/dev/null || true
    docker run -d --name ai-config-dev -v {{pwd}}:/home/testuser/ai-config -w /home/testuser/ai-config -u testuser ai-config-test:all-tools sleep infinity

docker-dev-attach:
    docker exec -it ai-config-dev /bin/bash

docker-dev-down:
    docker rm -f ai-config-dev
