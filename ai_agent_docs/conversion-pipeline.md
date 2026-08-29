# Sync and conversion pipelines

## Sync orchestration

`ai-config sync` separates planning from mutation:

```text
fresh cache clear (real `--fresh` only)
    -> observe Claude, cache, ownership, and source state
    -> build immutable RuntimeSnapshot and SourceBatch records
    -> plan_sync(DesiredState, RuntimeSnapshot, SourceBatch)
    -> validate blocking diagnostics and target preflight
    -> apply_sync_plan(SyncPlan)
    -> report ExecutionReport and commit ownership/cache checkpoints
```

`sync_pipeline.py` owns frozen records, the pure `plan_sync()` transform, and plan validation.
`sync_orchestration.py` observes state and runs the narrow executor. `sync_conversion.py` plans and
applies typed conversion work. It keeps target preflight and lifecycle logic. `sync_state.py` observes
cache, source, output-root, and ownership state. `operations.py` exposes stable command entry points.

A `SyncPlan` records public actions by phase, blocking diagnostics, ownership-ledger snapshots, and a
target-specific `ConversionPlan`. The conversion plan records candidates, digests, package specs,
retained identities, retiring roots, Pi desired files, emitted bytes, target actions, cache intent, and
checkpoints. Marketplace actions run before their plugin actions. Conversion actions run after them.
Before the normal-action stage, the executor checks Claude, cache, ownership, and source preconditions. It
checks conversion preconditions again before the conversion stage. It reports each completed or failed action.
A conversion error stops later cache and ownership checkpoints.

Planning never writes the filesystem or cache. It never cleans up or calls a tool that changes state.
Conversion observation can parse sources, emit artifacts in memory, and request Codex and Pi lifecycle
dry runs. The plan holds those decisions. CLI dry run renders that same plan, and real execution applies
it. Target lifecycle code can check current preconditions during apply. The materialized action sequence
still authorizes the work. The conversion executor accepts only `ConversionPlan`. It never parses
sources, emits files, chooses cache state, retains sources, finds output roots, or plans conversion.

`--fresh` remains outside the pure transform. During real sync, ai-config clears Claude's cache before
observation because the clear affects the observed state. A fresh dry run leaves the cache intact and does not mutate state.

Unavailable configured sources stay separate from resolved sources. Sync reports a non-blocking
conversion error for each one. Independent marketplace and plugin actions can finish. Sync then skips
conversion mutation and retains prior proven-owned state. Disabled or removed sources can ask for cleanup
only through Codex or Pi ownership ledgers. Cache version 9 invalidates content entries but retains
validated Codex and Pi output roots. Cleanup can therefore find prior custom roots. Ownership formats stay the same.

## Plugin conversion

ai-config converts Claude plugins through a target-neutral intermediate representation (IR):

```text
Claude plugin directory -> contained source reader -> ClaudePluginParser -> PluginIR
                        -> pure skill projection -> target emitter -> EmitResult/report
```

## Ownership boundaries

`PluginIR` holds identity, skills, commands, hooks, Model Context Protocol (MCP) servers, agents,
Language Server Protocol (LSP) servers, source paths, and diagnostics. Skill include records are
immutable. They hold the plugin-relative source path, the derived `_shared/` path, captured bytes, and
executable mode. Projection and reports hold rewrite counts and duplicated bytes. Emitters never change
the IR or reopen include sources. Each target gets an independent `EmitResult`, mappings, diagnostics,
and output paths.

`source_safety.py` controls conversion source reads. It validates portable plugin-relative paths. It
rejects final and in-root ancestor symlinks, traversal, special files, and resolved escapes before a read.
Manifests, components, skill assets, includes, Codex support files, and native target files use this
descriptor-relative, no-follow boundary. `compute_plugin_hash()` walks the same regular-file universe.
It permits one metadata-only exception: the sibling `CLAUDE.md -> AGENTS.md` context mirror when its
target opens as a no-follow regular file. The digest includes the link path and target text without
following the link. Every other symlink fails. Sync rehashes this universe before conversion to check for
a stale plan. Hashing and conversion remain separate contained passes. Standalone `convert` does not
compute a digest. Cache version 9 keeps validated Codex and Pi output roots while invalidating old
content signatures.

`skill_projection.py` is pure and shared by all four emitters. It rewrites only declared exact
`${CLAUDE_PLUGIN_ROOT}/<path>` references in instruction Markdown. Each becomes a skill-root-relative
`_shared/<path>` reference, even from nested Markdown. It copies captured bytes to each consumer. It
blocks undeclared placeholders and projected collisions. It returns evidence for each copy. A transitive dependency can have zero direct rewrites.

