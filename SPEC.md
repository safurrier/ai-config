# Specification

## Summary

ai-config manages Claude Code plugin marketplaces and installs. It also converts
installed or local Claude Code plugins into a target-neutral intermediate
representation, or IR. It emits compatible artifacts for Codex, Cursor, OpenCode,
and Pi.

## Goals / Non-Goals

### Goals

- One versioned YAML document for configured Claude Code marketplaces and plugins.
- Target artifacts with explicit fidelity diagnostics.
- Dry runs, verification, ownership, and cleanup that are visible and safe to retry.

### Non-goals

- Lossless equivalence when a target lacks a Claude component or semantic.
- Treating generated output as user-authored source.
- Claiming ownership of pre-existing files.
- Independent non-Claude top-level targets in config version 1.

## Requirements

- **Config.** The system MUST accept config version 1. Its top-level target type
  MUST be `claude`. It MUST validate marketplace, plugin, scope, and conversion
  settings before mutation.
- **Sync plan.** `sync` MUST observe runtime and source state. It MUST create an
  ordered plan, validate its preconditions, and apply only that plan. It MAY cross
  one explicit prerequisite barrier. First, it applies an immutable Claude-only
  plan. Then it observes state once more and applies a separately validated
  conversion-only plan. It MUST NOT sync until quiet or derive replacement actions
  during apply.
- **Local source.** A configured local marketplace MUST remain the conversion
  source authority after Claude installation. A missing or unsafe local source MUST
  remain unavailable. It MUST NOT fall back to Claude's installed cache. Remote and
  marketplace-less sources MAY use safely observed installed paths.
- **Dry run.** A dry run MUST avoid state-changing runtime calls, filesystem
  writes, cache writes, and ownership writes. The only exception is an explicitly
  requested `convert --report PATH` artifact.
- **Conversion.** The pipeline MUST parse a Claude Code plugin into a
  target-neutral IR before an independent target emitter runs.
- **Source reads.** Every source byte used for conversion MUST pass a fail-closed
  plugin-root containment check. It MUST NOT read or emit absolute paths,
  traversing paths, resolved escapes, final or in-root ancestor symlinks, or
  non-regular files. Sync hashing MAY retain metadata for the exact repository
  context mirror `CLAUDE.md -> AGENTS.md`. Both entries must be siblings, and the
  target must be a no-follow regular file. Hashing MUST NOT read through that link.
  Every other symlink shape MUST make the source unreadable. Sync MUST hash the
  complete safely readable tree and validated mirror metadata. It MUST recheck that
  digest before conversion. Standalone `convert` skips source digest computation.
  Digesting and conversion remain separate filesystem steps.
- **Shared files.** A skill MAY declare exact plugin-root-relative regular files in
  `x-ai-config-includes`. Each consuming generated skill MUST receive byte-preserved
  copies under `_shared/<plugin-relative-path>`. Each generated skill MUST remain
  self-contained.
- **Generated instructions.** Generated instruction Markdown MUST rewrite only
  declared exact `${CLAUDE_PLUGIN_ROOT}/<path>` references. Generated `SKILL.md`
  MUST omit build metadata. An undeclared root reference that remains MUST block
  that component.
- **Diagnostics.** Every conversion MUST classify each component as native,
  transformed, degraded, unsupported, or otherwise diagnosed by its target emitter.
- **Cleanup.** The system MUST refuse destructive cleanup unless target-specific
  evidence proves ownership of the exact state to remove.
- **Pi.** Pi reconciliation MUST preserve unowned collisions and locally modified
  owned output. It MUST NOT overwrite or delete either.
- **Codex.** Codex reconciliation MUST limit generated package writes and cleanup
  to ai-config reserved package roots and ownership records. The Codex CLI owns the
  installed plugin and marketplace lifecycle.
- **Cursor and OpenCode.** Their conversion MUST remain path-contained. Callers
  MUST NOT treat path containment as proof that ai-config owns a pre-existing file.
- **Status.** `status` MUST report installed state without config. Config drift
  comparison MUST occur only when a caller provides config or requests verification.
- **Update.** `update` MUST work on named installed plugins or all installed
  plugins. It MUST NOT imply config reconciliation.
- **Cache.** The conversion cache MUST use configured plugin selectors and
  conversion settings as logical identity. It MUST retain source provenance,
  physical path, source digest, and generated Codex digest as cache-hit
  observations. Cache migration MUST preserve only validated tracked output roots
  needed for ownership cleanup.
