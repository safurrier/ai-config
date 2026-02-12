# Conversion Quality Upgrade (B- → A)

**Date**: 2026-02-06
**Branch**: `research/plugin-conversion-feasibility`
**Owner**: Alex

## Problem Statement
The plugin conversion pipeline is functional but has correctness gaps, incomplete plan items, and workflow inconsistencies that keep it at a B- level. We need to fix known bugs, close the outstanding plan items, and raise reliability and operator clarity to an A.

## Goals
1. Eliminate correctness bugs surfaced in review (multi-LSP overwrite, Codex prompt path, name normalization failures, report misclassification, output_dir behavior mismatch).
2. Implement previously identified missing features (env var syntax transform, binary file handling, command format verification, conversion report output, init conversion follow-through).
3. Strengthen validation and test coverage (unit + E2E + CI + docs) without regressing existing behavior.

## Scope
- Parsing/IR robustness (name normalization, error handling)
- Emitters (path correctness, multi-LSP aggregation, env var transforms, binary files)
- Conversion reporting (lost features classification, report file output)
- Init wizard (persist/execute conversion selections)
- Target validators + doctor
- Docs + CI + E2E tests

## Out of Scope
- Auto-conversion during `ai-config sync` when conversion is not configured
- New target tools beyond Codex/Cursor/OpenCode
- Full rewrite of configuration schema outside minimal conversion section

## Requirements
- **Correctness**
  - Multi-LSP plugins must emit a single OpenCode LSP config with all servers.
  - Codex user-scope prompts must land under `~/.codex/prompts/` (or `.codex/prompts` in output).
  - Codex project-scope prompts should warn (not auto-convert) since prompts are only loaded from `~/.codex/prompts/`.
  - Warning should include instructions to use `--commands-as-skills` or user scope to make commands discoverable.
  - Plugin and skill names must normalize safely without crashing conversion.
  - `convert_plugin` must align output behavior with documentation.
  - Lost-features reporting must reflect true loss, not preserved variables.

- **Feature Completeness**
  - Env var syntax transformation for MCP outputs per target.
  - Binary file support in skill directories (parse + emit).
  - Confirm Codex/OpenCode command formats and update emitters if needed.
  - CLI option to write conversion reports to file.
  - Init wizard must persist conversion selections and optionally run sync.
  - `ai-config sync` must perform conversion when configured, using scope-based output defaults.
  - Scope → output: `user` ⇒ `Path.home()`, `project` ⇒ `Path.cwd()` (unless overridden).
  - Conversion outputs are treated as derived artifacts and may be overwritten on sync.
  - Add hash-based change detection to skip unnecessary conversions; provide `--force-convert` to bypass cache.

- **Validation & Docs**
  - Add tests for new behaviors (unit + targeted E2E).
  - Manual tmux-driven validation of conversion behaviors (prompt paths, env var syntax, LSP aggregation, binary files).
  - Update `CLAUDE.md` with tmux/E2E instructions.
  - Update CI to run tmux E2E tests with timeouts.
  - Update `CHANGELOG.md` for user-facing changes.

- **Test Coverage Targets**
  - Unit: sync-driven conversion wiring, scope→output resolution, name normalization, multi-LSP aggregation, env var transform, binary files, report output.
  - E2E (Docker): convert outputs recognized by tools (multi-LSP, prompts path, env vars, binaries), tmux tool validation remains fail-loudly.

## Constraints
- Keep backwards compatibility for existing config when possible.
- Avoid breaking CLI behaviors unless documented.
- Tests should remain fast; E2E tests gated to Docker.

## Success Criteria
- All known bugs fixed with tests covering them.
- New features implemented and documented.
- `ruff`, `ty`, `pytest tests/unit/` pass locally.
- E2E tests pass in Docker images (claude-only + all-tools where relevant).
- Reviewer assessment = A (no high/medium severity issues, clear gaps closed).

## Skill Discovery
Available skills in repo (fixtures only):
- `tests/fixtures/test-marketplace/test-plugin/skills/test-skill/SKILL.md`
- `tests/fixtures/sample-plugins/complete-plugin/skills/test-writer/SKILL.md`
- `tests/fixtures/sample-plugins/complete-plugin/skills/code-review/SKILL.md`
- `tests/fixtures/sample-plugins/complete-plugin/skills/category/nested-skill/SKILL.md`

Relevance checklist:
- [ ] test-skill - E2E fixture only
- [ ] test-writer - fixture only
- [ ] code-review - fixture only
- [ ] nested-skill - fixture only

No relevant skills to load for this plan. Baseline skills listed in `AGENTS.md` are not present in repo.
