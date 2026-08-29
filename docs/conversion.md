# Conversion

Convert Claude Code plugins for other AI coding tools. Read the target report. Check each degraded item. Keep the source plugin intact.

## Targets

| Target | Output |
|---|---|
| `codex` | Installable Codex packages and local marketplaces under `.ai-config/codex/marketplaces/`. |
| `cursor` | `.cursor/` skills, commands, hooks, and MCP configuration. |
| `opencode` | `.opencode/` skills plus `opencode.json` and `opencode.lsp.json`. |
| `pi` | `.pi/` project output or `.pi/agent/` user skills, prompts, and extensions. |

```bash
ai-config convert ./my-plugin --target codex
ai-config convert ./my-plugin --dry-run
ai-config convert ./my-plugin --target all --report ./report.json
```

## Codex packages

Use the generated package as the source of truth. Let Codex manage its own installed state. Do not edit unrelated Codex settings.

In 0.6.0, the `codex` target stopped writing loose `.codex/skills`, prompts, hooks, and MCP tables. It creates one self-contained package and local marketplace for each source plugin:

```text
.ai-config/codex/marketplaces/ai-config-my-plugin/
├── .agents/plugins/marketplace.json
└── plugins/my-plugin/
    ├── .codex-plugin/plugin.json
    ├── skills/
    │   ├── my-skill/SKILL.md
    │   └── command-my-command/SKILL.md
    └── hooks/hooks.json
```

The package manifest declares supported MCP servers. ai-config copies referenced hook support scripts into the package. It changes `${CLAUDE_PLUGIN_ROOT}` to Codex's `${PLUGIN_ROOT}`. It copies target-native files from the source plugin's targets/codex directory into the package root.

`ai-config convert` generates package sources only. A configured `ai-config sync` also registers generated local marketplaces. It installs or refreshes each plugin through `codex plugin`. Codex owns its installed cache and enablement in `CODEX_HOME`. ai-config does not copy that layout or rewrite unrelated Codex settings.

### Migration from 0.5.x

1. Remove `commands_as_skills` from conversion configuration and `--commands-as-skills` from scripts. Commands always become package skills. Reports mark commands with Claude argument variables as degraded.
2. Run `ai-config sync --dry-run`. Then run `ai-config sync --force-convert`.
3. Check the package with `ai-config doctor --target codex <output-dir>` and `codex plugin list --json`.
4. Review old `.codex/skills`, `.codex/prompts`, `.codex/hooks.json`, and generated MCP entries. Doctor can report stale output. ai-config cannot delete it because it cannot prove that it owns loose files.
5. Remove only legacy files you recognize as ai-config output.

Each generated marketplace uses `ai-config-<normalized-plugin>`. Each installed selector uses `<normalized-plugin>@ai-config-<normalized-plugin>`. The normalized manifest identity controls package paths, both manifests, ownership, Codex CLI selectors, and drift checks. Two configured sources with the same normalized identity fail before files or runtime state change.

Source package versions must follow SemVer 2.0.0, such as 1.2.3 or 1.2.3-rc.1. ai-config allows same-version content refreshes and applies upgrades. It fails closed for ownership or runtime downgrades and provides remediation. It records owned entries only in `.ai-config/codex/ownership.json`. Removal and update use only that state. An unrelated marketplace or plugin collision fails without mutation.

## Sync-driven conversion

Sync uses the configuration as its input. Check the selected scope. Check a custom output root.

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
        targets: [codex, cursor]
        scope: user
```

`scope` selects the default output root. User scope uses `~`. Project scope uses the current project. A custom `output_dir` overrides that root. Codex packages stay in the root's `.ai-config/codex/` tree.

## Component mapping

Read mappings per target. A supported item can still need transformation. An unsupported item needs a separate plan.

| Component | Codex | Cursor | OpenCode | Pi |
|---|---|---|---|---|
| Skills | Package-local native skill | Skill | Skill | Skill |
| Commands | Package skill; degraded with Claude variables | Command | Command | Prompt template |
| Hooks | Supported command hooks in package | Hooks configuration | Unsupported | Extension emulation |
| MCP | Package manifest `mcpServers` | `.cursor/mcp.json` | `opencode.json` | Unsupported |
| LSP | Unsupported | Unsupported | `opencode.lsp.json` | Unsupported |
| Agents | Unsupported | Unsupported | Unsupported | Unsupported |

Reports classify each component as native, transform, emulate, fallback/degraded, or unsupported. A mapping for one target does not change another target's report.

## Shared skill resources

Declare shared resources exactly once per consumer. Use exact file paths. Keep each generated skill complete.

Keep plugin-wide resources DRY. Declare each consumer in its `SKILL.md`:

```yaml
---
name: analyze
description: Analyze data with the shared helper
x-ai-config-includes:
  - shared/analyze.py
  - shared/schema.json
---

