# Configuration

ai-config uses YAML to declare plugins, marketplaces, and conversion settings.

## Configuration file location

ai-config reads configuration in this order:

1. `.ai-config/config.yaml` in the project
2. `.ai-config/config.yml` in the project
3. `~/.ai-config/config.yaml`
4. `~/.ai-config/config.yml`

A project file takes precedence over a global file. You can also provide a path with `-c /path/to/config.yaml`.

## Structure

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
        # Optional conversion settings
```

## Source target

Claude Code is the only source target. The `conversion` section and the `convert` command produce output for Codex, Cursor, OpenCode, and Pi.

```yaml
targets:
  - type: claude
    config:
      # Claude-specific configuration
```

## Marketplaces

A marketplace contains plugins.

### GitHub marketplace

```yaml
marketplaces:
  claude-code-tutorial:
    source: github
    repo: safurrier/claude-code-tutorial

  my-plugins:
    source: github
    repo: myorg/my-plugins
    branch: main  # Optional; defaults to main
```

### Local marketplace

A local marketplace points to a directory. This is useful for development or private plugins.

```yaml
marketplaces:
  dev-plugins:
    source: local
    path: ./plugins
  dotfiles-plugins:
    source: local
    path: $DOTS_REPO/config/ai-config/plugins
```

ai-config resolves relative paths from the configuration file's parent directory. It uses absolute paths unchanged. At load time, it expands `$VAR`, `${VAR}`, and `~`. Use those forms to make paths portable.

Each marketplace has a name. Plugin entries use that name.

## Plugins

A plugin entry names a marketplace item.

```yaml
plugins:
  - id: claude-code-tutorial@claude-code-tutorial
    scope: user
    enabled: true

  - id: my-plugin@my-plugins
    scope: project
    enabled: true
```

**Plugin ID:** `plugin-name@marketplace-name`

**Scopes:**

- `user`: Install to `~/.claude/plugins/` for all projects.
- `project`: Install to `.claude/plugins/` for this project.

## Conversion

The `conversion` section enables automatic conversion after sync installs plugins.

```yaml
conversion:
  enabled: true
  targets:
    - codex
    - cursor
    - opencode
    - pi
  scope: project
  output_dir: ./converted    # Optional
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Enables conversion. |
| `targets` | list | Required | `codex`, `cursor`, `opencode`, or `pi`. |
| `scope` | string | `"project"` | `"user"` writes to the home directory; `"project"` writes to the current directory. |
| `output_dir` | string | Automatic | Custom output directory. Relative paths use the configuration file location. |

Without `output_dir`, user scope writes under `~` and project scope writes under the current directory.

For Codex, ai-config normalizes the source plugin's `.claude-plugin/plugin.json` identity once. It uses that identity for generated paths and runtime selectors. Source `version` values must follow SemVer 2.0.0. Configured sources with the same normalized Codex identity fail before mutation.

See [Conversion](conversion.md) for conversion details.

## Full example

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

        # Project-specific tooling
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
          - opencode
          - pi
        scope: project
```

## Environment variables

Use environment variables in local marketplace paths and conversion output directories:

```yaml
marketplaces:
  my-plugins:
    source: local
    path: $MY_REPO/plugins        # Expanded at load time
    # ${MY_REPO}/plugins and ~/plugins also work
conversion:
  output_dir: $PROJECT_ROOT/output  # Expanded at load time
```

ai-config calls `os.path.expandvars` at load time. If a variable is undefined, its literal `$VAR` text remains. The resulting path can fail to resolve. `ai-config init` preserves environment-variable text for portability.

## Validation

Validate configuration with:

```bash
ai-config doctor --verbose
```

This checks:

- YAML syntax
- Required fields
- Marketplace repository access
- Plugin references
