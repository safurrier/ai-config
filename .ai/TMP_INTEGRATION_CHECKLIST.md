# TMP: Manual Integration Checks (DO NOT MERGE)

This file is temporary and should not be merged.

- Preflight
- Confirm Docker is running (for container-based checks)
- `uv sync --all-extras`
- `uv run ai-config --version`
- `uv run ai-config status`

- Convert sample plugin to each target
- `uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t codex -o /tmp/convert-codex`
- `uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t cursor -o /tmp/convert-cursor`
- `uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t opencode -o /tmp/convert-opencode`

- File output verification
- Codex: `.codex/skills/*/SKILL.md` exists
- Codex: `.codex/prompts/<plugin-command>.md` exists (user scope)
- Codex: `.codex/mcp-config.toml` exists
- Cursor: `.cursor/skills/*/SKILL.md` exists
- Cursor: `.cursor/mcp.json` has `${env:VAR}` syntax
- Cursor: `.cursor/hooks.json` exists (if hooks present)
- OpenCode: `.opencode/skills/*/SKILL.md` exists
- OpenCode: `opencode.json` has `{env:VAR}` syntax
- OpenCode: `opencode.lsp.json` contains all servers

- Interactive TUI checks (tmux)
- Claude: start `claude`, dismiss prompts, run `/skills`, confirm skills listed
- Codex: start `codex`, confirm no errors about skills directory
- OpenCode: `opencode debug skill`, confirm converted skills listed
- Cursor: `cursor-agent mcp list`, confirm MCP servers listed

- Sync-driven conversion
- Add conversion section to `.ai-config/config.yaml`
- `uv run ai-config sync`
- Confirm outputs land at correct scope (user vs project)

- Edge cases
- Non-kebab plugin/skill names normalize (output names match normalized forms)
- Multi-LSP aggregation preserved (no overwrite)
- Binary skill assets emit correctly (byte-for-byte match)

- Evidence capture
- Save tmux scrollback for each tool
- Save `ai-config convert --report` output
