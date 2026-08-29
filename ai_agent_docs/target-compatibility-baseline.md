# Target compatibility baseline

This record states the runtime assumptions for ai-config conversion. It records tested facts. It makes no claims beyond the probes. The tests use clean homes. The tests remove credentials. Each result names
its tool and version.

Last checked: 2026-08-20

It covers Codex packages, source-less Codex marketplace metadata, Codex compatibility, and Claude
skill include metadata. It also records the evidence for shared-resource projection.

## Summary

| Target | ai-config output | Runtime validation |
|---|---|---|
| Claude Code | Source plugin installed through Claude marketplaces | `claude plugin validate/list`, `claude mcp list` |
| Codex | One installable package and local marketplace per source plugin under `.ai-config/codex/marketplaces/` | Isolated marketplace, install, enable, discovery, update, and remove probe. |
| Cursor | `.cursor/skills/`, `.cursor/mcp.json`, `.cursor/hooks.json` | JSON checks and `cursor-agent mcp list` |
| OpenCode | `.opencode/skills/`, `opencode.json`, `opencode.lsp.json` | `opencode debug skill/config`, `opencode mcp list` |
| Pi | Project `.pi/` or user `.pi/agent/` skills, prompts, extensions | Remote procedure call (RPC) `get_commands` and extension-marker probe. |

## Claude 2.1.231 shared-skill metadata evidence

Phase 0 froze the per-skill `x-ai-config-includes` contract after strict validation and native plugin
loading accepted it. Run this isolated, credential-free probe:

```bash
uv run python tests/probes/probe_claude_skill_includes.py
```

The probe captured this output on 2026-08-20. Temporary path suffixes vary.

```text
$ /Users/alexfurrier/.local/share/mise/installs/node/24/bin/claude --version
2.1.231 (Claude Code)
exit=0
$ /Users/alexfurrier/.local/share/mise/installs/node/24/bin/claude plugin validate --strict /var/folders/.../ai-config-include-probe-v4xprg3l
Validating plugin manifest: /var/folders/.../ai-config-include-probe-v4xprg3l/.claude-plugin/plugin.json

✔ Validation passed
exit=0
$ /Users/alexfurrier/.local/share/mise/installs/node/24/bin/claude --plugin-dir /var/folders/.../ai-config-include-probe-v4xprg3l plugin details include-probe
include-probe 1.0.0
  Validate ai-config include metadata
  Source: include-probe@inline

Component inventory
  Skills (1)  one
  Agents (0)
  Hooks (0)
  MCP servers (0)
  LSP servers (0)

Projected token cost
  Always-on:   ~23 tok   added to every session

Per-component (rounded)
  component  always-on  on-invoke
  one              ~20        ~40

  On-invoke cost is paid each time a skill or agent fires.
  Token counts are estimates and may differ from actual usage.
exit=0
```

The probe `SKILL.md` declares:

```yaml
x-ai-config-includes:
  - shared/data.txt
```

This field is ai-config build metadata. It doesn't claim that Claude creates the resource. Claude
accepts and loads the source skill. ai-config removes the field when it creates self-contained target
skills.

## Codex runtime evidence

The live-tag lane resolved `@openai/codex@latest` at execution time on 2026-07-16. It selected 0.144.5.

```text
resolved package: @openai/codex@0.144.5
version output:   codex-cli 0.144.5
binary:           <temporary>/install/node_modules/@openai/codex/bin/codex.js
main tarball:      https://registry.npmjs.org/@openai/codex/-/codex-0.144.5.tgz
main integrity:    sha512-jjB+K+OMv572mKhS+2QuLxWXDJNdpwbPenf+V+8bdq7wg4Scqt3cn6WEekD8wPqDVZqck0HSX17K9rD9kbDJQA==
darwin-arm64:      https://registry.npmjs.org/@openai/codex/-/codex-0.144.5-darwin-arm64.tgz
platform integrity: sha512-zcT6NfBCqLFt+BReNSETTZW6v6PdbH0dzNtm9j7l7mDGqwPbKZDGJdnpkBao2389I0ZacyIKgSZoI0vez1d4Dw==
install source:    integrity-verified direct npm registry tarball extraction
```

The same lane completed package and public-sync probes for 0.145.0 on 2026-07-24. It completed both
probes for 0.146.0 on 2026-07-29. It completed both credential-free probes for 0.148.0 and 0.149.0 on
2026-08-20.

