# Validation Matrix


## Contents

- [Universal checks](#universal-checks)
- [Claude source plugin behavior](#claude-source-plugin-behavior)
- [Codex skills](#codex-skills)
- [Codex MCP](#codex-mcp)
- [Codex hooks](#codex-hooks)
- [Pi skills and prompts](#pi-skills-and-prompts)
- [Pi hooks](#pi-hooks)
- [Cursor](#cursor)
- [OpenCode](#opencode)
- [Config-write safety checks](#config-write-safety-checks)

Map every changed target surface to unit, validator, docs, and real-tool checks.

## Universal checks

Run while iterating:

```bash
uv run ruff check src/ tests/ && uv run ty check src/
uv run pytest tests/unit/converters/test_conversion.py -q
uv run pytest tests/unit/validators/test_target_validators.py -q
```

Before handoff:

```bash
uv run ruff check src/ && uv run ruff format --check src/ && uv run ty check src/ && uv run pytest tests/ --cov=src/ai_config --cov-report=term-missing --cov-report=xml
uv run mkdocs build --strict
```

For runtime changes:

```bash
uv run python tests/docker/test_in_docker.py
```

Record validation evidence through HK with rationale that ties the command to the changed surface:

```bash
hk validate --kind test --why 'Focused converter coverage for <target>/<surface>' -- uv run pytest <focused-test> -q
hk validate --kind check --why 'Static/type/docs gate before handoff' -- sh -c 'uv run ruff check src/ tests/ && uv run ty check src/ && uv run mkdocs build --strict'
hk validate --kind e2e --why 'Real <tool> runtime proves <surface> loads beyond generated file shape' -- <real-tool-probe>
hk dangerously-skip validation --label docker-all-tools-e2e --reason '<local blocker>' --mitigation '<CI or alternate probe that will cover it>'
hk review add --backend <subagent-or-tool> --reviewer target-runtime-assumption --rubric stale-runtime-assumptions --summary '<finding/disposition>'
hk ready --target . && hk summary --target .
```

For audit/plan-only work, do not run implementation validations unless requested; list these HK commands as planned evidence and state that no files were changed.

## Claude source plugin behavior

Use when parser, sync, marketplace, or Claude plugin assumptions change.

- Unit: `tests/unit/test_adapters_claude.py`
- Unit: `tests/unit/test_operations.py`
- Parser: `tests/unit/converters/test_conversion.py::TestClaudeParser`
- E2E: `tests/e2e/test_fresh_install.py`
- E2E: `claude plugin validate tests/fixtures/test-marketplace/test-plugin`
- Docs: `README.md`, `docs/config.md`, `docs/conversion.md`

## Codex skills

Use when Agent Skills paths, command-as-skill behavior, or prompt construction changes.

- Unit: `tests/unit/converters/test_conversion.py::TestCodexEmitter`
- Validator: `tests/unit/validators/test_target_validators.py::TestCodexValidator`
- Doctor: `tests/unit/test_cli_doctor_target.py::TestDoctorCodexTarget`
- E2E file shape: `tests/e2e/test_conversion.py::TestCodexConversion`
- Real tool: `codex -C <generated> debug prompt-input "test" | grep <skill>`
- Expected paths:
  - project: `.agents/skills/<plugin>-<skill>/SKILL.md`
  - user: `~/.agents/skills/<plugin>-<skill>/SKILL.md`

## Codex MCP

Use when MCP output, TOML writing, or config merging changes.

- Unit: config generation and merge tests in `TestCodexEmitter`
- Regression: quoted keys such as `[mcp_servers."github.com"]` remain quoted
- Validator: parse `.codex/config.toml`
- Real tool: `CODEX_HOME=<generated>/.codex codex mcp list`
- Safety: preserve existing scalar settings, profiles, MCP servers, and quoted/dotted keys
- Docs: explain project `.codex/config.toml` may need `CODEX_HOME` or manual merge depending runtime trust/loading

## Codex hooks

Use when hook mapping or command placeholder handling changes.

- Unit: hook conversion and diagnostics in `TestCodexEmitter`
- Validator: `.codex/hooks.json` and `[features].codex_hooks = true`
- Safety: no literal `${CLAUDE_PLUGIN_ROOT}` leakage
- Merge: preserve existing hooks and avoid duplicate generated hooks
- Real tool: add execution probe when an auth-free trigger exists

## Pi skills and prompts

Use when Pi output paths, prompt templates, or Agent Skills formatting changes.

- Unit: `tests/unit/converters/test_conversion.py::TestPiEmitter`
- Validator: `tests/unit/validators/test_target_validators.py::TestPiValidator`
- E2E file shape: `tests/e2e/test_conversion.py::TestDoctorTargetValidation::test_convert_pi_skills`
- Real tool project scope: Pi RPC `get_commands` includes `skill:<generated-skill>` from `.pi/skills/`
- Real tool user scope: Pi RPC `get_commands` includes `skill:<generated-skill>` from `.pi/agent/skills/` with `PI_CODING_AGENT_DIR`
- Expected paths:
  - project: `.pi/skills/`, `.pi/prompts/`
  - user: `.pi/agent/skills/`, `.pi/agent/prompts/`

## Pi hooks

Use when Claude hooks are emulated as Pi extensions.

- Unit: `TestPiEmitter::test_emit_hooks_as_extension`
- Unit: user-scope extension output test
- Validator: generated `.ts` extension exists and includes expected `pi.on(...)` events
- Safety: no literal `${CLAUDE_PLUGIN_ROOT}` leakage
- Real tool: load generated extension with `pi --extension` and assert marker file from `session_start`
- Expected paths:
  - project: `.pi/extensions/<plugin>-hooks.ts`
  - user: `.pi/agent/extensions/<plugin>-hooks.ts`

## Cursor

Use when Cursor output paths, MCP, hooks, or skills change.

- Unit: `TestCursorEmitter`
- Validator: `TestCursorValidator`
- E2E: JSON validity for `.cursor/mcp.json` and `.cursor/hooks.json`
- Real tool: `cursor-agent mcp list` when available
- Gap: auth-free skill listing may not be available; document any remaining file-shape-only coverage

## OpenCode

Use when OpenCode output paths, config, MCP, LSP, or skills change.

- Unit: `TestOpenCodeEmitter`
- Validator: `TestOpenCodeValidator`
- E2E: `opencode debug skill`, `opencode debug config`, `opencode mcp list`
- Expected paths depend on OpenCode's current config behavior; verify with runtime before changing.

## Config-write safety checks

Use when writing shared config files such as `.codex/config.toml`, `.codex/hooks.json`, `.cursor/mcp.json`, or `opencode.json`.

Check:

- existing unrelated settings preserved,
- existing target sections preserved,
- generated entries are idempotent,
- quoted/special keys survive parse/dump round trip,
- placeholders such as `${CLAUDE_PLUGIN_ROOT}` are resolved or diagnosed,
- conversion errors fail visibly rather than reporting no changes.
