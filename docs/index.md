# ai-config

Declarative plugin manager for Claude Code — with cross-tool plugin conversion.

## Why This Exists

Claude Code plugins are useful. They let you extend Claude with custom skills, hooks, and MCP servers. The problem is managing them.

Without ai-config, you're running `claude plugin install` and `claude plugin marketplace add` commands by hand across machines. There's no config file. No way to version control your setup. No way to share it.

ai-config fixes that. You write a YAML file describing what plugins you want, and it handles the rest. It also converts your Claude plugins to work with other AI coding tools like Codex, Cursor, and OpenCode.

Or more simply, run `ai-config init` and it writes the config for you.

## Installation

```bash
uv tool install git+https://github.com/safurrier/ai-config
```

This installs `ai-config` globally. Run `ai-config --help` to verify.

### For Development

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

**3. Convert to other tools** (optional)

```bash
ai-config convert ./my-plugin --target codex
```

Converts a Claude Code plugin to work with Codex, Cursor, or OpenCode. You can also set up automatic conversion on sync via the `conversion` config section.

**4. Check status**

```bash
ai-config status
```

Shows what's installed vs what's in config.

## What's Next

- [Commands](commands.md) — Full command reference
- [Configuration](config.md) — Config file format and examples
- [Conversion](conversion.md) — Converting plugins to other AI tools
