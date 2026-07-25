# Target Compatibility Baseline

This file records the runtime assumptions behind ai-config target conversion.

Last checked: 2026-07-24
Context: first-class Codex plugin packages for issue #18 / ai-config 0.6.0 and source-less Codex marketplace metadata for issue #20.

## Summary

| Target | ai-config output | Runtime validation |
|---|---|---|
| Claude Code | Source plugin installed through Claude marketplaces | `claude plugin validate/list`, `claude mcp list` |
| Codex | One installable package and local marketplace per source plugin under `.ai-config/codex/marketplaces/` | isolated marketplace/install/enable/discovery/update/remove probe |
| Cursor | `.cursor/skills/`, `.cursor/mcp.json`, `.cursor/hooks.json` | JSON checks and `cursor-agent mcp list` |
| OpenCode | `.opencode/skills/`, `opencode.json`, `opencode.lsp.json` | `opencode debug skill/config`, `opencode mcp list` |
| Pi | project `.pi/` or user `.pi/agent/` skills, prompts, extensions | RPC `get_commands` and extension marker probe |

## Codex 0.144.5 and 0.145.0 evidence

The latest lane resolved npm's `@openai/codex@latest` tag at execution time on 2026-07-16:

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

The same lane resolved and passed the complete package and public-sync probes for Codex 0.145.0 on
2026-07-24:

```text
resolved package: @openai/codex@0.145.0
version output:   codex-cli 0.145.0
main integrity:   sha512-/PSPSFujjjmiyVFvG2yu/grOFhsWdokTH8t2KGWhXSo/M5n/dIDsnbsnO82/7bLtIoDuzQf7ATBUMWqPWQINlQ==
darwin-arm64 integrity: sha512-h6aQ0UxnaP8mIM/9/qPAH9MNkRliJo88toq1T36IxNM2L5JSU0TFamu+MZn7YkFgDsrp0RfiI+97Tm8AVVxqtA==
install source:    integrity-verified direct npm registry tarball extraction
```

The direct extraction in `tests/probes/probe_latest_codex.sh` is intentional. npm's configured
install-date cutoff rejected a normal fresh install because 0.144.5 was newer than the cutoff.
The lane still resolves the live tag, reads each registry URL and integrity value, verifies SHA-512,
and recreates npm's main-plus-platform package layout. It does not call an older installed Codex
"latest."

Exact feature rows:

```text
hooks                                stable             true
plugin_sharing                       stable             true
plugins                              stable             true
remote_plugin                        stable             true
```

This differs from the 0.142.3 spike: `remote_plugin` moved from `under development false` to
`stable true`. ai-config's local package implementation does not depend on remote plugin behavior.

Observed help surfaces:

| Command | First help line / contract |
|---|---|
| `codex plugin --help` | Manage Codex plugins |
| `codex plugin add --help` | Install a plugin from a configured marketplace snapshot. |
| `codex plugin list --help` | List plugins available from configured marketplace snapshots |
| `codex plugin remove --help` | Remove an installed plugin from local config and cache. |
| `codex plugin marketplace --help` | Add, list, upgrade, or remove configured plugin marketplaces |
| `codex plugin marketplace add --help` | Add a local or Git marketplace to configured sources |
| `codex plugin marketplace list --help` | List configured marketplaces and roots |
| `codex plugin marketplace upgrade --help` | Refresh configured Git marketplace snapshots. |
| `codex plugin marketplace remove --help` | Remove a configured marketplace source by name |

Official sources checked on 2026-07-24:

