# ai-config

ai-config manages Claude Code plugins from declarative YAML. It can also convert plugins for Codex, Cursor, OpenCode, and Pi.

## Why use it

AI coding setups often include skills, MCP servers, hooks, and workflows. Moving to another tool or machine can mean rebuilding that setup. ai-config keeps the setup in one YAML file.

- **Reproducible setup:** Define plugins once, then run `ai-config sync`. The same configuration works on each machine.
- **Cross-tool conversion:** Convert customizations for Codex, Cursor, OpenCode, and Pi.
- **Version control:** Store `.ai-config/config.yaml` in Git and share it with a team.

Run `ai-config init` to create the file.

## Installation

```bash
uv tool install git+https://github.com/safurrier/ai-config
```

This installs `ai-config` globally. Verify the installation with `ai-config --help`.

### Development setup

```bash
git clone https://github.com/safurrier/ai-config.git
cd ai-config
just setup    # Install dependencies
just check    # Run lint, type check, tests
```

## Quick start

### Create a configuration

```bash
ai-config init
```

The interactive wizard adds marketplaces and plugins. It creates `.ai-config/config.yaml`.

### Sync plugins

```bash
ai-config sync
```

This installs and removes plugins to match the configuration. Run it after editing `config.yaml`.

### Convert a plugin

```bash
ai-config convert ./my-plugin --target codex
```

This optional command converts a Claude Code plugin for Codex, Cursor, OpenCode, or Pi. The `conversion` configuration section can also convert plugins during sync.

### Check status

```bash
ai-config status
```

This shows installed plugins and the configured state.

## The model

Define a setup once. `ai-config sync` installs Claude plugins and generates matching output for other tools:

```text
ai-config sync
  → Claude Code: plugins installed
  → Codex:       ~/.ai-config/codex/ packages, installed via codex plugin CLI
  → Cursor:      ~/.cursor/skills/, ~/.cursor/mcp.json, ~/.cursor/hooks.json
  → OpenCode:    ~/.opencode/skills/, ~/opencode.json
  → Pi:          ~/.pi/agent/skills/, ~/.pi/agent/prompts/, ~/.pi/agent/extensions/
```

Store `.ai-config/config.yaml` in dotfiles. Run `ai-config sync` on each machine. To use another tool, add it to `conversion.targets` and sync again.

## Next steps

- [Commands](commands.md): Command reference.
- [Configuration](config.md): Configuration format and examples.
- [Conversion](conversion.md): Plugin conversion details.
