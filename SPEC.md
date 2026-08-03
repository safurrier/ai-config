# ai-config specification

## Summary

ai-config is a declarative manager for Claude Code plugin marketplaces and installations. It can also parse installed or local Claude Code plugins into a target-neutral intermediate representation and emit compatible artifacts for Codex, Cursor, OpenCode, and Pi.

## Goals / Non-Goals

- Goal: converge configured Claude Code marketplaces and plugins through one versioned YAML document.
- Goal: convert one Claude Code plugin source into target-specific artifacts with explicit fidelity diagnostics.
- Goal: make dry-run, verification, ownership, and cleanup behavior inspectable and safe to retry.
- Non-goal: provide lossless equivalence where a target lacks a Claude component or semantic.
- Non-goal: treat generated output as user-authored source or claim ownership of pre-existing files.
- Non-goal: configure non-Claude runtimes as independent top-level targets in config version 1.

## Requirements

- The system MUST accept config version 1 with `claude` as its top-level target type and validate marketplace, plugin, scope, and conversion settings before mutation.
- `sync` MUST observe runtime and source state, create an ordered plan, validate its preconditions, and apply only that plan.
- A dry run MUST avoid state-changing runtime calls, filesystem writes, cache writes, and ownership writes.
- The conversion pipeline MUST parse a Claude Code plugin into a target-neutral IR before invoking an independent target emitter.
- Every conversion MUST classify each component as native, transformed, degraded, unsupported, or otherwise diagnosed by the target emitter.
- The system MUST refuse destructive cleanup unless target-specific evidence proves ownership of the exact state being removed.
- Pi reconciliation MUST preserve unowned collisions and locally modified owned output rather than overwrite or delete them.
- Codex reconciliation MUST limit generated package writes and cleanup to ai-config's reserved package roots and ownership records while delegating installed plugin and marketplace lifecycle to the Codex CLI.
- Cursor and OpenCode conversion MUST remain path-contained, but callers MUST NOT interpret path containment as proof that a pre-existing file is ai-config-owned.
- `status` MUST report installed state without requiring config; config drift comparison MUST occur only when config or verification is requested.
- `update` MUST operate on named installed plugins or all installed plugins and MUST NOT imply config reconciliation.
- The system SHOULD make unchanged sync and conversion runs no-ops.
- A caller MAY request project or user conversion scope and MAY provide an explicit output directory.

## Interfaces & Contracts

- `.ai-config/config.yaml` or `.ai-config/config.yml` — project configuration; user configuration falls back to the equivalent files under `~/.ai-config/`.
- `ai-config init` — creates a validated configuration through an interactive wizard.
- `ai-config sync [--dry-run] [--fresh] [--verify] [--json]` — reconciles the selected config and optionally its configured conversion targets.
- `ai-config status [--config PATH] [--verify] [--json]` — observes installed state; config-aware lifecycle drift is opt-in.
- `ai-config update [PLUGIN ... | --all] [--fresh]` — updates installed Claude plugins independently of config reconciliation.
- `ai-config convert PLUGIN_PATH --target TARGET` — runs standalone Claude-plugin conversion and reports mappings and diagnostics.
- `ai-config doctor [--target TARGET] [OUTPUT_DIR]` — validates config/plugin inputs or emitted target artifacts.
- `ai-config watch` — watches plugin/config inputs and invokes sync; Claude Code still requires a session restart to reload plugin changes.
- Python package boundaries — `config.py` parses desired configuration; `sync_orchestration.py` observes and executes; `sync_pipeline.py` owns immutable plans; `converters/` parses IR and emits target output; target lifecycle and ownership modules own destructive boundaries.

## Invariants

- Planning is deterministic for an equivalent desired state, runtime snapshot, source batch, and conversion input.
- The same materialized sync plan authorizes dry-run rendering and real execution.
- Target emitters do not mutate the parsed plugin IR or another target's result.
- Marketplace actions precede dependent Claude plugin actions, and conversion actions follow them.
- Failed or stale preconditions prevent the affected mutation and prevent unsupported cache or ownership checkpoints.
- Missing or temporarily unavailable sources do not authorize deletion of their prior proven-owned output.
- Generated Codex and Pi cleanup never crosses the validated ownership root.
- Target-native files override generated files only within their selected target output and only after path and symlink validation.
- Reports distinguish completed, failed, skipped, degraded, unsupported, and no-op outcomes rather than presenting partial work as success.

## Acceptance

- `uv run ruff check src/` and `uv run ty check src/` pass.
- `uv run pytest tests/unit/ -v` passes the unit contract for config parsing, planning, conversion, target validation, lifecycle, and ownership behavior.
- `uv run mkdocs build --strict` resolves and renders the public documentation.
- Docker E2E lanes exercise supported tool surfaces, while isolated Codex and Pi probes verify real lifecycle behavior without using the caller's runtime homes or credentials.
- `sync --dry-run` and the corresponding real sync expose the same planned action ordering for unchanged evidence.
- Repeated sync converges without mutation, and tamper/removal tests prove cleanup stays within recorded target ownership.
