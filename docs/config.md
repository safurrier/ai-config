# Configuration

ai-config uses a YAML file to declare your plugins and marketplaces.

## Config File Location

ai-config looks for config in this order:

1. `.ai-config/config.yaml` (project-local)
2. `~/.ai-config/config.yaml` (global)

You can also specify a path with `-c /path/to/config.yaml`.

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
```

## Targets

Currently only Claude Code is supported. Future versions may add Codex CLI and OpenCode.

```yaml
targets:
  - type: claude
    config:
      # Claude-specific config
```

## Marketplaces

Marketplaces are GitHub repositories containing plugins.

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

- `user` - Installed to `~/.claude/plugins/`, available everywhere
- `project` - Installed to `.claude/plugins/`, only for current project

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
```

## Environment Variables

You can use environment variables in config:

```yaml
marketplaces:
  private-plugins:
    source: github
    repo: ${GITHUB_ORG}/private-plugins
```

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