- **Verification.** `sync --verify` MUST run its read-only verification plan only
  after every requested apply stage succeeds. An intentionally empty isolated
  `CODEX_HOME` is a valid initial state.
- **No-op runs.** The system SHOULD make unchanged sync and conversion runs no-ops.
- **Scope.** A caller MAY request project or user conversion scope. A caller MAY
  provide an explicit output directory.

## Interfaces & Contracts

- `.ai-config/config.yaml` or `.ai-config/config.yml`: project configuration.
  User configuration falls back to the matching file under `~/.ai-config/`.
- `ai-config init`: creates a validated configuration through an interactive wizard.
- `ai-config sync [--dry-run] [--fresh] [--verify] [--json]`: reconciles the
  selected config and optional configured conversion targets.
- `ai-config status [--config PATH] [--verify] [--json]`: observes installed state.
  Config-aware lifecycle drift is opt-in.
- `ai-config update [PLUGIN ... | --all] [--fresh]`: updates installed Claude
  plugins without config reconciliation.
- `ai-config convert PLUGIN_PATH --target TARGET`: converts one standalone Claude
  plugin and reports mappings and diagnostics.
- `ai-config doctor [--target TARGET] [OUTPUT_DIR]`: validates config or plugin
  inputs, or emitted target artifacts.
- `ai-config watch`: watches plugin and config inputs, then invokes sync. Claude
  Code still needs a session restart to reload plugin changes.
- Python package boundaries: `config.py` parses desired configuration. `sync_orchestration.py` observes and
  executes. `sync_pipeline.py` owns immutable plans. `converters/` parses IR and
  emits target output. Lifecycle and ownership modules own destructive boundaries.

## Invariants

- **Planning.** Planning stays deterministic for an equivalent desired state,
  runtime snapshot, source batch, and conversion input.
- **Plan use.** The same materialized sync plan authorizes dry-run rendering and
  real execution.
- **Emitters.** Target emitters do not mutate the parsed plugin IR or another
  target's result.
- **Includes.** Shared include records in IR are immutable. One pure target-neutral
  projection supplies all target emitters without rereading include sources.
- **Action order.** Marketplace actions precede dependent Claude plugin actions.
  Conversion actions follow them. A staged conversion plan has no marketplace or
  plugin action. Unmet prerequisites block that stage.
- **Failed checks.** Failed or stale preconditions prevent the affected mutation.
  They also prevent unsupported cache or ownership checkpoints.
- **Unavailable sources.** Missing or temporary sources do not authorize deletion
  of their prior proven-owned output.
- **Cleanup roots.** Generated Codex and Pi cleanup never crosses the validated
  ownership root.
- **Overrides.** Target-native files override only an exact generated file path in
  their selected target output after path and symlink validation. File and directory
  conflicts fail. The system rechecks final generated-skill invariants after precedence.
- **Reports.** Reports distinguish completed, failed, skipped, degraded,
  unsupported, and no-op outcomes. They never present partial work as success.
- **Include reports.** They use plugin-relative logical sources. They record the
  consumer, target-relative path, copy count, duplicated bytes, and direct rewrite
  count. Zero rewrites remain valid transitive-dependency evidence.

## Acceptance

- `uv run ruff check src/` and `uv run ty check src/` pass.
- `uv run pytest tests/unit/ -v` passes the unit contract for config parsing,
  planning, conversion, target validation, lifecycle, and ownership behavior.
- `uv run mkdocs build --strict` resolves and renders the public documentation.
- Docker E2E lanes exercise supported tool surfaces. Isolated Codex and Pi probes
  verify real lifecycle behavior without the caller's runtime homes or credentials.
- `sync --dry-run` and the matching first real stage expose the same planned action
  order for unchanged evidence. The system reports an unavailable remote conversion
  as deferred, not speculated, before installation.
- A fresh isolated local-marketplace `sync --force --verify` converges in one run
  without false Codex refresh drift. A fresh remote source uses at most one Claude
  prerequisite apply and one conversion apply.
- Repeated sync converges without mutation. Tamper and removal tests prove cleanup
  stays within recorded target ownership.
- Shared-resource fixtures prove that two consumers receive independent byte-exact
  copies for all four emitters. They retain no build metadata or unresolved Claude
  root placeholder.
