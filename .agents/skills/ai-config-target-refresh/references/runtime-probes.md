# Runtime Probes


## Contents

- [Claude Code](#claude-code)
- [Codex](#codex)
- [Pi](#pi)
- [OpenCode](#opencode)
- [Cursor](#cursor)
- [Dogfood rollout](#dogfood-rollout)

Use these probes to prove target-tool discovery and config loading. Prefer temp dirs and auth-free introspection. Probe commands are version-specific candidates, not permanent truth: before relying on a probe, confirm the installed CLI exposes it (`<tool> <subcommand> --help`, `debug --help`, or equivalent). If a probe is missing or renamed, record the command, version, and failure, then classify coverage as an E2E/probe gap instead of treating generated file shape as runtime proof.

## Claude Code

Version and basic plugin surfaces:

```bash
claude --version
claude plugin list --json
claude plugin marketplace list --json
claude mcp list 2>&1
```

Validate a plugin fixture without installing it:

```bash
claude plugin validate tests/fixtures/test-marketplace/test-plugin
```

Sync smoke after writing a local ai-config config:

```bash
uv run ai-config sync
claude plugin marketplace list --json
claude plugin list --json
```

Interactive `/skills` validation requires auth. Keep it optional or marked `requires_api_key`.

## Codex

Version:

```bash
codex --version
```

Project-scope Agent Skills discovery:

```bash
tmp=$(mktemp -d)
uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t codex -o "$tmp"
codex -C "$tmp" debug prompt-input "test" | grep -q dev-tools-code-review
```

MCP config loading through isolated `CODEX_HOME`:

```bash
tmp=$(mktemp -d)
uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t codex -o "$tmp"
CODEX_HOME="$tmp/.codex" codex mcp list | grep -q dev-tools-database
```

Config TOML parse check:

```bash
python3 -c "import tomllib; tomllib.load(open('$tmp/.codex/config.toml', 'rb'))"
```

Hook behavior may require feature flags and runtime support. At minimum, validate generated `.codex/hooks.json` and `[features].codex_hooks = true`, then add real hook execution once an auth-free hook trigger is available.

## Pi

Version:

```bash
pi --version
```

Project-scope skill discovery through RPC command registry:

```bash
tmp=$(mktemp -d)
agent_dir=$(mktemp -d)
uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t pi -o "$tmp"
cd "$tmp"
printf '%s\n' '{"id":"skills","type":"get_commands"}' |
  PI_OFFLINE=1 PI_CODING_AGENT_DIR="$agent_dir" \
  pi --offline --mode rpc --no-session --no-extensions \
    --provider openai --model gpt-4o-mini --api-key fake |
  grep -q 'skill:dev-tools-code-review'
```

User-scope skill discovery through `PI_CODING_AGENT_DIR`:

```bash
tmp=$(mktemp -d)
uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t pi --scope user -o "$tmp"
printf '%s\n' '{"id":"skills","type":"get_commands"}' |
  PI_OFFLINE=1 PI_CODING_AGENT_DIR="$tmp/.pi/agent" \
  pi --offline --mode rpc --no-session --no-extensions \
    --provider openai --model gpt-4o-mini --api-key fake |
  grep -q 'skill:dev-tools-code-review'
```

Generated hook extension execution:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/plugin/.claude-plugin" "$tmp/plugin/hooks"
printf %s '{"name":"marker-plugin","hooks":"hooks/hooks.json"}' > "$tmp/plugin/.claude-plugin/plugin.json"
printf %s '{"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"sh -c '\''echo ran > '$tmp'/marker'\''"}]}]}}' > "$tmp/plugin/hooks/hooks.json"
uv run ai-config convert "$tmp/plugin" -t pi -o "$tmp/out"
PI_OFFLINE=1 pi --offline \
  --extension "$tmp/out/.pi/extensions/marker-plugin-hooks.ts" \
  --provider openai --model gpt-4o-mini --api-key fake -p test || true
test -f "$tmp/marker"
```

## OpenCode

Version and skill discovery:

```bash
opencode --version
opencode debug --help
opencode debug skill --help
uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t opencode -o /tmp/opencode-test
opencode debug skill
opencode debug config
opencode debug paths
opencode mcp list 2>&1
```

If `opencode debug skill` is absent or renamed in the checked version, fall back only to documented/current OpenCode introspection commands and record the skill-discovery check as an E2E/probe gap until a real replacement is added.

## Cursor

Version and MCP:

```bash
cursor-agent --version || cursor --version
uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t cursor -o /tmp/cursor-test
cursor-agent mcp list 2>&1
python3 -c "import json; json.load(open('/tmp/cursor-test/.cursor/mcp.json'))"
```

Cursor skill discovery may not have a stable auth-free CLI listing. Validate generated file shape and any available CLI surface, then document the gap.

## Dogfood rollout

After a merge-candidate change:

```bash
uv tool install --reinstall .
cd ~/git_repositories/dots
mise run ai-config:sync
```

Then verify key runtime files:

```bash
test -f ~/.agents/skills/alex-ai-github-open-pr/SKILL.md
test -f ~/.pi/agent/skills/alex-ai-github-open-pr/SKILL.md
test -f ~/.pi/agent/extensions/alex-ai-hooks.ts
codex debug prompt-input "test" | grep -q alex-ai-github-open-pr
! grep -R "CLAUDE_PLUGIN_ROOT" ~/.pi/agent/extensions ~/.codex/hooks.json 2>/dev/null
```
