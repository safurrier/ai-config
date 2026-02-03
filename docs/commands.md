# Commands

Complete reference for all ai-config commands.

## Overview

| Command | What it does |
|---------|--------------|
| `init` | Interactive config generator |
| `sync` | Install/uninstall plugins to match config |
| `status` | Show what's currently installed |
| `watch` | Auto-sync on file changes |
| `update` | Update plugins to latest versions |
| `doctor` | Validate setup and show fix hints |
| `plugin create` | Scaffold a new plugin |
| `cache clear` | Clear the plugin cache |

## Global Options

All commands support these options:

```bash
ai-config [OPTIONS] COMMAND

Options:
  -c, --config PATH  Path to config file
  --verbose         Enable verbose output
  --help           Show help message
```

## init

Interactive wizard for creating or updating your config file.

```bash
ai-config init
```

**Options:**

- `--non-interactive` - Create config with defaults (no prompts)
- `--force` - Overwrite existing config

The wizard walks you through:

1. Adding marketplaces (GitHub repos with plugins)
2. Selecting plugins from those marketplaces
3. Choosing install scope (user or project)

Creates `.ai-config/config.yaml` in current directory.

## sync

Make installed plugins match your config file.

```bash
ai-config sync
```

**Options:**

- `--fresh` - Clear cache and reinstall everything
- `--dry-run` - Show what would change without doing it

What it does:

- Installs plugins listed in config but not installed
- Uninstalls plugins installed but not in config
- Updates plugin configurations

## status

Show current state of marketplaces and plugins.

```bash
ai-config status
```

Displays:

- Configured marketplaces and their status
- Installed plugins (from config and extra)
- Any sync issues

## watch

Auto-sync when config or plugin files change.

```bash
ai-config watch
```

**Options:**

- `--debounce SECONDS` - Wait time before syncing (default: 1.0)

Useful during plugin development. Watches:

- `.ai-config/config.yaml`
- Plugin directories

Press Ctrl+C to stop.

## update

Update all plugins to their latest versions.

```bash
ai-config update
```

**Options:**

- `--marketplace NAME` - Update only plugins from specific marketplace

## doctor

Validate your setup and find problems.

```bash
ai-config doctor
```

**Options:**

- `--verbose` - Show detailed validation info
- `--fix` - Attempt to fix found issues

Checks:

- Marketplace URLs are reachable
- Plugins are properly installed
- Skills have required fields
- Hooks are executable
- MCP server configs are valid

## plugin create

Scaffold a new plugin.

```bash
ai-config plugin create NAME
```

**Options:**

- `--marketplace NAME` - Create in specific marketplace
- `--type TYPE` - Plugin type (skill, hook, mcp)

Creates plugin directory with:

- `plugin.yaml` - Plugin metadata
- Appropriate starter files based on type

## cache clear

Clear the plugin cache.

```bash
ai-config cache clear
```

Forces fresh downloads on next sync. Use when plugins seem stale.
