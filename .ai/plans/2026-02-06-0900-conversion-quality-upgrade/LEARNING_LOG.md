# Learning Log

## 2026-02-06: Plan Created

### Context
Plan created to raise conversion pipeline from B- to A by fixing known bugs and completing outstanding plan items.

### Notes
- Baseline skills listed in `AGENTS.md` are not present in this repo; only fixture skills exist and are not relevant to this plan.
- Biggest correctness risks identified: multi-LSP overwrite, Codex user-scope prompt path, and name normalization failures.
- Decision direction: conversion should be sync-driven with scope-based output defaults; tmux tests should fail loudly when tmux is missing.

### Open Questions
- What is the current authoritative command format for Codex and OpenCode?
- Should `convert_plugin` default to writing output or remain no-op unless `output_dir` set?

## 2026-02-06: Research Notes (Command Formats)

### Codex Custom Prompts
- OpenAI docs confirm custom prompts are **deprecated** and live under `~/.codex/prompts/` with `/prompts:<name>` invocation. They are explicitly described as local to the Codex home directory and not shared via repository. This suggests project-scoped `.codex/prompts/` is likely **not** recognized. citeturn1search0

### OpenCode Commands
- OpenCode docs show commands are defined in `.opencode/commands/<name>.md` with YAML frontmatter (description/agent/model) and invoked via `/name`. The current emitter path `.opencode/commands/` matches docs. citeturn1search3

### Decision
- For Codex + project scope, keep emitting prompts but **warn with instructions**: recommend `--commands-as-skills` for project scope or use `scope=user` to target `~/.codex/prompts/`.

## 2026-02-06: Codebase Conventions Sweep

### Findings
- `src/AGENTS.md` documents core patterns: frozen dataclasses + tuple collections for config types, `_parse_*` loaders with `ConfigError` hierarchy, async validators via `ValidationResult`, and CLI organization that keeps business logic out of Click layer.
- Validators are async (`Validator` protocol + `asyncio.gather`), so new validation rules should be non-blocking and return `pass|warn|fail` with `fix_hint`.
- E2E tests rely on Docker helpers in `tests/e2e/conftest.py` plus tmux helpers in `tests/e2e/tmux_helper.py`; tmux is a hard requirement (fail loudly).
- Adapters wrap subprocess calls to external tools (no raw exceptions); new tool calls should follow this pattern.

## 2026-02-06: Manual Tmux Validation

### Notes
- Ran a tmux-driven manual validation script that executes conversions and checks outputs.
- Verified: Codex user-scope prompts path, Cursor/OpenCode env var syntax, OpenCode multi-LSP aggregation, binary file emission, report file output.
- Final run reported `ALL_OK`. Log captured under `/tmp/ai-config-tmux-manual-1770361551/tmux.log`.

## 2026-02-06: Manual Tmux Validation (Re-run)

### Notes
- Initial tmux script failed due to prompt filename mismatch, LSP key prefixing, env var regex, and using `python` instead of `python3`.
- Updated checks and reran successfully; final log captured under `/tmp/ai-config-tmux-manual-4bDS/tmux.log`.

## 2026-02-06: Docker E2E Claude Prompts

### Notes
- All-tools E2E failed in `TestInteractiveClaudeSkillDiscovery` due to new Claude first-run prompts.
- Addressed by:
  - Dismissing theme prompt via `Enter` fallback to `1`.
  - Handling login method selection via `Down` + `Enter`.
  - Injecting `ANTHROPIC_API_KEY` into tmux session and typing key when prompted.
- Re-ran all-tools E2E suite to confirm pass.