- [Codex changelog](https://developers.openai.com/codex/changelog)
- [Codex 0.145.0 release](https://github.com/openai/codex/releases/tag/rust-v0.145.0)
- [Plugins](https://learn.chatgpt.com/docs/plugins)
- [Build plugins](https://learn.chatgpt.com/docs/build-plugins)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Hooks](https://learn.chatgpt.com/docs/hooks)
- [Developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)

## Codex package contract used by ai-config

- `.codex-plugin/plugin.json` owns package metadata, `skills`, `hooks`, and `mcpServers`.
- `.agents/plugins/marketplace.json` points to a local package source.
- Package skills are native Agent Skills. Claude commands become package skills; commands using
  `$ARGUMENTS` or positional variables are reported degraded because Codex skills do not provide
  Claude slash-command substitution.
- Supported command hooks become package `hooks/hooks.json`. `${CLAUDE_PLUGIN_ROOT}` becomes
  `${PLUGIN_ROOT}`, and referenced support scripts are copied into the package. Missing support
  files cause the handler to be omitted and diagnosed.
- MCP servers become manifest `mcpServers` entries. Agents and LSP servers remain unsupported.
- `targets/codex/**` files land inside the package root and can override generated package files.
- No new `.codex/skills`, `.codex/prompts`, `.codex/hooks.json`, or direct generated
  `[mcp_servers.*]` tables are emitted.

`ai-config sync` uses the Codex CLI for marketplace and installed-cache state. ai-config owns only
its generated marketplace directories and `.ai-config/codex/ownership.json`; Codex owns
`$CODEX_HOME/config.toml`, enablement, and cache. Parsed source identity is the sole normalized key
for package/marketplace manifests, ownership, CLI selectors, and drift checks. Normalized collisions,
duplicate runtime records, source/path mismatches, and SemVer downgrades fail before mutation.
Removal is limited to entries recorded in the ownership file. Possible old loose output is reported
by `doctor` and never removed without proof of ownership.

The adapter intentionally accepts only the observed Codex 0.144.x and 0.145.x contracts. It validates
the CLI version plus typed schemas and semantic identity for marketplace list/add/remove and plugin
list/add/remove responses. Malformed JSON, duplicate keys/records, partial output, unknown versions,
and inconsistent success responses are errors. Every call uses a finite timeout and bounds/strips
control characters from error output. POSIX calls start a separate process group; after a bounded
SIGTERM grace period, timeout cleanup inspects and kills any remaining group even if the direct child
already exited, then performs a bounded direct-child reap. Non-POSIX cleanup is limited to the direct
child; 0.6.0 does not advertise descendant cleanup on those platforms.

Codex 0.144.5 can omit `marketplaceSource` from resolved marketplace and plugin catalog rows when no
configured source corresponds to the resolved marketplace root. The adapter accepts only absence:
a present value must remain a typed object with a known source type and non-empty source. Installed
rows without this metadata retain their plugin source but have no inferred marketplace root, so
desired or previously owned identity collisions still fail before mutation.

## Isolated runtime probe

```bash
tests/probes/probe_latest_codex.sh
```

The latest shell lane runs both `probe_codex_plugin_package.py` and
`probe_ai_config_sync_codex.py`. Each creates fresh `HOME` and `CODEX_HOME`, removes
`OPENAI_API_KEY`, `CODEX_API_KEY`, `CHATGPT_API_KEY`, `OPENAI_ORG_ID`, and
`OPENAI_PROJECT_ID`.

The isolated generated-package probe proves:

1. generated package and marketplace validation;
2. marketplace add/list and plugin available/install/list;
3. enabled, disabled, and re-enabled skill discovery through `debug prompt-input`;
4. package hooks copied to the installed cache and package MCP visible through `mcp list`;
5. content update followed by CLI remove/reinstall and updated discovery;
6. repeated sync leaves Codex config byte-identical;
7. managed removal leaves an unrelated marketplace, plugin, disabled/enabled state, and scalar config;
8. strict Codex doctor still loads the resulting config.

The public-command probe invokes `python -m ai_config sync --config <isolated> --json` against a
disposable source marketplace and real Codex binary. It proves first registration/install,
unchanged no-op, automatic repair of tampered generated output, SemVer refresh/update and
discovery, status drift reporting, disabled-plugin reinstall, missing-plugin repair, owned removal,
and preservation of unrelated marketplace, plugin enablement, scalar config, and source-less
marketplace/plugin catalog state. The pinned all-tools E2E lane runs both probes.

The Docker all-tools image pins `@openai/codex@0.145.0`. The separate workflow latest lane resolves
and probes `@latest` so reproducibility and drift detection remain independent.

## Other target assumptions

### Pi

- Project skills/prompts/extensions use `.pi/`; user scope uses `.pi/agent/`.
- Hook commands are emulated with TypeScript extensions.
- RPC `get_commands` proves skill discovery without credentials.

### Cursor

- Output includes `.cursor/skills/`, `.cursor/mcp.json`, and `.cursor/hooks.json`.
- `cursor-agent mcp list` is the available real-tool MCP check; skill validation remains file based.

### OpenCode

- Output includes `.opencode/skills/`, `opencode.json`, and `opencode.lsp.json`.
- `opencode debug skill/config/paths` and `opencode mcp list` are preferred auth-free probes.

## Update checklist

1. Resolve current versions and record exact binaries/install sources.
2. Confirm named help/probe surfaces before using them.
3. Isolate runtime homes and credentials.
4. Update emitters, validators, docs, and real-tool tests together.
5. Pin a reproducible E2E version and retain an explicit latest lane.
