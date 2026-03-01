# ai-config

Declarative plugin manager for Claude Code — with cross-tool conversion to Codex, Cursor, and OpenCode.

## Why this exists

Claude Code plugins are useful. They let you extend Claude with custom skills, hooks, and MCP servers. The problem is managing them.

Without ai-config, you're running `claude plugin install` and `claude plugin marketplace add` commands by hand across machines. There's no config file. No way to version control your setup. No way to share it.

ai-config fixes that. You write a YAML file describing what plugins you want, and it handles the rest. It also converts your Claude plugins to work with other AI coding tools so you don't have to maintain separate configs.

Or more simply, run `ai-config init` and it walks you through everything.

## What this isn't

This README does not have:

- 14 shields.io badges declaring build status, coverage, npm downloads, discord members, twitter followers, and mass-to-charge ratio
- A mass of emojis to make it look "friendly" and "approachable"
- Claims about revolutionizing your development workflow
- A "Quick Start" that's actually 73 steps
- Screenshots of a dashboard that doesn't exist
- A "Powered by AI" badge despite just being a for-loop

It's a config file and some commands. That's it.

## Installation

```bash
pip install ai-config-cli
# or
uv tool install ai-config-cli
```

This installs `ai-config` globally. Run `ai-config --help` to verify.

### From source (latest)

```bash
uv tool install git+https://github.com/safurrier/ai-config
```

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

Interactive wizard walks you through adding marketplaces and plugins. Supports GitHub repos and local paths (including env vars like `$DOTS_REPO/plugins` for portability across machines). Creates `.ai-config/config.yaml`.

**2. Sync to install plugins**

```bash
ai-config sync
```

Installs/uninstalls plugins to match your config. If you have conversion enabled, it also generates config for Codex, Cursor, and OpenCode.

If plugins seem stale or out of date:

```bash
ai-config sync --fresh
```

**3. Iterate with watch (plugin development)**

```bash
ai-config watch
```

Auto-syncs when you edit config or plugin files. Press Ctrl+C to stop.

**Note:** Claude Code loads plugins at session start. After changes sync, restart Claude Code to apply them. Use `claude --resume` to continue your previous session.

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
        my-marketplace:
          source: github
          repo: owner/repo
        my-local-plugins:
          source: local
          path: $DOTS_REPO/plugins    # env vars preserved for portability
      plugins:
        - id: my-plugin@my-marketplace
          scope: user
          enabled: true
      conversion:
        enabled: true
        targets: [codex, cursor, opencode]
        scope: user
```

**Interactive setup** - Don't want to write YAML? Run the wizard:

```bash
ai-config init
```

Walks you through adding marketplaces and plugins with arrow-key navigation. Escape goes back a step, Ctrl+C cancels.

**Sync** - Make reality match your config:

```bash
ai-config sync
```

**Cross-tool conversion** - Generate config for other AI coding tools:

```bash
ai-config convert --plugin ~/.claude/plugins/my-plugin --target codex
```

Or let sync handle it automatically with the `conversion:` section in your config. Skills, hooks, MCP servers, and commands are mapped to each tool's native format.

**Validation** - Find problems before they bite you:

```bash
ai-config doctor
ai-config doctor --target codex    # validate converted output
```

Checks that marketplaces exist, plugins are installed, skills are valid, hooks work.

## Commands

| Command | What it does |
|---------|--------------|
| `init` | Interactive config generator |
| `sync` | Install/uninstall plugins to match config (+ conversion) |
| `status` | Show what's currently installed |
| `watch` | Auto-sync on file changes (plugin development) |
| `update` | Update plugins to latest versions |
| `doctor` | Validate setup and show fix hints |
| `convert` | Convert a plugin to another tool's format |
| `plugin create` | Scaffold a new plugin |
| `cache clear` | Clear the plugin cache |

## Config file locations

ai-config looks for config in this order:

1. `.ai-config/config.yaml` (project-local)
2. `~/.ai-config/config.yaml` (global)

You can also pass `-c /path/to/config.yaml` to any command.

Paths support environment variables (`$MY_VAR`) and tilde (`~`), expanded at load time.

## Scopes

Plugins can be installed in different scopes:

- **user** - Available everywhere (`~/.claude/plugins/`)
- **project** - Only in the current project (`.claude/plugins/`)

## Conversion targets

ai-config converts Claude plugins to work with:

| Tool | Output | Binary |
|------|--------|--------|
| Codex (OpenAI) | `.codex/` | `codex` |
| Cursor | `.cursor/` | `cursor-agent` |
| OpenCode | `.opencode/` | `opencode` |

Skills, commands, hooks, and MCP servers are mapped to each tool's native format. Not everything maps 1:1 — conversion reports show what was native, approximated, or unsupported.

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

**Converted output looks wrong**

```bash
ai-config doctor --target codex
```

## License

MIT