| Emitter | Primary output | Shared-state behavior |
|---|---|---|
| `CodexEmitter` | `.ai-config/codex/marketplaces/<name>/` package + marketplace | Emits owned sources only; sync uses Codex CLI for install, cache, and config. |
| `CursorEmitter` | `.cursor/` plus MCP/hooks JSON | Writes target files. |
| `OpenCodeEmitter` | `.opencode/`, `opencode.json`, `opencode.lsp.json` | Writes target files. |
| `PiEmitter` | project `.pi/` or user `.pi/agent/` | Writes target files and extensions. |

`EmitResult` holds emitted files, component mappings, diagnostics, include evidence, and proven-owned
cleanup paths. `write_to()` removes only explicit owned cleanup paths before it writes. Native files in
`targets/<target>/` override generated files at the target's natural root. Pi's desired-file ledger owns
included copies. Codex stores them in its owned package. Cursor and OpenCode lack a provenance ledger,
so they add no cleanup paths for removed includes.

## Codex package and lifecycle seam

`CodexEmitter` emits one marketplace per package. It avoids a global marketplace-file merge:

```text
.ai-config/codex/marketplaces/ai-config-<plugin>/
├── .agents/plugins/marketplace.json
└── plugins/<plugin>/
    ├── .codex-plugin/plugin.json
    ├── skills/**/SKILL.md
    └── hooks/hooks.json
```

`converters/codex_package.py` names packages and paths. The emitter never writes `CODEX_HOME`.
`codex_lifecycle.py` reads ai-config's ownership file and calls `adapters/codex.py` for marketplace and
plugin add, list, and remove operations. Codex controls cache and enablement.

Lifecycle convergence receives desired package specs and the sources that changed:

- A new package adds its marketplace and installs its plugin.
- A changed or disabled managed package removes it, then adds it through the Codex CLI.
- An unchanged package makes no mutation.
- A removed source removes only its recorded plugin and marketplace. It then deletes only its generated marketplace root.
- An unrelated marketplace name collision fails closed.
- A command failure reports the stage, exact command, output, and remediation.

Conversion cache versioning invalidates old loose-output signatures. The ownership file stays separate
from the content hash cache because it defines the destructive boundary.

## Core sync rules

Each sync stage has one fixed plan. The plan says what may change. Apply only that plan. When a remote source needs installation, apply its prerequisite projection, re-observe, and build a separate plan for the conversion stage.

Read the source before a change. Check its path before a read. Keep all reads in the source boundary.
Keep each target apart. One target must not change another target's files. Keep each result separate.

Write only owned files. Keep proof before any delete. Do not guess ownership from a path.

Keep dry runs safe. A dry run shows the plan but changes no state. A real run checks the plan before it acts.

Keep errors clear. Name the failed stage. Show the command, its output, and a fix. Stop later checkpoints
when conversion fails.

Use small steps. First, read state. Next, make the plan. Then, check the plan. Last, apply it. Do not
mix these steps. A plan can be read and saved. It must not change while it runs.

Use safe paths. A path must stay in the plugin root. A link must pass the source check. A file must be a
safe regular file. Read its bytes once. Pass those bytes to the target. Do not open the source again.

Use clear target work. Each target gets its own result. Each result lists its files and warnings. A target
may write its own output. It may not write a peer target's output. A cleanup step needs a known owned
path. If proof is not present, leave the path in place.

Use a real dry run. It shows the observable first stage in the same order as a real run. For a deferred source, it reports diagnostics instead of guessing a later conversion plan. It does not clear cache, write files, call a live lifecycle tool, or delete data. A real run checks the same state before each stage.

## Fidelity and reports

Each component has its own mapping:

- Native: package skill and package or marketplace structure.
- Transform: command-to-skill without variables, package hooks, and package MCP.
- Fallback or degraded: command variables and partial hook semantics.
- Unsupported: agents, LSP, and hook handlers or events without a Codex package equivalent.

Reports and dry runs list package paths. Sync dry runs also list planned Codex marketplace and plugin
lifecycle actions without calling Codex.

## Validation

`CodexOutputValidator` checks marketplace JSON, local source containment, manifest identity and version,
package skill frontmatter, hook structure and root variables, and MCP declarations. It reports possible
legacy loose output but never deletes it.

`tests/probes/probe_codex_plugin_package.py` provides real runtime proof. It covers generation, doctor
validation, CLI installation, enabled and disabled discovery, hook and MCP ingestion, update,
idempotence, removal, and unrelated-state preservation in isolated homes.
