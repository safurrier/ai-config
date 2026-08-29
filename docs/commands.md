# Commands

This page lists ai-config commands. Use it before changing plugin state. Start with `--dry-run` when a command supports it. Read the reported actions. Check the paths. Check the scope. Then apply the change.

## Overview

| Command | Purpose |
|---------|---------|
| `init` | Create configuration interactively. |
| `sync` | Make installed plugins match configuration. |
| `status` | Show installed state. |
| `watch` | Sync after file changes. |
| `update` | Update plugins. |
| `doctor` | Validate setup and show fixes. |
| `convert` | Convert plugins for other AI tools. |
| `plugin create` | Create a plugin skeleton. |
| `cache clear` | Clear the plugin cache. |

## Global options

```bash
ai-config [OPTIONS] COMMAND

Options:
  -c, --config PATH  Path to config file
  --version          Show version
  --help             Show help message
```

## `init`

Create or update a configuration file interactively.

```bash
ai-config init
```

| Option | Description |
|--------|-------------|
| `-o, --output PATH` | Configuration file path. |
| `--non-interactive` | Create a minimal configuration without prompts. |

The wizard adds GitHub or local marketplaces, selects their plugins, and chooses user or project scope. It creates `.ai-config/config.yaml` in the current directory unless `-o` provides another path.

## `sync`

Make installed plugins match configuration.

```bash
ai-config sync
```

| Option | Description |
|--------|-------------|
| `-c, --config PATH` | Configuration file path. |
| `--dry-run` | Show changes without writing them. |
| `--fresh`, `--force` | Clear Claude's plugin cache and reconvert configured outputs. Target homes and ownership ledgers remain. |
| `--force-convert` | Reconvert without clearing the plugin cache. |
| `--verify` | Verify sync state after completion. |
| `--json` | Write planned, completed, and failed actions with reasons as JSON. |

Sync installs configured plugins. It removes unconfigured plugins. It updates plugin configuration. It runs configured conversion. See [Conversion](conversion.md).

Codex conversion reports register, install, update, reinstall or repair, remove, and no-op actions with reasons. JSON separates `planned_actions`, `completed_actions`, and `failed_actions`. Sync exits non-zero if a target fails or lifecycle verification finds drift. Terminal output prints `No changes needed` only after a clean result.

## `status`

Show marketplace and plugin state.

```bash
ai-config status
```

| Option | Description |
|--------|-------------|
| `-c, --config PATH` | Configuration file path. It also calculates lifecycle drift. |
| `--verify` | Verify that current state matches configuration. |
| `--json` | Write planned lifecycle actions and reasons as JSON. |

Status shows configured marketplaces, configured plugins, extra plugins, and sync issues. With `--config` or `--verify`, it uses the sync lifecycle planner. It exits non-zero for a non-no-op action or inspection error. It plans before it reports a clean state. It prints `No lifecycle actions needed` or `All in sync` only after clean inspection and planning. Claude-only state cannot justify those messages while Codex package drift remains.

## `watch`

Sync when configuration or plugin files change.

```bash
ai-config watch
```

| Option | Description |
|--------|-------------|
| `-c, --config PATH` | Configuration file path. |
| `--debounce SECONDS` | Delay before sync. Default: `1.5`. |
| `--dry-run` | Show changes without syncing. |
| `-v, --verbose` | Show file events. |

Watch monitors `.ai-config/config.yaml` and plugin directories. Press Ctrl+C to stop.

!!! warning "Claude Code reload required"

    Claude Code loads plugins when a session starts. Restart it after `watch` syncs changes.

    To continue the prior session:

    ```bash
    claude --resume
    ```

## `update`

Update plugins.

```bash
ai-config update --all
ai-config update PLUGIN1 PLUGIN2
```

| Option | Description |
|--------|-------------|
| `--all` | Update every plugin. |
| `--fresh` | Clear the cache before updating. |

| Argument | Description |
|----------|-------------|
| `PLUGINS` | Plugin IDs as space-separated positional arguments. |

Specify `--all` or at least one plugin name.

## `doctor`

Validate setup and identify problems.

```bash
ai-config doctor
```

| Option | Description |
|--------|-------------|
| `-c, --config PATH` | Configuration file path. |
| `--category CATEGORY` | Run a validation category. Repeat this option as needed. |
| `-t, --target TARGET` | Validate `codex`, `cursor`, `opencode`, `pi`, or `all` output. |
| `--json` | Write JSON. |
| `-v, --verbose` | Show passed checks. |

| Argument | Description |
|----------|-------------|
| `OUTPUT_DIR` | Converted-output directory in target mode. Default: current directory. |

### Default mode

Doctor checks marketplace URLs. It checks installed plugins, skill fields, executable hooks, and MCP server configuration.

### Target mode

Use `--target` to validate converted output:

```bash
ai-config doctor --target codex ./output-dir
ai-config doctor --target all ./output-dir
```

It checks target output structure, `SKILL.md` files, and MCP, hooks, and LSP configuration.

## `convert`

Convert a Claude Code plugin for other AI coding tools.

```bash
ai-config convert PLUGIN_PATH
```

| Option | Description |
|--------|-------------|
| `-t, --target TARGET` | One or more targets: `codex`, `cursor`, `opencode`, `pi`, or `all`. Default: `all`. |
| `-o, --output DIR` | Output directory. The default uses `--scope`. |
| `--scope SCOPE` | `user` or `project`; selects the default output path. |
| `--dry-run` | Preview without writing files. |
| `--best-effort` | Continue when a component cannot convert. |
| `--format FORMAT` | Console format: `summary`, `markdown`, or `json`. |
| `--report PATH` | Report file path. |
| `--report-format FORMAT` | Report format: `json` by default, or `markdown`. |

| Argument | Description |
|----------|-------------|
| `PLUGIN_PATH` | Claude Code plugin directory. |

Targets:

- **codex:** Installable packages and local marketplaces under `.ai-config/codex/`. Configured sync manages the Codex CLI lifecycle.
- **cursor:** `.cursor/` with skills, commands, hooks, and MCP configuration.
- **opencode:** `opencode.json` and `.opencode/` skills.
- **pi:** `.pi/` with skills, prompt templates, and extensions.

Specify a target more than once, for example: `-t codex -t cursor`.

See [Conversion](conversion.md) for details.

## `plugin create`

Create a plugin skeleton.

```bash
ai-config plugin create NAME
```

| Option | Description |
|--------|-------------|
| `--path PATH` | Plugin directory base path. |

The command creates `manifest.yaml`, a skills directory, and a hooks directory.

## `cache clear`

Clear the plugin cache.

```bash
ai-config cache clear
```

The next sync downloads fresh plugin sources. Use this when plugins appear stale.
