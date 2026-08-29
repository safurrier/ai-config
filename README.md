# ai-config

Declarative plugin manager for Claude Code, with cross-tool conversion to Codex, Cursor, OpenCode, and Pi.

## Why this exists

You've built an AI coding setup with custom skills, Model Context Protocol (MCP) servers, hooks, and workflows. Then you try Codex or Pi and start from scratch. Or you get a new machine and need to remember what you installed.

ai-config solves both problems. You define your setup in one YAML file, then use it to:

1. **Install your Claude Code plugins reproducibly** across machines with `ai-config sync`.
2. **Convert those plugins** for other tools with the same skills and config.

Keep your customizations out of one tool's config directory. Avoid hand-maintaining Claude plugins, Codex packages, Cursor and OpenCode config, and Pi extensions.

Or more simply: run `ai-config init` and it walks you through the config.

## What this isn't

This README avoids:

- 14 shields.io badges declaring build status, coverage, npm downloads, discord members, twitter followers, and mass-to-charge ratio
- A mass of emojis that make it look "friendly" and "approachable"
- Claims about revolutionizing your development workflow
- A "Quick Start" that's actually 73 steps
- Screenshots of a dashboard that doesn't exist
- A "Powered by AI" badge despite just being a for-loop

It's a config file and some commands. That's it.

## Install

```bash
pip install ai-config-cli
# or
uv tool install ai-config-cli
```

This installs the `ai-config` command. Confirm that it resolves before changing tool config:

```bash
ai-config --help
```

From source, use the repo URL instead:

```bash
uv tool install git+https://github.com/safurrier/ai-config
```

## Quick start: preview before you sync

**1. Create a config**

```bash
ai-config init
```

The wizard adds marketplaces and plugins, then writes `.ai-config/config.yaml` unless you pass `-o`. If the wizard offers to run sync immediately, say no when you want to inspect the file first.

**2. Preview the changes**

```bash
ai-config sync --dry-run
```

This is the safe checkpoint. It shows planned installs, removals, and conversions without writing plugin output.

**3. Apply the sync**

```bash
ai-config sync --verify
```

This makes installed plugins match your config and verifies the result. If your config enables conversion, sync also writes target-tool output for Codex, Cursor, OpenCode, and Pi according to your conversion scope.

**4. Check for problems**

```bash
ai-config doctor
```

Claude Code loads plugins at session start. After sync changes plugins, restart Claude Code to apply them. Use `claude --resume` if you want to continue the previous session.

## What sync does

A config can install Claude Code plugins and convert them for other tools:

```yaml
version: 1
targets:
  - type: claude
    config:
      marketplaces:
        my-plugins:
          source: github
          repo: myorg/ai-plugins
      plugins:
        - id: code-review@my-plugins
          scope: user
      conversion:
        enabled: true
        targets: [codex, cursor, opencode, pi]
        scope: user
```

With conversion enabled, `ai-config sync` can write outputs such as:

- **Claude Code**: plugins installed through Claude Code's plugin system
- **Codex**: installable plugin packages and ai-config-owned local marketplaces under `.ai-config/codex/`. Sync manages them through `codex plugin`.
- **Cursor**: skills, commands, hooks, and Model Context Protocol (MCP) config under `.cursor/` or `~/.cursor/`
- **OpenCode**: skills plus `opencode.json` / `opencode.lsp.json`
- **Pi**: skills, prompt templates, and hook extensions under `.pi/` or `~/.pi/`

The exact paths depend on conversion `scope` and `output_dir`. Codex 0.6.0 is a breaking migration from loose `.codex` output. Review the [Codex migration guide](docs/conversion.md#migration-from-05x) before syncing. See [Configuration](docs/config.md) and [Conversion](docs/conversion.md) for full rules.

## Config lookup

By default, commands look for config in this order:

1. `.ai-config/config.yaml`
2. `.ai-config/config.yml`
3. `~/.ai-config/config.yaml`
4. `~/.ai-config/config.yml`

Project-local config wins over global config. Pass `-c /path/to/config.yaml` to use a specific file.

The config's project root resolves relative local marketplace and conversion-output paths. The loader expands environment variables and `~`, so paths like `$DOTS_REPO/plugins` can stay portable in dotfiles.

## Common workflows

| Workflow | Command | Notes |
|---|---|---|
| Create or update config interactively | `ai-config init` | Writes `.ai-config/config.yaml` by default. |
| Preview sync | `ai-config sync --dry-run` | Use before the first real sync or after large config edits. |
| Apply and verify sync | `ai-config sync --verify` | Installs/uninstalls plugins and runs configured conversion. |
| See installed state | `ai-config status` | Add `--verify` to compare against config. |
| Validate config or output | `ai-config doctor` | Use `--target codex`, `--target cursor`, `--target opencode`, or `--target pi` for converted output. |
| Rebuild stale output | `ai-config sync --fresh` | Clears Claude's plugin cache and reconverts configured outputs while preserving target homes and ownership ledgers. |
| Re-run conversion only | `ai-config sync --force-convert` | Useful after changing conversion targets. |
| Develop local plugins | `ai-config watch` | Add `--dry-run` if you only want file-change reports. |

For options and examples, use [Commands](docs/commands.md). For target behavior and fidelity notes, use [Conversion](docs/conversion.md).

## Development

```bash
git clone https://github.com/safurrier/ai-config.git
cd ai-config
uv sync --all-extras
uv run ruff check src/
uv run ty check src/
uv run pytest tests/unit/ -v
```

If you use `just`, the shortcut is:

```bash
just setup
just check
```

## Troubleshooting

**Preview before sync. Sync can install or uninstall plugins and write converted tool config.**

```bash
ai-config sync --dry-run
```

**Use `--fresh` when Claude's cached plugins or converted output look stale. Leave target files in place because sync preserves and reconciles target ownership state.**

```bash
ai-config sync --fresh
```

**Validate converted output with target doctor. Each Claude feature may map differently because hooks, Model Context Protocol settings, commands, and agents can degrade or skip by target.**

```bash
ai-config doctor --target all ./output-dir
```

## Further reading

- [Commands](docs/commands.md): complete CLI reference
- [Configuration](docs/config.md): config schema, path resolution, scopes, and examples
- [Conversion](docs/conversion.md): target mappings, dry runs, reports, and validation

## License

MIT
