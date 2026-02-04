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
├── unit/            # Fast unit tests
└── integration/     # Integration tests (marked)
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
- Run single test: `uv run pytest tests/unit/test_config.py::test_name -v`

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
