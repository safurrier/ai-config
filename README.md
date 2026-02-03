# ai-config

Declarative plugin manager for Claude Code.

(Future: Codex CLI and OpenCode support planned once plugins become more standardized for sharing ai-context)

## Why this exists

Claude Code plugins are useful. They let you extend Claude with custom skills, hooks, and MCP servers. The problem is managing them.

Without ai-config, you're running `claude plugin install` and `claude plugin marketplace add` commands by hand across machines. There's no config file. No way to version control your setup. No way to share it.

ai-config fixes that. You write a YAML file describing what plugins you want, and it handles the rest.

Or more simply, run `ai-config init` and it writes the config for you.

## What this isn't

This README does not have:

- 14 shields.io badges declaring build status, coverage, npm downloads, discord members, twitter followers, and mass-to-charge ratio
- A mass of emojis to make it look "friendly" and "approachable"
- Claims about revolutionizing your development workflow
- Integration with 47 different tools (we integrate with one)
- A "Quick Start" that's actually 73 steps
- Screenshots of a dashboard that doesn't exist
- A "Powered by AI" badge despite just being a for-loop

It's a config file and some commands. That's it.

## Installation

```bash
uv tool install git+https://github.com/safurrier/ai-config
```

This installs `ai-config` globally. Run `ai-config --help` to verify.

### For development

```bash
git clone https://github.com/safurrier/ai-config.git
cd ai-config
just setup    # Install dependencies
just check    # Run lint, type check, tests
```

## Quick Start

**1. Create your config**

```bash
ai-config init
```

Interactive wizard walks you through adding marketplaces and plugins. Creates `.ai-config/config.yaml`.

**2. Sync to install plugins**

```bash
ai-config sync
```

Installs/uninstalls plugins to match your config. Run this after editing `config.yaml`.

If plugins seem stale or out of date:

```bash
ai-config sync --fresh
```

**3. Iterate with watch (plugin development)**

```bash
ai-config watch
```

Auto-syncs when you edit config or plugin files. Press Ctrl+C to stop.

**4. Troubleshoot with doctor**

```bash
ai-config doctor
```

Validates marketplaces, plugins, skills, hooks, and MCP servers. Shows fix hints for any issues.

## What it does

**Declarative config** - Define your plugins in `.ai-config/config.yaml`:

```yaml
version: 1
targets:
  - type: claude
    config:
      marketplaces:
        claude-code-tutorial:
          source: github
          repo: safurrier/claude-code-tutorial
      plugins:
        - id: claude-code-tutorial@claude-code-tutorial
          scope: user
          enabled: true
```

**Interactive setup** - Don't want to write YAML? Run the wizard:

```bash
ai-config init
```

It walks you through adding marketplaces and plugins with arrow-key navigation.

**Sync** - Make reality match your config:

```bash
ai-config sync
```

**Validation** - Find problems before they bite you:

```bash
ai-config doctor
```

Checks that marketplaces exist, plugins are installed, skills are valid, hooks work.

## Commands

| Command | What it does |
|---------|--------------|
| `init` | Interactive config generator |
| `sync` | Install/uninstall plugins to match config |
| `status` | Show what's currently installed |
| `watch` | Auto-sync on file changes (plugin development) |
| `update` | Update plugins to latest versions |
| `doctor` | Validate setup and show fix hints |
| `plugin create` | Scaffold a new plugin |
| `cache clear` | Clear the plugin cache |

## Config file locations

ai-config looks for config in this order:

1. `.ai-config/config.yaml` (project-local)
2. `~/.ai-config/config.yaml` (global)

You can also pass `-c /path/to/config.yaml` to any command.

## Scopes

Plugins can be installed in different scopes:

- **user** - Available everywhere (`~/.claude/plugins/`)
- **project** - Only in the current project (`.claude/plugins/`)

## Troubleshooting

**Plugin installed but not showing up in / commands**

Clear cache and re-sync:

```bash
ai-config sync --fresh
```

**Something's broken and Claude Code won't help**

```bash
ai-config doctor --verbose
```

## License

MIT
