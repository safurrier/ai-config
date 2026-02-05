# ai-config

Declarative plugin manager for Claude Code.

## Why This Exists

Claude Code plugins let you extend Claude with custom skills, hooks, and MCP servers. Managing them manually (`claude plugin install`, `claude plugin marketplace add`) doesn't scale across machines or teams.

ai-config provides a YAML config file for declarative plugin management. Define what you want, run `ai-config sync`, done.

## Repo Map

```
src/ai_config/
├── cli.py           # Click CLI entry point
├── config.py        # Config file parsing
├── operations.py    # sync, update, status logic
├── init.py          # Interactive setup wizard
├── watch.py         # File watcher for dev mode
├── adapters/        # Tool-specific adapters (claude.py)
└── validators/      # Validation (plugins, skills, hooks, MCP)
tests/
├── unit/            # Fast unit tests (374 tests)
├── integration/     # Integration tests (marked)
├── e2e/             # Docker-based E2E tests
│   ├── conftest.py      # Docker fixtures
│   ├── test_fresh_install.py  # Claude-only sync tests
│   └── test_multi_tool.py     # Multi-tool installation tests
├── docker/          # Docker test infrastructure
│   ├── Dockerfile.claude-only  # Fast image with Claude Code only
│   ├── Dockerfile.all-tools    # Full image with 4 AI tools
│   └── test_in_docker.py       # CLI for local Docker testing
└── fixtures/        # Test data
    └── test-marketplace/       # Local marketplace for E2E tests
```

## How to Work Here

1. **Setup**: `uv sync --all-extras`
2. **Make changes**
3. **Validate**: `uv run ruff check src/ && uv run ty check src/ && uv run pytest tests/unit/ -v`
4. **Commit** when all checks pass

## Commands

All commands use `uv run` (or `just` if installed).

| Task | Command |
|------|---------|
| Install deps | `uv sync --all-extras` |
| Lint | `uv run ruff check src/` |
| Format | `uv run ruff format src/` |
| Fix lint | `uv run ruff check src/ --fix` |
| Type check | `uv run ty check src/` |
| All checks | `uv run ruff check src/ && uv run ty check src/ && uv run pytest tests/ -v` |
| Unit tests | `uv run pytest tests/unit/ -v` |
| Single test | `uv run pytest tests/unit/test_foo.py -v` |
| Coverage | `uv run pytest tests/ -v --cov=src/ai_config --cov-report=term-missing` |
| Docs serve | `uv run mkdocs serve` |
| E2E tests (Claude) | `uv run pytest tests/e2e/ -m "e2e and docker" -v` |
| E2E tests (all tools) | `uv run pytest tests/e2e/ -m "e2e and docker and slow" -v` |
| Docker shell | `python tests/docker/test_in_docker.py --shell` |
| Docker build | `python tests/docker/test_in_docker.py --build-only` |

If `just` is available, use `just check` (runs lint + ty + test).

## Code Style

Enforced by tooling—don't memorize rules, run the tools:

- **Formatting**: `ruff format` (line-length 100)
- **Linting**: `ruff check` with autofix
- **Types**: `ty check` with strict mode

Conventions:
- Python 3.9+ syntax
- Type annotations required
- Imports: stdlib → third-party → local (enforced by ruff isort)

## Testing

- Unit tests in `tests/unit/` - fast, no external deps
- Integration tests marked with `@pytest.mark.integration`
- E2E tests in `tests/e2e/` - Docker-based, validates real tool interactions
- Run single test: `uv run pytest tests/unit/test_config.py::test_name -v`

### E2E Testing with Docker

E2E tests run in Docker containers to validate ai-config works with real AI coding tools.

**Two Docker images available:**

| Image | Tools | Use Case |
|-------|-------|----------|
| `all-tools` | Claude, Codex, OpenCode, Cursor | Default - full multi-tool validation |
| `claude-only` | Claude Code | Fast local testing |

**Running E2E tests locally:**

```bash
# Default: All tools tests
python tests/docker/test_in_docker.py

# Fast: Claude-only tests (quicker builds)
python tests/docker/test_in_docker.py --claude-only

# Debug: Interactive shell
python tests/docker/test_in_docker.py --shell

# Rebuild image from scratch
python tests/docker/test_in_docker.py --rebuild
```

**Pytest markers:**
- `@pytest.mark.e2e` - All E2E tests
- `@pytest.mark.docker` - Tests requiring Docker
- `@pytest.mark.slow` - Tests using all-tools image

**Multi-tool support:**

ai-config is designed to support multiple AI coding tools. Current installation methods:

| Tool | Install Command | Binary |
|------|-----------------|--------|
| Claude Code | `npm install -g @anthropic-ai/claude-code` | `claude` |
| OpenAI Codex | `npm install -g @openai/codex` | `codex` |
| OpenCode | `npm install -g opencode-ai` | `opencode` |
| Cursor CLI | `curl -fsSL https://cursor.com/install \| bash` | `cursor-agent` |

## Releases

**Before merging a PR with user-facing changes:**
1. Update `CHANGELOG.md` under `[Unreleased]` section
2. Use Keep a Changelog format: Added, Changed, Deprecated, Removed, Fixed, Security

**To release a new version:**
1. Move `[Unreleased]` entries to new version section with date
2. Update version in `pyproject.toml`
3. Update comparison links at bottom of CHANGELOG.md
4. Create PR, merge to main
5. Create GitHub release with tag `vX.Y.Z` (this auto-publishes to PyPI)

Version is in `pyproject.toml` (currently `0.1.0`). Tags use `v` prefix (e.g., `v0.1.0`).

### PyPI Publishing

Publishing is automated via GitHub Actions (`.github/workflows/publish.yml`):
- Triggered when a GitHub Release is published
- Uses trusted publishing (no API tokens needed)
- Requires PyPI environment configured in repo settings

**One-time setup (repo admin):**
1. Go to PyPI → Account settings → Publishing
2. Add trusted publisher: GitHub, `safurrier/ai-config`, workflow `publish.yml`, environment `pypi`
3. Go to GitHub repo → Settings → Environments → Create `pypi` environment

## Nested Docs

- `src/AGENTS.md` - Code patterns, validator/CLI extension guides

## Gotchas

- **Claude Code reloads plugins at session start** - after `ai-config sync`, restart Claude Code (use `claude --resume` to continue)
- **Config locations**: `.ai-config/config.yaml` (project) or `~/.ai-config/config.yaml` (global)
- **Scopes**: `user` scope installs to `~/.claude/plugins/`, `project` scope to `.claude/plugins/`
- **Docker E2E tests require Docker** - use `docker info` to verify Docker is running
- **Cursor CLI binary is `cursor-agent`** - not `cursor` (the desktop app uses `cursor`)
- **E2E tests are class-scoped** - tests in the same class share a container, different classes get fresh containers
