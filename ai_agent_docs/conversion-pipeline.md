# Conversion Pipeline

ai-config converts Claude plugins through a target-independent IR:

```text
Claude plugin directory -> ClaudePluginParser -> PluginIR -> target emitter -> EmitResult/report
```

## Ownership boundaries

`PluginIR` carries identity, skills, commands, hooks, MCP servers, agents, LSP servers, source paths,
and diagnostics. Emitters do not mutate the IR. Each target owns an independent `EmitResult`,
component mappings, diagnostics, and output paths.

| Emitter | Primary output | Shared-state behavior |
|---|---|---|
| `CodexEmitter` | `.ai-config/codex/marketplaces/<name>/` package + marketplace | emits owned sources only; sync uses Codex CLI for install/cache/config |
| `CursorEmitter` | `.cursor/` plus MCP/hooks JSON | writes target files |
| `OpenCodeEmitter` | `.opencode/`, `opencode.json`, `opencode.lsp.json` | writes target files |
| `PiEmitter` | project `.pi/` or user `.pi/agent/` | writes target files/extensions |

`EmitResult` contains emitted files, independent component mappings, diagnostics, and proven-owned
cleanup paths. `write_to()` removes only explicit owned cleanup paths before writing. Target-native
files under `targets/<target>/` override generated files at the target's natural root.

## Codex package and lifecycle seam

`CodexEmitter` emits one marketplace per package so conversion is deterministic and does not need to
merge a global marketplace file:

```text
.ai-config/codex/marketplaces/ai-config-<plugin>/
├── .agents/plugins/marketplace.json
└── plugins/<plugin>/
    ├── .codex-plugin/plugin.json
    ├── skills/**/SKILL.md
    └── hooks/hooks.json
```

`converters/codex_package.py` is the shared naming/path source of truth. The emitter never writes
`CODEX_HOME`. `codex_lifecycle.py` reads ai-config's ownership file and delegates marketplace/plugin
add/list/remove to `adapters/codex.py`. Codex remains responsible for cache and enablement.

Lifecycle convergence receives all desired package specs plus the set whose source changed:

- new package: add marketplace, install plugin;
- changed or disabled managed package: remove/add through Codex CLI;
- unchanged package: no mutation;
- removed source: remove only the recorded plugin and marketplace, then delete only its generated
  marketplace root;
- unrelated marketplace name collision: fail closed;
- command failure: include stage, exact command, output, and remediation.

Conversion cache versioning invalidates old loose-output signatures. The ownership file is separate
from the content hash cache because it defines the destructive boundary.

## Fidelity and reports

Each component produces its own mapping:

- native: package skill, package/marketplace structure;
- transform: command-to-skill without variables, package hooks, package MCP;
- fallback/degraded: command variables, partial hook semantics;
- unsupported: agents, LSP, or hook handlers/events without a Codex package equivalent.

Reports and dry runs list package paths. Sync dry runs additionally list planned Codex marketplace
and plugin lifecycle actions without invoking Codex.

## Validation

`CodexOutputValidator` validates marketplace JSON, local source containment, manifest identity and
version, package skill frontmatter, hook structure/root variables, and MCP declarations. It also
reports possible legacy loose output without deleting it.

Real runtime proof uses `tests/probes/probe_codex_plugin_package.py`: generation, doctor validation,
CLI installation, enabled/disabled discovery, hook/MCP ingestion, update, idempotence, removal, and
unrelated-state preservation in isolated homes.