```text
0.145.0 main integrity: sha512-/PSPSFujjjmiyVFvG2yu/grOFhsWdokTH8t2KGWhXSo/M5n/dIDsnbsnO82/7bLtIoDuzQf7ATBUMWqPWQINlQ==
0.145.0 darwin-arm64 integrity: sha512-h6aQ0UxnaP8mIM/9/qPAH9MNkRliJo88toq1T36IxNM2L5JSU0TFamu+MZn7YkFgDsrp0RfiI+97Tm8AVVxqtA==
0.146.0 main integrity: sha512-yG3sPWNda/2YAIQIDq9MrrjoCTIQ7rxYM5IasrG3VBcuhCLTkgeg/JzqmJq1V98RE4MJ5jCxDXXQlOjrditFRw==
0.146.0 darwin-arm64 integrity: sha512-nb61yX4r5L6Z0dlC4o3u0GAK1YCd4TUvjaB382bajDoh84V+uv2hTBIVZ++fgXWV9yoeuNrNnNcn7GoTGOe2Tg==
0.148.0 main tarball: https://registry.npmjs.org/@openai/codex/-/codex-0.148.0.tgz
0.148.0 main integrity: sha512-bh5kH9+BMrFaHGmLeoSansPdfRksvr4UXzjQInns/KRO7r8VJ+6AAW+SqUsE8XcG3+OW/mI4EEy8Gpo9UDXGvQ==
0.148.0 darwin-arm64: https://registry.npmjs.org/@openai/codex/-/codex-0.148.0-darwin-arm64.tgz
0.148.0 platform integrity: sha512-xgBPFiF1fHUlRS7HE6wGB56LjBJh16kGD7b4TTbwdVBZNB4QDkTok+vdkAGrfpVkfKcwGNhPSKDgCw+KMZOVug==
0.149.0 main tarball: https://registry.npmjs.org/@openai/codex/-/codex-0.149.0.tgz
0.149.0 main integrity: sha512-i4dryj2Y1j+00Mb5n+0n71EYnTK9/KDc2cdFo/dXD0d1oTog2bhUssKDEIOnKmnEf51P0Z/HJTWvTKw/UHyOvQ==
0.149.0 darwin-arm64: https://registry.npmjs.org/@openai/codex/-/codex-0.149.0-darwin-arm64.tgz
0.149.0 platform integrity: sha512-GsZJbzBWiD48RETrO8VHGAQNgfSrUVxItXZFeD87wswatPi0+lKuQo8Dx4nMYmOZhZrVtwr3al/feRrZxnDV8Q==
install source: integrity-verified direct npm registry tarball extraction
```

The 0.149.0 release notes report no plugin lifecycle contract change. Its probes confirmed the same
feature rows, help surfaces, JSON schemas, identities, lifecycle behavior, and source-less catalog
visibility as 0.148.0.

```text
hooks                                stable             true
plugin_sharing                       stable             true
plugins                              stable             true
remote_plugin                        stable             true
```

`remote_plugin` changed from `under development false` in 0.142.3 to `stable true`. ai-config's local
package design doesn't rely on remote plugins.

| Command | Contract |
|---|---|
| `codex plugin --help` | Manage Codex plugins |
| `codex plugin add --help` | Install a plugin from a configured marketplace snapshot. |
| `codex plugin list --help` | List plugins available from configured marketplace snapshots. |
| `codex plugin remove --help` | Remove an installed plugin from local config and cache. |
| `codex plugin marketplace --help` | Add, list, upgrade, or remove configured plugin marketplaces. |
| `codex plugin marketplace add --help` | Add a local or Git marketplace to configured plugin marketplaces. |
| `codex plugin marketplace list --help` | List marketplaces Codex considers and their roots. |
| `codex plugin marketplace upgrade --help` | Refresh configured Git marketplace snapshots. |
| `codex plugin marketplace remove --help` | Remove a configured marketplace source by name. |

Official sources checked through 2026-08-20:

