# Project evolution

ai-config evolved from a Claude-only declarative installer into a cross-tool
conversion and reconciliation system. The phases below record why the current
boundaries exist; individual feature changes remain in the changelog.

## Declarative Claude management

The initial release made a YAML file authoritative for Claude marketplaces and
plugins. `init`, `sync`, `status`, `update`, `watch`, `doctor`, and plugin
scaffolding established the desired-vs-installed model that still anchors the
CLI. PyPI publishing and Docker E2E followed so the tool could be installed and
tested outside one workstation.

Evidence: initial commit `499cb2b612d26909c6787775401b76e806384310`,
[PR #1](https://github.com/safurrier/ai-config/pull/1), and
[PR #2](https://github.com/safurrier/ai-config/pull/2).

## One source, multiple targets

[PR #3](https://github.com/safurrier/ai-config/pull/3) added the cross-tool
pipeline. Claude plugin bundles remained the authoring source, while a typed IR
separated parsing from Codex, Cursor, and OpenCode emitters. Fidelity statuses
made unsupported and degraded mappings visible. Pi joined through the same seam
in [PR #8](https://github.com/safurrier/ai-config/pull/8).

The init rewrite and environment-variable path support in
[PR #7](https://github.com/safurrier/ai-config/pull/7) made the declarative
configuration portable across machines. Target-native overrides in
[PR #16](https://github.com/safurrier/ai-config/pull/16) added an escape hatch
for target-specific behavior without replacing the canonical source or IR.

## From emitted files to target lifecycles

Early targets mostly wrote loose files. Runtime audits then showed that target
discovery paths and capabilities change independently: Pi user files moved
under `~/.pi/agent/`, Codex discovery and hook/MCP paths changed, and shared
configuration needed merge behavior.

[PR #17](https://github.com/safurrier/ai-config/pull/17) evaluated Codex's new
package surface. [PR #19](https://github.com/safurrier/ai-config/pull/19) then
replaced loose Codex output with native packages and an ownership-aware CLI
lifecycle. This was a deliberate breaking change, not a new parallel target.

## Proven ownership before cleanup

Native lifecycle introduced a sharper safety question: absence from desired
state is not proof that a runtime path belongs to ai-config. Codex therefore
records package and marketplace identity. After stale loose Pi files were
observed, [PR #24](https://github.com/safurrier/ai-config/pull/24) added
per-file source, path, digest, mode, and pending-transaction evidence.

Historical unowned output remains a human cleanup decision. Cursor and OpenCode
remain path-contained but do not claim the stronger ledger contract.

## Plan before mutation

As sync accumulated Claude state, conversion, target CLI actions, caches, and
ownership checkpoints, interleaved decision-making made dry-run parity and
partial failure hard to reason about. [PR #26](https://github.com/safurrier/ai-config/pull/26)
reframed sync as observation, immutable snapshot, deterministic plan,
validation, apply, and reporting.

The current system therefore has two durable internal seams: Parse → IR → Emit
for conversion, and Observe → Plan → Apply for reconciliation. The former
separates source semantics from target representation; the latter separates
evidence and authorization from mutation.

## Decision timeline

| Effective date | Lasting decision | Current record |
|---|---|---|
| 2026-02-12 | All targets receive one normalized IR | [ADR 002](../adr/002-normalize-conversion-through-a-target-independent-ir.md) |
| 2026-07-17 | Codex uses native plugin packages rather than loose output | [ADR 003](../adr/003-use-native-codex-plugin-packages.md) |
| 2026-07-26 | Cleanup requires durable ownership proof | [ADR 004](../adr/004-require-proven-ownership-before-generated-output-cleanup.md) |
| 2026-07-29 | Sync materializes a plan before normal mutation | [ADR 005](../adr/005-plan-sync-before-applying-it.md) |
| 2026-08-01 | Ratify Claude plugins as the canonical conversion source; implementation began 2026-02-12 | [ADR 001](../adr/001-use-claude-plugins-as-the-canonical-source.md) |
