# Implementation Plan

## Phase 0: Research & Decisions
1. **Confirm command formats**
   - Codex: verify current support for `.codex/prompts/` vs skills-as-commands.
   - OpenCode: verify commands directory name (`commands` vs `command`) and any frontmatter requirements.
   - Output: brief notes in LEARNING_LOG.

2. **Decide conversion execution model**
   - Conversion is executed by `ai-config sync` when configured.
   - `convert_plugin` remains explicit (no implicit write unless `output_dir` provided).
   - CLI `ai-config convert` and `sync` resolve `output_dir` from scope unless `--output` provided.

## Codebase Conventions (Observed)
- **Modules**: CLI entry in `src/ai_config/cli.py`, business logic in `src/ai_config/operations.py`, config parsing in `src/ai_config/config.py`, schema types in `src/ai_config/types.py`, conversion under `src/ai_config/converters/`, validators under `src/ai_config/validators/`.
- **Schema/Types**: `types.py` uses frozen dataclasses + tuples for collections; validation in `__post_init__` with explicit error messages.
- **Config parsing**: `_parse_*` helpers in `config.py`, structured `ConfigError` hierarchy, relative paths resolved against config parent (repo root).
- **CLI rendering**: Rich console via `cli_theme.create_console`, consistent iconography via `SYMBOLS`, and `cli_render.py` for formatted sections.
- **Validators**: `Validator` protocol returns `list[ValidationResult]` with `pass|warn|fail`; async validation aggregated with `asyncio.gather` and `fix_hint` on actionable failures.
- **Adapters**: Tool adapters (e.g., `adapters/claude.py`) wrap subprocess calls and normalize errors (avoid raw exceptions).
- **Unit tests**: per-module tests in `tests/unit/`, class-based `Test*` groupings, docstring per test, `pytest` + `CliRunner` for CLI, `unittest.mock.patch` for adapter/operations interactions.
- **E2E tests**: Docker fixtures in `tests/e2e/conftest.py`, `exec_in_container` helper, tmux helper in `tests/e2e/tmux_helper.py`, tests execute `uv run ai-config ...` inside containers.
- **Fixtures & data**: plugin fixtures under `tests/fixtures/`, sample plugin includes commands/skills/hooks/MCP/LSP; use these for test inputs.

## Phase 0.5: TDD Test Additions (Before Implementation)
1. **Unit tests**
   - Add CLI tests in `tests/unit/test_cli.py` using `CliRunner` + `patch` for sync/convert path resolution.
   - Add operations tests in `tests/unit/test_operations.py` with `patch` on `ai_config.operations` for sync-driven conversion wiring.
   - Add conversion tests in `tests/unit/converters/test_conversion.py` for multi-LSP aggregation, env var transforms, binary files, prompt warnings.
   - Add config/type tests in `tests/unit/test_config.py` and `tests/unit/test_types.py` for new conversion schema.
   - Add report output tests in `tests/unit/test_cli.py` or new `tests/unit/converters/test_report_output.py`.

2. **E2E tests (Docker)**
   - Extend `tests/e2e/test_conversion.py` or `tests/e2e/test_tool_validation.py` with new cases.
   - Use `exec_in_container` to run `uv run ai-config convert` and validate filesystem outputs.

## Phase 1: Parser/IR Robustness
1. **Safe slugification utilities**
   - Add shared helper for `plugin_id` and `skill.name` normalization.
   - Rules: lowercase, replace spaces/underscores with `-`, strip invalid chars, collapse multiple `-`, trim length, fallback if empty.

2. **Catch validation exceptions**
   - Wrap `PluginIdentity` and `Skill` creation in `try/except` for `ValidationError`.
   - Emit diagnostics and continue (best-effort should not crash).
   - If normalization changes names, emit WARN diagnostics.

3. **Tests**
   - Non-kebab plugin names (spaces/punctuation) should not crash.
   - Non-kebab skill names normalize or skip with warnings.
   - Ensure normalization respects 64-char limit.

## Phase 2: Emitters Fixes
1. **Codex prompt path fix**
   - Ensure user-scope prompts emit to `.codex/prompts/` under output root.
   - If scope=project and commands-as-prompts, emit WARN that Codex only loads prompts from `~/.codex/prompts/` and provide instructions:
     - Use `--commands-as-skills` to make commands discoverable in project scope.
     - Or run conversion with `scope=user` to place prompts in `~/.codex/prompts/`.
   - Add tests for user scope + output path correctness.

2. **OpenCode LSP aggregation**
   - Accumulate all LSP servers into a single `opencode.lsp.json` write.
   - Ensure conversion does not overwrite earlier servers.
   - Add tests with multiple LSP servers.