- [Codex changelog](https://developers.openai.com/codex/changelog)
- [Codex 0.149.0 release](https://github.com/openai/codex/releases/tag/rust-v0.149.0)
- [Codex 0.148.0 release](https://github.com/openai/codex/releases/tag/rust-v0.148.0)
- [Codex 0.146.0 release](https://github.com/openai/codex/releases/tag/rust-v0.146.0)
- [Codex 0.145.0 release](https://github.com/openai/codex/releases/tag/rust-v0.145.0)
- [Plugins](https://learn.chatgpt.com/docs/plugins)
- [Build plugins](https://learn.chatgpt.com/docs/build-plugins)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Hooks](https://learn.chatgpt.com/docs/hooks)
- [Developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)

## Codex package contract

- `.codex-plugin/plugin.json` owns package metadata, `skills`, `hooks`, and `mcpServers`.
- `.agents/plugins/marketplace.json` points to a local package source.
- Package skills use the native Agent Skills format. Claude commands become package skills. Commands with `$ARGUMENTS` or positional variables have degraded support because Codex has no Claude slash-command substitution.
- Supported command hooks use `hooks/hooks.json`. `${CLAUDE_PLUGIN_ROOT}` becomes `${PLUGIN_ROOT}`. The package copies referenced support scripts. Missing support files omit the handler and add a diagnostic.
- MCP servers become manifest `mcpServers` entries. Agents and Language Server Protocol (LSP) servers remain unsupported.
- `targets/codex/**` files land in the package root and can override generated package files.
- ai-config emits no `.codex/skills`, `.codex/prompts`, `.codex/hooks.json`, or direct generated `[mcp_servers.*]` tables.

`ai-config sync` uses the Codex CLI for marketplace and installed-cache state. ai-config owns only its
generated marketplace directories and `.ai-config/codex/ownership.json`. Codex owns `$CODEX_HOME/config.toml`,
enablement, and cache. Parsed source identity is the sole normalized key for manifests, ownership, CLI
selectors, and drift checks. Collisions, duplicates, source or path mismatches, and SemVer downgrades
fail before mutation. Removal needs an ownership-file record. `doctor` reports old loose output but does
not remove it without ownership proof.

The adapter supports Codex 0.144.x through 0.149.x. It checks the CLI version, typed schemas, and
semantic identity for marketplace and plugin list, add, and remove responses. Malformed JSON, duplicate
keys or records, partial output, unknown versions, and inconsistent success responses are errors. Each
call has a finite timeout. The adapter bounds error output and strips control characters. On POSIX, calls use a
separate process group. Cleanup sends SIGTERM, checks for survivors, kills the group, and reaps the direct
child. Non-POSIX cleanup handles only the direct child. Version 0.6.0 doesn't promise descendant cleanup
on those platforms.

Codex 0.144.5 can omit `marketplaceSource` when no configured source matches the marketplace root. The
adapter accepts only absence. A present value must be a typed object with a known source type and a
non-empty source. Installed rows without it retain the plugin source but infer no marketplace root.
Desired or owned identity collisions still fail before mutation. Codex 0.148.0 and 0.149.0 don't list
the probe's seeded `$CODEX_HOME/.tmp/plugins` source-less catalog. The public-sync probe records its
initial CLI visibility and exact files, then requires both to remain unchanged. Configured marketplace
and plugin schemas and behavior remain compatible.

## Isolated runtime probe

```bash
tests/probes/probe_latest_codex.sh
```

The shell lane runs `probe_codex_plugin_package.py` and `probe_ai_config_sync_codex.py`. Each creates
fresh `HOME` and `CODEX_HOME`. Each removes `OPENAI_API_KEY`, `CODEX_API_KEY`, `CHATGPT_API_KEY`,
`OPENAI_ORG_ID`, and `OPENAI_PROJECT_ID`.

The package probe proves generation and validation, marketplace and plugin lifecycle actions, enabled and
disabled discovery through `debug prompt-input`, hooks and MCP ingestion, updates, idempotence, managed
removal, unrelated-state preservation, and strict doctor loading. The public-command probe runs
`python -m ai_config sync --config <isolated> --json` against a disposable marketplace and real Codex.
It proves registration, no-op sync, repair, SemVer refresh, drift reporting, reinstall and removal, plus
preservation of unrelated state and the source-less catalog. The all-tools E2E lane runs both probes.

The Docker all-tools image pins `@openai/codex@0.145.0`. A separate lane resolves and probes `@latest`.
This keeps reproducibility and drift detection independent.

## Other target assumptions

### Pi

- Project skills, prompts, and extensions use `.pi/`. User scope uses `.pi/agent/`.
- Hook commands use TypeScript extensions.
- RPC `get_commands` proves skill discovery without credentials.

### Cursor

- Output includes `.cursor/skills/`, `.cursor/mcp.json`, and `.cursor/hooks.json`.
- `cursor-agent mcp list` checks the Model Context Protocol (MCP). Skill validation stays file based.

### OpenCode target

- Output includes `.opencode/skills/`, `opencode.json`, and `opencode.lsp.json`.
- Use `opencode debug skill/config/paths` and `opencode mcp list` for auth-free probes.

## Update checklist

1. Resolve versions and record exact binaries and install sources.
2. Confirm help and probe surfaces before use.
3. Isolate runtime homes and credentials.
4. Update emitters, validators, docs, and real-tool tests together.
5. Pin a reproducible E2E version and retain a distinct latest lane.
