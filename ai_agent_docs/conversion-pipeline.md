# Sync and Conversion Pipelines

## Sync orchestration

`ai-config sync` uses an explicit data boundary before normal mutation:

```text
fresh cache clear (real `--fresh` only)
    -> observe Claude, cache, ownership, and source state
    -> build immutable RuntimeSnapshot and SourceBatch records
    -> plan_sync(DesiredState, RuntimeSnapshot, SourceBatch)
    -> validate blocking diagnostics and target preflight
    -> apply_sync_plan(SyncPlan)
    -> report ExecutionReport and commit ownership/cache checkpoints
```

`sync_pipeline.py` owns the frozen, tool-independent records, the pure `plan_sync()` transform, and
structural plan validation. `sync_orchestration.py` owns observation and the narrow executor;
`sync_conversion.py` exposes separate typed conversion planning and application boundaries while
retaining target-specific preflight and lifecycle logic; `sync_state.py` owns cache, source, output-root,
and ownership observation helpers below orchestration; `operations.py` retains only stable command
entry points. A `SyncPlan` contains phase-tagged, ordered public actions, blocking diagnostics, exact
ownership-ledger snapshots, and a target-specific `ConversionPlan`. That conversion record carries
resolved candidates and digests, package specifications, retained identities, retiring roots, Pi
desired files, emitted bytes, target action batches, cache update intent, and planned checkpoints.
Marketplace actions always precede dependent plugin actions; conversion actions follow
them. Before any normal action, the executor verifies the observed Claude, cache, ownership, and
source preconditions. It reports completed and failed actions explicitly and does not authorize cache
or ownership checkpoints after a conversion error.

Planning never performs filesystem writes, cache writes, destructive cleanup, or state-changing tool
calls. Conversion observation may parse sources, emit artifacts in memory, and ask the Codex and Pi
lifecycle authorities for dry-run actions. Those decisions are then included in the same materialized
plan used by CLI dry-run rendering and real execution. During apply, target-specific lifecycle code
may validate current preconditions, but the materialized action sequence remains the authorization
boundary. The conversion executor accepts only `ConversionPlan`; it never invokes source parsers,
emitters, cache-choice logic, retention logic, output-root discovery, or conversion planning.

`--fresh` is intentionally outside the pure transform. For a real sync, Claude's cache is cleared
before observation because that ordering changes what can be observed. A fresh dry-run does not clear
the cache and remains mutation-free.

Unavailable configured sources are represented separately from resolved sources. Their diagnostic is
materialized as a reported (non-blocking) conversion error, so earlier independent marketplace and
plugin actions retain historical progress while conversion mutation is skipped and prior proven-owned
state is retained. Disabled or removed sources can request cleanup only through the existing Codex or
Pi ownership ledgers. Cache and ownership formats are unchanged.

## Plugin conversion

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
