# Target Compatibility Baseline

This file records the target-runtime assumptions that ai-config's converter support matrix is based on. Update it when target CLI behavior changes or when refreshing conversion support.

Last checked: 2026-07-13
Context: Codex plugin/package feasibility spike ([issue #13](https://github.com/safurrier/ai-config/issues/13))

Current Codex snapshot:

```text
command: /opt/homebrew/bin/codex --version
output:  codex-cli 0.142.3
binary:  /opt/homebrew/bin/codex
root:    /opt/homebrew/Caskroom/codex/0.142.3/
host:    local macOS Homebrew cask installation
```

The earlier multi-tool snapshot remains `pi 0.74.0`, npm Codex `0.129.0`, and npm Pi
`0.74.0` as of 2026-05-15; those tools were not refreshed for this Codex-only spike.

## Summary

| Target | Observed support | ai-config output | Runtime validation |
|---|---|---|---|
| Claude Code | Native plugin marketplace, skills, hooks, MCP | Source tool, not emitted by converter | `claude plugin validate`, `claude plugin list --json`, `claude mcp list` |
| Codex | Agent Skills, MCP in `config.toml`, hooks, and installable plugin bundles | Loose files under `.codex/`; experimental package fixture is test-only | `codex debug prompt-input`, `codex mcp list`, and the isolated plugin package probe |
| Cursor | Skills, MCP JSON, hooks JSON | `.cursor/skills/`, `.cursor/mcp.json`, `.cursor/hooks.json` | JSON validation, `cursor-agent mcp list` when available |
| OpenCode | Skills, MCP/config, LSP/config debug surfaces | `.opencode/skills/`, `opencode.json`, `opencode.lsp.json` | `opencode debug skill`, `opencode debug config`, `opencode mcp list` |
| Pi | Skills, prompt templates, TypeScript extensions | `.pi/skills/`, `.pi/prompts/`, `.pi/extensions/`; user-scope under `.pi/agent/` | RPC `get_commands`, `pi --extension` marker hook |

## Version capture commands

Run these during each target refresh and paste observed outputs below or into the PR notes:

```bash
claude --version
codex --version
pi --version
cursor-agent --version || cursor --version
opencode --version
```

## Current assumptions

### Claude Code

- Claude plugin support is the source format for ai-config.
- Sync behavior installs local/GitHub plugin marketplaces and plugins through Claude CLI commands.
- Use valid marketplace fixtures for `claude plugin validate`; the broad `complete-plugin` fixture may intentionally include fields that are useful for parser coverage but invalid for current Claude validation.

Validation patterns:

```bash
claude plugin validate tests/fixtures/test-marketplace/test-plugin
claude plugin marketplace list --json
claude plugin list --json
claude mcp list 2>&1
```

### Codex

#### Existing loose-file target

The production `codex` target is unchanged by the package spike:

- Agent Skills go to `.codex/skills` for project and user output. They do not go to
  `.agents/skills`, which Pi also scans and would report as duplicate output.
- Commands become deprecated custom prompts by default or skills with
  `--commands-as-skills`. MCP servers become `[mcp_servers.*]` tables in
  `.codex/config.toml`. Supported command hooks become `.codex/hooks.json`.
- Shared `config.toml` and `hooks.json` files are merged on write. Unrelated existing settings,
  hooks, and quoted keys are preserved; generated values replace conflicting keys, and generated
  hooks are deduplicated.
- `CodexOutputValidator` checks loose skill frontmatter, TOML structure and MCP entries,
  hook JSON, and deprecated prompts. It does not validate plugin manifests or marketplaces.
- Conversion reports use the common mapping statuses. Skills are native, MCP and supported hooks
  are transforms, prompts are a degraded fallback, and agents/LSP servers are skipped. Target
  mappings and output ownership remain separate. An unexpected emitter exception still aborts a
  multi-target conversion unless `--best-effort` is enabled.

The loose target's hook flag is now stale: Codex 0.142.3 lists `hooks` as stable and the hooks
page calls `codex_hooks` a deprecated alias. This spike does not change that production behavior.

Loose-file validation remains:

```bash
codex -C <generated-project> debug prompt-input "test" | grep <generated-skill>
CODEX_HOME=<generated>/.codex codex mcp list
```

#### Plugin/package contract

Official sources checked on 2026-07-13:

- [Codex changelog](https://developers.openai.com/codex/changelog) — the 2026-03-25 entry
  announces plugins across the app, CLI, and IDE extensions, packaging skills, app integrations,
  and MCP server configuration. The same changelog listed newer CLI releases than the locally
  tested 0.142.3, so all runtime observations below are version-scoped.
- [Plugins](https://learn.chatgpt.com/docs/plugins) — install/use/remove behavior and bundled
  skills, connectors, MCP servers, and hooks.
- [Build plugins](https://learn.chatgpt.com/docs/build-plugins) — required
  `.codex-plugin/plugin.json`, marketplace schema and locations, local/Git/npm sources, cache,
  config toggles, skills, hooks, apps, and MCP package fields.
- [Build skills](https://learn.chatgpt.com/docs/build-skills) — skill layout, discovery, and
  `[[skills.config]]` enable/disable entries.
- [Hooks](https://learn.chatgpt.com/docs/hooks) — hook files, stable `hooks` flag, plugin hook
  trust, events, and `PLUGIN_ROOT`/`PLUGIN_DATA`.
- [Developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli) — CLI global
  flags, including `--strict-config`, `--enable`, and `--disable`.
- [Submit plugins](https://learn.chatgpt.com/docs/submit-plugins) — public submission supports
  skills-only, MCP-backed app, and combined packages; publication validation is portal-based.
- [Codex `plugin-json-spec.md`](https://github.com/openai/codex/blob/bbe93d3e5f22202362cac87e7e9dc755d8706a8a/codex-rs/skills/src/assets/samples/plugin-creator/references/plugin-json-spec.md)
  at repository commit `bbe93d3e5f22202362cac87e7e9dc755d8706a8a` — built-in creator reference
  for manifest and marketplace fields. Its validator note rejects `hooks`, while current public
  build and hooks pages accept that field; the current pages and successful CLI ingestion are the
  evidence used for this fixture.

Evidence classification:

| Class | Evidence and implication |
|---|---|
| Documented stable | `plugins`, `plugin_sharing`, and `hooks` report stage `stable` and effective `true`. Public docs define the plugin manifest, marketplace, local/Git/npm sources, cache path, plugin toggle, skills, hooks, MCP servers, apps, install, and removal. |
| Experimental | The fixture and probe in this repository are explicitly experimental. Upstream `remote_plugin` reports `under development` and `false`; it is outside the proposed local/Git/npm generation contract. |
| Undocumented/version-specific | The public build page documents marketplace CLI commands but not the full `plugin add/list/remove` JSON contract. Their 0.142.3 `--help` and observed JSON are version-specific evidence. No `codex plugin validate` command exists, and `--strict-config` is rejected for `codex plugin`. |
| Inferred | A successful `plugin add` proves that this fixture is accepted and copied, not that every public manifest rule was checked. Cache deletion on `plugin remove` and skill absence while the plugin is disabled were observed in the isolated probe. |

Exact help and feature capture commands:

```bash
/opt/homebrew/bin/codex --version
/opt/homebrew/bin/codex --help
/opt/homebrew/bin/codex plugin --help
/opt/homebrew/bin/codex plugin add --help
/opt/homebrew/bin/codex plugin list --help
/opt/homebrew/bin/codex plugin remove --help
/opt/homebrew/bin/codex plugin marketplace --help
/opt/homebrew/bin/codex plugin marketplace add --help
/opt/homebrew/bin/codex plugin marketplace list --help
/opt/homebrew/bin/codex plugin marketplace upgrade --help
/opt/homebrew/bin/codex plugin marketplace remove --help
/opt/homebrew/bin/codex doctor --help
/opt/homebrew/bin/codex debug --help
/opt/homebrew/bin/codex features list
```

The auth-free lifecycle probe uses fresh temporary values for both `HOME` and `CODEX_HOME`, removes
known API credential variables from its child environment, and runs:

```bash
uv run python tests/probes/probe_codex_plugin_package.py

codex plugin marketplace list --json
codex plugin marketplace add <fixture-root> --json
codex plugin list --available --json
codex plugin add experimental-package@ai-config-experimental --json
codex plugin list --json
codex -C <fixture-root> debug prompt-input probe
# edit only temporary config: [plugins."experimental-package@ai-config-experimental"] enabled=false
codex plugin list --json
codex -C <fixture-root> debug prompt-input probe
# restore enabled=true in the same temporary config
codex --strict-config plugin list --json
codex --strict-config doctor --json
codex plugin remove experimental-package@ai-config-experimental --json
codex plugin marketplace remove ai-config-experimental --json
```

Observed behavior on 0.142.3:

- Marketplace add/list and plugin available/add/list/remove succeeded without authentication.
- Install copied the manifest, one skill, and one hook file to
  `$CODEX_HOME/plugins/cache/ai-config-experimental/experimental-package/0.1.0/` and wrote an
  enabled plugin table to temporary `config.toml`.
- `debug prompt-input` found `experimental-package:hello` when enabled, omitted it when disabled,
  and found it again after re-enabling. The probe does not trust or execute the bundled hook.
- Remove deleted the cached version and plugin config; marketplace remove deleted its config.
- `codex --strict-config doctor --json` reported `config.load` as `ok` even though the overall
  auth-free doctor result can fail its separate credential check. Strict config cannot be applied
  directly to plugin subcommands. There is no public auth-free standalone plugin validator.
- Public package fields cover skills, hooks, MCP servers, apps/connectors, and npm-backed package
  sources. The minimal fixture uses one skill and one hook. MCP/app/npm behavior is documented but
  not exercised because the bounded proof needs no server, credentials, network package, or app ID.

**Recommendation (issue option 2): add a future opt-in `codex-plugin` target.** Keep `codex` as the
loose-file default. A separate target matches the package's install/cache lifecycle and avoids
mixing immutable bundle output with the existing shared-config merge contract.

Implementation-ready follow-up:

1. Add a package emitter behind a new opt-in target only when implementation work is authorized.
   Reuse `PluginIR` for identity, skills, hooks, and MCP servers; emit commands as package skills or
   diagnose them, and keep agents/LSP unsupported. Add only metadata fields required by a chosen
   publishing tier rather than copying the whole public listing schema into IR.
2. Emit one self-contained plugin root plus an optional repo marketplace entry. Do not merge package
   content into `.codex/config.toml`; installed enable state and plugin-scoped MCP policy remain
   Codex-owned user state.
3. Add a package validator for manifest paths, names, semver, skill files, hook JSON, MCP JSON, and
   marketplace references. Keep it separate from `CodexOutputValidator`. Report package files and
   mappings through the existing `ConversionReport` model.
4. Register the target across CLI/config/sync only after unit coverage and this isolated probe pass.
   Add Docker coverage pinned to a known Codex version. Preserve independent per-target reports and
   verify that selecting `codex-plugin` never changes loose `codex`, Cursor, OpenCode, or Pi output.

### Pi

- Pi-native skills use `.pi/skills/` for project scope and `.pi/agent/skills/` for user-scope output roots.
- Pi-native prompt templates use `.pi/prompts/` and `.pi/agent/prompts/`.
- Claude hooks are emulated via generated TypeScript extensions under `.pi/extensions/` or `.pi/agent/extensions/`.
- Pi RPC `get_commands` is the deterministic auth-free check for skill command registration.
- `pi --extension <generated.ts>` can validate extension loading and early hook execution without successful model completion.

Validation patterns:

```bash
PI_CODING_AGENT_DIR=<tmp-agent> pi --mode rpc --offline --no-session --no-extensions ...
# send {"id":"skills","type":"get_commands"}; assert skill:<name>

PI_OFFLINE=1 pi --offline --extension <generated-extension> ... || true
# assert marker file from hook command
```

### Cursor

- Cursor output currently includes `.cursor/skills/`, `.cursor/mcp.json`, and `.cursor/hooks.json`.
- `cursor-agent mcp list` is the available real-tool MCP check.
- Auth-free CLI skill listing may not be stable; keep file-shape validation and update this baseline if a better introspection command appears.

### OpenCode

- OpenCode exposes useful debug surfaces: `opencode debug skill`, `opencode debug config`, and `opencode debug paths`.
- Use these before relying on generated file shape alone.

## Update checklist

When this baseline is refreshed:

1. Update `Last checked`.
2. Record version command outputs.
3. Update each target's assumptions.
4. Link or mention upstream docs/release notes consulted.
5. Add/adjust E2E tests for any changed runtime behavior.
6. Run the `ai-config-target-refresh` skill workflow.
