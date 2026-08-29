# Manual validation

Use this guide to validate ai-config with real AI coding tools. These checks need an interactive terminal interface or API keys, so automated tests cannot run them.

## Prerequisites

```bash
# Start Docker dev container
just docker-dev-up && just docker-dev-attach

# Inside container: install dependencies
uv sync --all-extras

# Run the automated smoke test first
uv run pytest tests/e2e/test_integration_smoke.py -v
```

Fix smoke-test failures before manual validation.

## Claude Code

**Required environment variable:** `ANTHROPIC_API_KEY`

```bash
export ANTHROPIC_API_KEY=sk-...

# Start Claude Code
claude

# Inside Claude session:
/skills          # Lists test-plugin skills, including test-skill
# Ctrl+C to exit
```

Expected result: `test-skill` appears with the description `A test skill for marketplace validation`.

## OpenAI Codex

**Required environment variable:** `OPENAI_API_KEY`

```bash
export OPENAI_API_KEY=sk-...

# Start Codex
codex

# List registered plugins
codex plugin list --json
```

Expected result: Codex starts without errors. The plugin list includes the converted plugin after sync registers its generated marketplace.

## OpenCode

No API key is required for these debug commands.

```bash
opencode debug skill    # Lists converted skills
opencode debug config   # Shows MCP configuration
opencode debug paths    # Shows paths
```

Expected result: The commands show converted skills, MCP servers, and the expected paths.

## Cursor

No API key is required for this command.

```bash
cursor-agent mcp list   # Lists MCP servers from conversion
```

Expected result: The converted plugin's MCP servers appear in the list.

## Sync-driven conversion

After the smoke test runs `ai-config sync`, inspect the generated output:

```bash
# User scope output
ls ~/.ai-config/codex/marketplaces/  # Generated Codex package sources
ls ~/.cursor/skills/                 # Cursor skills
ls ~/.opencode/skills/               # OpenCode skills

# MCP configuration files
cat ~/.cursor/mcp.json    # Uses ${env:VAR} syntax for environment variables
cat ~/opencode.json       # Uses {env:VAR} syntax for environment variables
cat ~/opencode.lsp.json   # OpenCode LSP configuration

# Codex lifecycle state
codex plugin list --json
```

## Plugin marketplace

```bash
# Registered Claude marketplaces
claude plugin marketplace list --json

# Installed Claude plugins
claude plugin list --json
```

Expected output includes `test-marketplace` in the marketplace list and `test-plugin` in the plugin list.

## Troubleshooting

**`ai-config sync` reports a source error:** The marketplace fixture `source` field must be a string path such as `"./test-plugin"`, not an object. Verify the fixture with `uv run pytest tests/unit/test_marketplace_fixtures.py -v`.

**Claude plugin commands fail:** Check the installation with `claude --version`. Also check that `~/.claude/plugins/` exists.

**Skills do not appear:** Restart Claude Code after `ai-config sync`. Claude Code loads plugins when a session starts. Use `claude --resume` to continue the prior session.
