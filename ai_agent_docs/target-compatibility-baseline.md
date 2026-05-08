# Target Compatibility Baseline

This file records the target-runtime assumptions that ai-config's converter support matrix is based on. Update it when target CLI behavior changes or when refreshing conversion support.

Last checked: 2026-05-08
Context: PR #12 cross-tool capability refresh

## Summary

| Target | Observed support | ai-config output | Runtime validation |
|---|---|---|---|
| Claude Code | Native plugin marketplace, skills, hooks, MCP | Source tool, not emitted by converter | `claude plugin validate`, `claude plugin list --json`, `claude mcp list` |
| Codex | Agent Skills, MCP in `config.toml`, hooks behind `codex_hooks` | `.agents/skills/`, `.codex/config.toml`, `.codex/hooks.json`, prompts | `codex debug prompt-input`, `CODEX_HOME=<generated> codex mcp list` |
| Cursor | Skills, MCP JSON, hooks JSON | `.cursor/skills/`, `.cursor/mcp.json`, `.cursor/hooks.json` | JSON validation, `cursor-agent mcp list` when available |
| OpenCode | Skills, MCP/config, LSP/config debug surfaces | `.opencode/skills/`, `opencode.json`, `opencode.lsp.json` | `opencode debug skill`, `opencode debug config`, `opencode mcp list` |
| Pi | Skills, prompt templates, TypeScript extensions | `.pi/skills/`, `.pi/prompts/`, `.pi/extensions/`; user-scope under `.pi/agent/` | RPC `get_commands`, `pi --extension` marker hook |

## Version capture commands

Run these during each target refresh and paste observed outputs below or into the PR notes:

```bash
claude --version
codex --version
pi --version
cursor-agent --version || cursor --version
opencode --version
```

## Current assumptions

### Claude Code

- Claude plugin support is the source format for ai-config.
- Sync behavior installs local/GitHub plugin marketplaces and plugins through Claude CLI commands.
- Use valid marketplace fixtures for `claude plugin validate`; the broad `complete-plugin` fixture may intentionally include fields that are useful for parser coverage but invalid for current Claude validation.

Validation patterns:

```bash
claude plugin validate tests/fixtures/test-marketplace/test-plugin
claude plugin marketplace list --json
claude plugin list --json
claude mcp list 2>&1
```

### Codex

- Agent Skills are discovered from `.agents/skills` for project output and `$HOME/.agents/skills` for user output.
- MCP servers are configured in `.codex/config.toml` under `[mcp_servers.*]`.
- Supported command hooks can be emitted to `.codex/hooks.json` with `[features].codex_hooks = true`.
- Shared Codex files must be merged, not clobbered.
- TOML keys that are not valid bare keys must remain quoted, e.g. `[mcp_servers."github.com"]`.

Validation patterns:

```bash
codex -C <generated-project> debug prompt-input "test" | grep <generated-skill>
CODEX_HOME=<generated>/.codex codex mcp list
```

### Pi

- Pi-native skills use `.pi/skills/` for project scope and `.pi/agent/skills/` for user-scope output roots.
- Pi-native prompt templates use `.pi/prompts/` and `.pi/agent/prompts/`.
- Claude hooks are emulated via generated TypeScript extensions under `.pi/extensions/` or `.pi/agent/extensions/`.
- Pi RPC `get_commands` is the deterministic auth-free check for skill command registration.
- `pi --extension <generated.ts>` can validate extension loading and early hook execution without successful model completion.

Validation patterns:

```bash
PI_CODING_AGENT_DIR=<tmp-agent> pi --mode rpc --offline --no-session --no-extensions ...
# send {"id":"skills","type":"get_commands"}; assert skill:<name>

PI_OFFLINE=1 pi --offline --extension <generated-extension> ... || true
# assert marker file from hook command
```

### Cursor

- Cursor output currently includes `.cursor/skills/`, `.cursor/mcp.json`, and `.cursor/hooks.json`.
- `cursor-agent mcp list` is the available real-tool MCP check.
- Auth-free CLI skill listing may not be stable; keep file-shape validation and update this baseline if a better introspection command appears.

### OpenCode

- OpenCode exposes useful debug surfaces: `opencode debug skill`, `opencode debug config`, and `opencode debug paths`.
- Use these before relying on generated file shape alone.

## Update checklist

When this baseline is refreshed:

1. Update `Last checked`.
2. Record version command outputs.
3. Update each target's assumptions.
4. Link or mention upstream docs/release notes consulted.
5. Add/adjust E2E tests for any changed runtime behavior.
6. Run the `ai-config-target-refresh` skill workflow.