Run `${CLAUDE_PLUGIN_ROOT}/shared/analyze.py`.
```

Conversion captures every declared regular file once in the IR. It materializes byte-preserved copies in the generated skill. The following locations are illustrative:

```text
_shared/shared/analyze.py
_shared/shared/schema.json
```

Exact declared root references in instruction Markdown become skill-root-relative paths under `_shared`. The generated `SKILL.md` omits `x-ai-config-includes`. If two skills use the same source, each receives an independent regular-file copy. This intentional distribution-time duplication keeps skills self-contained on Codex, Cursor, OpenCode, and Pi.

V1 accepts exact plugin-root-relative files only. It rejects globs, directory or recursive declarations, absolute paths, empty, dot, or dotdot components, backslashes, symlinks, hardlinks, special files, duplicate declarations, projected-path collisions, and undeclared `${CLAUDE_PLUGIN_ROOT}` references. Declared transitive dependencies need no direct Markdown reference. Reports show a zero rewrite count for them rather than marking them unused. Included scripts and binaries are byte-preserved. They should locate siblings through language mechanisms such as `__file__`.

Reports add one record per include and consumer. Each record gives the plugin-relative logical source, target-relative destination, copy count, duplicated bytes, and direct rewrite count. Pi copies use the normal digest ownership ledger. Codex copies stay inside the generated package root. Cursor and OpenCode write desired copies but do not delete removed copies because containment is not provenance.

## Source safety

These checks protect source bytes. They reject unsafe paths before a read. Do not weaken these limits.

Conversion reads manifests, component files, skill assets, includes, Codex support files, and target-native files through descriptor-relative, no-follow traversal. Traversal starts at one retained plugin source descriptor on POSIX. A platform without the required descriptor APIs fails closed before a source read. It does not claim equivalent race resistance. Absolute or traversing paths, final symlinks, in-root ancestor symlinks, resolved escapes, and non-regular files fail closed before ai-config reads bytes. `--best-effort` can isolate unsafe components so unrelated safe components continue. During sync, the cache digest covers every safely readable plugin file, including shared and target-native bytes. Sync checks that digest again as an execution precondition. Standalone `convert` does not calculate a digest. Sync digest reads and later conversion reads are separate contained passes. They are not one immutable filesystem snapshot.

## Target-native files

Use overrides only for target-specific content. Keep the shared source model neutral. Check the final projection.

Put hand-written files in `targets/<target>/`. ai-config copies them into the target's natural output root. They override a generated regular file at the same path. File and directory conflicts fail. ai-config checks final generated skills after overrides. Native files therefore cannot reintroduce `x-ai-config-includes` or unresolved `${CLAUDE_PLUGIN_ROOT}` references. When an override replaces `SKILL.md` or an included `_shared` copy, report evidence describes the final emitted projection only. For Codex, the natural root is the generated plugin package, not shared `.codex` configuration.

## Options

| Option | Description |
|---|---|
| `-t, --target` | Repeatable `codex`, `cursor`, `opencode`, `pi`, or `all`. |
| `-o, --output` | Output root. |
| `--scope` | `user` or `project` default output root. |
| `--dry-run` | Report packages and files without writing or running lifecycle commands. |
| `--best-effort` | Continue other target conversion after component errors. |
| `--format` | `summary`, `markdown`, or `json`. |
| `--report`, `--report-format` | Write a JSON or Markdown report. |

## Validation and cache

Validate generated output. Inspect lifecycle actions. Keep ownership records for later cleanup.

### Review checklist

Before conversion or sync, review these facts:

- Check the selected target.
- Check the output root.
- Check the plugin identity.
- Check the plugin version.
- Check the source path.
- Check each source file.
- Check declared includes.
- Check native overrides.
- Check the dry-run report.
- Check degraded components.
- Check unsupported components.
- Check generated packages.
- Check generated skills.
- Check generated hooks.
- Check generated MCP settings.
- Check the ownership ledger.
- Check lifecycle actions.
- Check failed actions.
- Check the final state.
- Keep the source unchanged.

```bash
ai-config doctor --target codex ./output-dir
ai-config doctor --target all ./output-dir
ai-config sync --force-convert
```

Sync keys conversion cache entries by configured plugin selector and conversion settings. A cache hit also requires source provenance, physical path, the complete safe source digest, and owned generated Codex bytes. A changed source path refreshes output because target files can contain resolved plugin-root paths. ai-config discards legacy path-keyed entries. Validated tracked output roots remain available for ownership cleanup. Normal sync repairs deleted or changed output without treating an incidental path as plugin identity.

Configured local marketplaces remain the conversion-source authority after Claude installs a cached copy. The configured tree decides the source. A cache does not replace it. If that tree is missing or unsafe, sync retains prior ownership and reports it unavailable. It does not convert stale installed bytes. Remote and marketplace-less plugins can use safely observed installed sources.

A new remote plugin can need Claude installation before sync can inspect its source. The stages are bounded. The second observation happens once. Real sync applies one immutable Claude prerequisite plan. It observes once more. Then it applies a separately validated conversion-only plan. It never retries Claude actions or recursively syncs until quiet. Dry-run reports prerequisite actions and the deferred source. It does not speculate about the second stage. If parsing or conversion fails after installation, completed Claude actions remain visible. Conversion exits non-zero and verification is skipped.

Dry-run and JSON output distinguish planned, completed, and failed actions. `sync --verify` performs one read-only verification after all apply stages succeed. An empty isolated `CODEX_HOME` is a supported initial state. `status --config ... --json` exits non-zero when lifecycle planning finds a non-no-op action or an inspection error. A temporarily unavailable source retains prior ownership. A disabled or removed source triggers cleanup. Removing or disabling Codex also reconciles prior owned roots, including a custom `output_dir` recorded in the conversion cache.

Every Codex subprocess has a finite timeout. Timeout handling is bounded. Failure reports retain useful state. On POSIX, each command starts in a separate process group. After a bounded SIGTERM grace period, timeout cleanup checks and kills a remaining group, even if the direct child exited first. It then performs a bounded reap of the direct child. Non-POSIX platforms receive direct-child timeout cleanup only. ai-config 0.6.0 does not claim descendant cleanup on those platforms. The adapter accepts the repository-supported Codex 0.144.x through 0.149.x JSON contracts. Runtime probe evidence extends through 0.149.0. Malformed, partial, duplicate, inconsistent, or unknown version responses fail closed. Lifecycle failures retain ownership for retry, sanitize child output, identify the stage and command, provide remediation, and report completed and failed actions.
