---
id: config
title: Configuration
description: >
  YAML configuration reference for ai-config. Covers config file location,
  structure, targets, marketplaces, plugins, conversion settings, and validation.
index:
  - id: config-file-location
  - id: config-structure
  - id: targets
  - id: marketplaces
  - id: plugins
  - id: conversion
  - id: full-example
  - id: environment-variables
  - id: validation
---

# Configuration

ai-config uses a YAML file to declare your plugins, marketplaces, and conversion settings.

## Config File Location

ai-config looks for config in this order:

1. `.ai-config/config.yaml` (project-local)
2. `.ai-config/config.yml` (project-local, alternate extension)
3. `~/.ai-config/config.yaml` (global)
4. `~/.ai-config/config.yml` (global, alternate extension)

Project-local config takes precedence over global config. You can also specify an explicit path with `-c /path/to/config.yaml`.

## Config Structure

```yaml
version: 1
targets:
  - type: claude
    config:
      marketplaces:
        # Marketplace definitions
      plugins:
        # Plugin references
      conversion:
        # Conversion settings (optional)
```

## Targets

Currently only Claude Code is supported as a source target. Conversion to Codex, Cursor, and OpenCode is handled by the `conversion` config section or the `convert` command.

```yaml
targets:
  - type: claude
    config:
      # Claude-specific config
```

## Marketplaces

Marketplaces are repositories containing plugins.

### GitHub Marketplaces

```yaml
marketplaces:
  claude-code-tutorial:
    source: github
    repo: safurrier/claude-code-tutorial

  my-plugins:
    source: github
    repo: myorg/my-plugins
    branch: main  # optional, defaults to main
```

### Local Marketplaces

Local marketplaces point to a directory on disk. Useful for development or private plugins that aren't hosted on GitHub.

```yaml
marketplaces:
  dev-plugins:
    source: local
    path: ./plugins
  dotfiles-plugins:
    source: local
    path: $DOTS_REPO/config/ai-config/plugins
```

Relative paths are resolved from the config file's parent directory (the repo root, not the `.ai-config/` directory). Absolute paths are used as-is. Environment variables (`$VAR` or `${VAR}`) and tilde (`~`) are expanded at load time — use them for portability across machines.

Each marketplace has a name (used to reference plugins) and a source config.

## Plugins

Plugins reference items from marketplaces.

```yaml
plugins:
  - id: claude-code-tutorial@claude-code-tutorial
    scope: user
    enabled: true

  - id: my-plugin@my-plugins
    scope: project
    enabled: true
```

**Plugin ID format:** `plugin-name@marketplace-name`

**Scopes:**

- `user` — Installed to `~/.claude/plugins/`, available everywhere
- `project` — Installed to `.claude/plugins/`, only for current project

## Conversion

Configure automatic plugin conversion to other AI coding tools. When present, `ai-config sync` converts all synced plugins to the specified targets after installing them.

```yaml
conversion:
  enabled: true
  targets:
    - codex
    - cursor
    - opencode
  scope: project
  output_dir: ./converted    # optional
  commands_as_skills: false   # optional
```

**Fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Enable/disable conversion |
| `targets` | list | *(required)* | Target tools: `codex`, `cursor`, `opencode` |
| `scope` | string | `"project"` | `"user"` (writes to home dir) or `"project"` (writes to cwd) |
| `output_dir` | string | *(auto)* | Custom output directory. Relative paths resolve from config file location |
| `commands_as_skills` | bool | `false` | Convert commands to skills instead of prompts (Codex-specific) |

When `output_dir` is not set, output goes to the home directory (`~`) for `user` scope or the current directory for `project` scope.

See [Conversion](conversion.md) for a full guide on what gets converted and how.

## Full Example

```yaml
version: 1
targets:
  - type: claude
    config:
      marketplaces:
        claude-code-tutorial:
          source: github
          repo: safurrier/claude-code-tutorial

        company-plugins:
          source: github
          repo: mycompany/claude-plugins

        dev-plugins:
          source: local
          path: ./plugins

      plugins:
        # Tutorial plugin for learning Claude Code
        - id: claude-code-tutorial@claude-code-tutorial
          scope: user
          enabled: true

        # Company-wide coding standards
        - id: coding-standards@company-plugins
          scope: user
          enabled: true

        # Project-specific tooling (only in this repo)
        - id: project-tools@company-plugins
          scope: project
          enabled: true

        # Local development plugin
        - id: my-dev-tool@dev-plugins
          scope: project
          enabled: true

      conversion:
        enabled: true
        targets:
          - codex
          - cursor
        scope: project
        commands_as_skills: false
```

## Environment Variables

You can use environment variables in local marketplace paths and conversion output directories:

```yaml
marketplaces:
  my-plugins:
    source: local
    path: $MY_REPO/plugins        # expanded at load time
    # also works: ${MY_REPO}/plugins, ~/plugins
conversion:
  output_dir: $PROJECT_ROOT/output  # also expanded
```

Variables are expanded at load time using `os.path.expandvars`. If a variable is undefined, the literal `$VAR` string is kept (and the path will likely fail to resolve). The `ai-config init` wizard preserves env var strings in the config file for portability.

## Validation

Run `ai-config doctor` to validate your config:

```bash
ai-config doctor --verbose
```

This checks:

- YAML syntax is valid
- Required fields are present
- Marketplace repos are accessible
- Plugin references resolve
