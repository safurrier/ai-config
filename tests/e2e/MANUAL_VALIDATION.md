# Manual Validation Guide

Step-by-step guide for validating ai-config integration with real AI coding tools. These checks require interactive TUI access or API keys that can't be automated.

## Prerequisites

```bash
# Start Docker dev container
just docker-dev-up && just docker-dev-attach

# Inside container: install dependencies
uv sync --all-extras

# Run the automated smoke test first (covers non-interactive checks)
uv run pytest tests/e2e/test_integration_smoke.py -v
```

If the smoke test fails, fix those issues before proceeding with manual validation.

## 1. Claude Code

**Requires**: `ANTHROPIC_API_KEY`

```bash
export ANTHROPIC_API_KEY=sk-...

# Start Claude Code
claude

# Inside Claude session:
/skills          # Should list test-plugin skills (test-skill)
# Ctrl+C to exit
```

**Expected**: `test-skill` appears in the skills list with description "A test skill for marketplace validation".

## 2. OpenAI Codex

**Requires**: `OPENAI_API_KEY`

```bash
export OPENAI_API_KEY=sk-...

# Start Codex - should start without skill directory errors
codex

# Verify skills directory exists
ls ~/.codex/skills/
```

**Expected**: Codex starts without errors. Skills directory contains converted skill files.

## 3. OpenCode

**No API key needed** for debug commands.

```bash
opencode debug skill    # Should list converted skills
opencode debug config   # Should show MCP config
opencode debug paths    # Should show correct paths
```

**Expected**: Debug commands show converted skills, MCP servers, and correct path configuration.

## 4. Cursor

**No API key needed** for CLI commands.

```bash
cursor-agent mcp list   # Should list MCP servers from conversion
```

**Expected**: MCP servers from the converted plugin appear in the list.

## 5. Sync-Driven Conversion

After the automated smoke test runs `ai-config sync`, verify the cross-tool outputs:

```bash
# User scope outputs
ls ~/.codex/skills/       # Codex skills
ls ~/.cursor/skills/      # Cursor skills
ls ~/.opencode/skills/    # OpenCode skills

# MCP config files
cat ~/.cursor/mcp.json    # Should use ${env:VAR} syntax for env vars
cat ~/opencode.json       # Should use {env:VAR} syntax for env vars
cat ~/opencode.lsp.json   # OpenCode LSP config
```

## 6. Plugin Marketplace Verification

```bash
# Verify marketplace is registered
claude plugin marketplace list --json

# Verify plugin is installed
claude plugin list --json

# Expected output should include:
#   - "test-marketplace" in marketplace list
#   - "test-plugin" in plugin list
```

## Troubleshooting

**`ai-config sync` fails with source error**: The marketplace fixture `source` field must be a string path (`"./test-plugin"`), not an object. Run the unit tests to verify: `uv run pytest tests/unit/test_marketplace_fixtures.py -v`

**Claude plugin commands fail**: Ensure Claude Code is installed (`claude --version`) and the plugin directory exists (`ls ~/.claude/plugins/`).

**Skills not showing up**: After `ai-config sync`, restart Claude Code. Plugins are loaded at session start. Use `claude --resume` to continue your previous session.
