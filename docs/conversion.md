# Conversion

Convert Claude Code plugins to work with other AI coding tools.

## Overview

The `convert` command takes a Claude Code plugin directory and produces equivalent configuration for other tools. Supported targets:

| Target | Tool | Output |
|--------|------|--------|
| `codex` | OpenAI Codex | `.codex/` dir with TOML config + skills |
| `cursor` | Cursor | `.cursor/` dir with rules + MCP config |
| `opencode` | OpenCode | `opencode.json` + `.opencode/` skills dir |
| `pi` | Pi | `.pi/` dir with skills + prompt templates |

Each target gets the closest equivalent of your plugin's skills, commands, hooks, MCP servers, and LSP servers — with diagnostics when something can't convert cleanly.

## Quick Start

Convert a plugin to all targets:

```bash
ai-config convert ./my-plugin
```

Convert to a specific target:

```bash
ai-config convert ./my-plugin --target codex
```

Preview without writing files:

```bash
ai-config convert ./my-plugin --dry-run
```

## Sync-Driven Conversion

Instead of running `convert` manually, you can configure automatic conversion in your config file. Every time `ai-config sync` runs, it converts all synced plugins to the specified targets.

```yaml
version: 1
targets:
  - type: claude
    config:
      marketplaces:
        my-plugins:
          source: github
          repo: myorg/my-plugins

      plugins:
        - id: my-tool@my-plugins
          scope: user
          enabled: true

      conversion:
        enabled: true
        targets:
          - codex
          - cursor
        scope: project
```

With this config, `ai-config sync` installs your Claude plugins and then converts them to Codex and Cursor format.

### Conversion Config Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Enable/disable conversion |
| `targets` | list | *(required)* | Target tools: `codex`, `cursor`, `opencode`, `pi` |
| `scope` | string | `"project"` | `"user"` (home dir) or `"project"` (cwd) |
| `output_dir` | string | *(auto)* | Custom output directory. Relative paths resolve from config file location |
| `commands_as_skills` | bool | `false` | Convert commands to skills instead of prompts (Codex-specific) |

## Component Mapping

How each plugin component maps to target tools:

| Component | Codex | Cursor | OpenCode | Pi |
|-----------|-------|--------|----------|----|
| Skills | `.codex/skills/*.md` | `.cursor/rules/*.mdc` | `.opencode/skills/*.md` | `.pi/skills/*/SKILL.md` |
| Commands | Prompts or skills | Commands | Prompts | Prompt templates |
| Hooks | Unsupported | Hooks config | Unsupported | Unsupported |
| MCP servers | `.codex/config.toml` | `.cursor/mcp.json` | `opencode.json` | Unsupported |
| LSP servers | Unsupported | Unsupported | `opencode.lsp.json` | Unsupported |
| Agents | Unsupported | Unsupported | Unsupported | Unsupported |

**Mapping fidelity levels:**

- **Native** — direct 1:1 equivalent exists
- **Transform** — config/schema conversion required
- **Emulate** — wrapped via a fallback mechanism
- **Fallback** — degraded to prompt or plain text
- **Unsupported** — no equivalent in the target

## Options Reference

```
ai-config convert PLUGIN_PATH [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-t, --target TARGET` | Target tool(s): `codex`, `cursor`, `opencode`, `pi`, `all` (default: `all`) |
| `-o, --output DIR` | Output directory (default: based on `--scope`) |
| `--scope SCOPE` | `user` or `project` — controls default output path |
| `--dry-run` | Preview changes without writing files |
| `--best-effort` | Continue even if some components fail to convert |
| `--format FORMAT` | Console output: `summary` (default), `markdown`, `json` |
| `--report PATH` | Write conversion report to a file |
| `--report-format FORMAT` | Report file format: `json` (default) or `markdown` |
| `--commands-as-skills` | Convert commands to skills instead of prompts (Codex) |

Multiple targets can be specified:

```bash
ai-config convert ./my-plugin -t codex -t cursor
```

## Validating Output

After conversion, use `doctor` to validate the output:

```bash
ai-config doctor --target codex ./output-dir
ai-config doctor --target all ./output-dir
```

This checks that the converted files have valid structure, required fields, and correct naming conventions for each target tool.

## Conversion Cache

Sync-driven conversion uses content hashing to skip re-conversion when plugin sources haven't changed.

`--force` does a full rebuild (clears plugin cache + re-converts everything):

```bash
ai-config sync --force
```

`--force-convert` re-converts without clearing the plugin cache (useful after adding a new target or updating the converter):

```bash
ai-config sync --force-convert
```

## Examples

### Convert a local plugin to Codex

```bash
ai-config convert ./my-plugin --target codex --scope project
```

Creates `.codex/` in the current directory with skills and MCP config.

### Convert to all targets with a report

```bash
ai-config convert ./my-plugin --report ./report.json
```

Converts to all targets and writes a JSON report with component mappings and diagnostics.

### Dry run with detailed output

```bash
ai-config convert ./my-plugin --dry-run --format markdown
```

Shows what would be created in Markdown format without writing any files.
