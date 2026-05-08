# PR #12 Case Study: Codex and Pi Target Refresh


## Contents

- [Problem pattern](#problem-pattern)
- [Key corrections](#key-corrections)
- [Review lessons](#review-lessons)
- [Durable validation pattern](#durable-validation-pattern)

This case study captures concrete lessons from the cross-tool capability refresh PR.

## Problem pattern

ai-config's target support matrix had drifted from current AI CLI behavior:

- Codex skills were emitted to stale `.codex/skills` paths.
- Codex MCP was emitted as a separate `.codex/mcp-config.toml`, but current Codex uses `[mcp_servers.*]` in `config.toml`.
- Codex hooks were marked unsupported, but Codex supports hooks behind `codex_hooks`.
- Pi hooks were marked unsupported, but Pi extensions can emulate lifecycle/tool hooks.
- Tests validated generated files more than real tool discovery.

## Key corrections

### Codex skills

Current Codex discovers Agent Skills from `.agents/skills` and user/global Agent Skills paths. The converter now emits:

- project: `.agents/skills/<plugin>-<skill>/SKILL.md`
- user: `$HOME/.agents/skills/<plugin>-<skill>/SKILL.md`

Validation:

```bash
codex -C <generated-project> debug prompt-input "test" | grep <generated-skill>
```

### Codex MCP

Codex MCP belongs in `.codex/config.toml`:

```toml
[mcp_servers.<name>]
command = "..."
args = [...]
```

Validation:

```bash
CODEX_HOME=<generated>/.codex codex mcp list
```

### Codex config merge safety

Shared Codex files must merge, not clobber. Preserve:

- unrelated top-level config,
- existing `[profiles]` scalar/subtable mixes,
- existing MCP servers,
- existing hooks,
- quoted table keys such as `[mcp_servers."github.com"]`.

Regression: TOML table/key serialization must quote keys that are not valid bare keys. Otherwise `[mcp_servers."github.com"]` can become `[mcp_servers.github.com]`, changing the parsed structure.

### Codex hooks

Supported Claude command hooks can map to `.codex/hooks.json` and require:

```toml
[features]
codex_hooks = true
```

Resolve `${CLAUDE_PLUGIN_ROOT}` in generated commands. Do not leave Claude-only placeholders in Codex output.

### Pi skills

Pi skill locations did not need the same Codex-style switch. Pi supports:

- project: `.pi/skills/`
- user: `.pi/agent/skills/`
- also generic Agent Skills paths, but the Pi target emits Pi-native paths.

Validation:

```bash
PI_CODING_AGENT_DIR=<isolated-agent-dir> pi --mode rpc ...
# Send: {"id":"skills","type":"get_commands"}
# Assert: skill:<generated-skill> appears
```

### Pi hooks

Pi hooks are emulated with generated TypeScript extensions:

- project: `.pi/extensions/<plugin>-hooks.ts`
- user: `.pi/agent/extensions/<plugin>-hooks.ts`

Validation:

```bash
pi --extension <generated-extension> ...
# Assert a marker file is written by a session_start hook
```

### Docker and dangerous skips

Local Docker/Colima may be unavailable. When full local all-tools E2E cannot run:

1. record an explicit dangerous validation skip,
2. run non-Docker CI parity and focused local real-tool probes where possible,
3. ensure GitHub E2E runs and passes before merge.

## Review lessons

Fresh-context review caught real blockers:

- generated Pi hooks leaked `${CLAUDE_PLUGIN_ROOT}` and failed before useful work,
- Codex shared config was initially clobbered rather than merged.

Codex/Bugbot feedback caught a second concrete issue:

- TOML quoting in config merges changed dotted server names.

Only respond publicly to AI PR feedback after making code changes tied to concrete actionable findings.

## Durable validation pattern

For target refresh work, use this ladder:

1. focused converter/validator unit tests,
2. static checks,
3. docs build,
4. auth-free real-tool probes,
5. Docker all-tools E2E,
6. dogfood against Alex's dots sync,
7. fresh-context target-runtime review,
8. HK ready/handoff.
