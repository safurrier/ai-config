# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-03-01

### Added

- Pi as a conversion target — skills map natively (Agent Skills standard), commands map as prompt templates
- Pi user-scope output goes to `~/.pi/agent/skills/` and `~/.pi/agent/prompts/` (matching Pi's discovery paths)
- Pi output validator (`ai-config doctor --target pi`) checks both project and user scope locations
- `--force` alias for `--fresh` on `sync` and `update` commands
- `ai_agent_docs/adding-a-target.md` — step-by-step playbook for adding new conversion targets
- Pi in Docker E2E test image (`@mariozechner/pi-coding-agent`)
- "One config, five tools" example in README showing the full multi-tool sync flow

### Changed

- README and docs reframed around portability — no vendor lock-in, reproducible setup across machines

### Fixed

- Flaky watch integration tests (increased watchdog init and join timeouts)
- `test_no_config_found` failing when `.ai-config/config.yaml` exists in CWD

## [0.3.0] - 2026-02-28

### Added

- Docker-based E2E testing infrastructure
  - `tests/docker/Dockerfile.all-tools` - Full image with Claude Code, OpenAI Codex, OpenCode, Cursor CLI
  - `tests/docker/Dockerfile.claude-only` - Fast image with Claude Code only
  - `tests/docker/test_in_docker.py` - CLI for local Docker testing
  - `tests/e2e/` - E2E test suite validating ai-config with real AI tools
  - `.github/workflows/e2e.yml` - CI workflow for automated E2E testing
- Multi-tool validation for 4 AI coding tools:
  - Claude Code (`npm install -g @anthropic-ai/claude-code`)
  - OpenAI Codex (`npm install -g @openai/codex`)
  - OpenCode (`npm install -g opencode-ai`)
  - Cursor CLI (`curl -fsSL https://cursor.com/install | bash`)
- New pytest markers: `@pytest.mark.e2e`, `@pytest.mark.docker`, `@pytest.mark.slow`
- Conversion config section persisted by `ai-config init`
- Sync-driven conversion pipeline with scope-based output defaults
- Conversion report file output (`--report`, `--report-format`)
- Binary asset support in skill conversion
- Env var syntax transformation for Cursor/OpenCode MCP outputs
- Multi-LSP aggregation for OpenCode conversion
- Codex project-scope prompt warnings with remediation guidance
- Conversion hash cache with `--force-convert` override

### Changed

- `ai-config convert` supports `--scope` for output path resolution
- Codex prompts emit to `.codex/prompts/` relative to output root
- Name normalization for plugin/skill parsing to improve portability

### Fixed

- `ai-config sync` now exits non-zero when sync errors occur
- Prevent OpenCode LSP config from overwriting when multiple servers exist
- Interactive wizard now defaults to no plugins selected (user must opt-in)
- ESC key cancels prompts in `ai-config init` wizard
- MCP validator supports HTTP and SSE transport types (not just stdio)
- GitHub marketplace name now read from `marketplace.json` instead of URL slug
- `ai-config sync` detects and reports marketplace name mismatches

## [0.1.0] - 2025-02-03

### Added

- Initial release
- `init` command - interactive config generator
- `sync` command - install/uninstall plugins to match config
- `status` command - show current plugin state
- `watch` command - auto-sync on file changes
- `update` command - update plugins to latest versions
- `doctor` command - validate setup with fix hints
- `plugin create` command - scaffold new plugins
- `cache clear` command - clear plugin cache
- Support for GitHub and local marketplaces
- User and project scope plugin installation

[Unreleased]: https://github.com/safurrier/ai-config/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/safurrier/ai-config/releases/tag/v0.1.0