3. **Env var syntax transformation**
   - Implement `transform_env_vars()` that maps between `${VAR}`, `${env:VAR}`, `{env:VAR}`.
   - Apply in MCP emission for Cursor + OpenCode outputs.
   - Update tests that currently assert “preserved syntax”.

4. **Binary file support**
   - Parse binary files into IR (base64) instead of skipping.
   - Emit binary files in all emitters.
   - Add tests for binary file round-trip (parse → emit).

5. **Command format updates (if research requires)**
   - Update Codex/OpenCode command emitters to match current formats.
   - Update validators + tests accordingly.

## Phase 3: Conversion Reporting & CLI
1. **Lost-features classification**
   - Replace heuristic “notes contains variable” with explicit `lost_features` from emitters.
   - Adjust reports to reflect actual loss.

2. **Report output files**
   - Add `--report <path>` and `--report-format` to `ai-config convert`.
   - Support JSON and Markdown output.

3. **Scope-based output resolution**
   - For CLI `convert` and `sync`: `scope=user` ⇒ `Path.home()`, `scope=project` ⇒ `Path.cwd()`.
   - Allow explicit `--output` to override scope mapping.
   - Update docstrings + tests to match.

## Phase 4: Init Wizard + Sync Integration
1. **Persist conversion selection**
   - Extend config schema to include optional `conversion` section.
   - Update config parsing/validation to ignore when absent.

2. **Defer conversion to sync (with optional prompt)**
   - Init writes conversion settings but does not convert immediately.
   - Offer “run sync now?” prompt at end of init.
   - If accepted, run `ai-config sync` which performs conversion.

3. **Tests**
   - Init generates config with `conversion` section.
   - Sync executes conversion using scope-based output path.

## Phase 5: Sync Conversion Pipeline
1. **Sync executes conversion when configured**
   - After Claude plugin sync, convert configured plugins to targets.
   - Use scope-based output directory defaults if not overridden.
   - Overwrite converted outputs (derived artifacts).

2. **Change detection (required)**
   - Compute hash over source plugin directories to skip unnecessary conversion.
   - Cache under `~/.ai-config/cache/conversion-hashes.json` keyed by plugin path + conversion signature.
   - Add `--force-convert` flag to bypass hash and always re-convert.

## Phase 6: Validators & Doctor
1. **Target validators**
   - Validate `opencode.lsp.json` contains all servers.
   - Validate env var syntax where feasible (warn if mismatched).

2. **Doctor target mode**
   - Ensure results match updated outputs and new config paths.

## Phase 7: E2E + CI + Docs
1. **E2E tests**
   - Add test for multi-LSP OpenCode output.
   - Add test for Codex user-scope prompt path.
   - Add test for env var syntax transformation.
   - Add binary file emission test (fixture).

2. **Tmux availability behavior**
   - Keep tmux-dependent tests fail-loudly when tmux missing (explicit requirement).
   - Add manual tmux-driven checks for conversion outputs (prompts, env vars, LSP aggregation, binaries, report output).

3. **Docs & CI**
   - Update `CLAUDE.md` with tmux E2E instructions and tool validation commands.
   - Update CI workflow to include tmux tests and timeouts.

4. **Changelog**
   - Add conversion fixes + new features to `[Unreleased]`.

## Manual Tmux Validation Runbook (Local)
Use a tmux-driven session to validate end-to-end behavior and capture logs for review.

1. **Setup**
   - Start tmux session in repo root.
   - `uv sync --all-extras` to ensure CLI dependencies are present.

2. **Codex user-scope prompts**
   - Convert sample plugin with `--target codex --scope user --output <tmp>`.
   - Validate `.codex/prompts/commit.md` exists under output root.

3. **OpenCode aggregation + env vars**
   - Create a temp plugin with two LSP servers and MCP env vars.
   - Convert to `--target opencode`, verify `opencode.lsp.json` contains both servers.
   - Validate env var syntax uses `{env:VAR}` in `opencode.json`.

4. **Cursor env vars**
   - Convert the same temp plugin to `--target cursor`.
   - Validate env var syntax uses `${env:VAR}` in `.cursor/mcp.json`.

5. **Binary files**
   - Include a binary asset in a skill directory.
   - Verify emitted binary file exists and bytes match.

6. **Report output**
   - Use `--report` output file and confirm it is written.

## Validation Steps
- `uv run ruff check src/`
- `uv run ty check src/`
- `uv run pytest tests/unit/ -v`
- Manual tmux-driven validation (local) covering conversion outputs
- `python tests/docker/test_in_docker.py --claude-only`
- `python tests/docker/test_in_docker.py` (all-tools, if available)

## Rollout
- Ensure `CHANGELOG.md` updated.
- Re-run `ai-config convert` on sample plugin to verify outputs.
- Confirm `ai-config doctor --target all` on converted output.
