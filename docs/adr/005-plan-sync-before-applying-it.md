# Plan sync before applying it

Status: Accepted
Date: 2026-07-29

## Context

Sync spans external Claude state, plugin sources, generated artifacts, target
lifecycle commands, caches, and ownership ledgers. Interleaving observation,
decisions, and mutation made dry-run parity, stale-input detection, and
partial-progress reporting difficult to establish.

[PR #26](https://github.com/safurrier/ai-config/pull/26), merged as
`693442307dbd54b1c8e0f9bb4a17937f98539a2f`, introduced the current phase
boundary and characterization coverage. The data contracts live in
`src/ai_config/sync_pipeline.py`; observation and execution are separated in
`sync_orchestration.py` and `sync_conversion.py`.

## Decision

Run normal sync as explicit observation, immutable snapshot construction,
deterministic planning, validation, apply, and reporting phases. Dry-run and
real execution consume the same typed, ordered `SyncPlan`.

Planning is mutation-free. Apply validates its preconditions and executes the
materialized plan without rebuilding decisions. Target lifecycle code retains
authority for target-specific checks and actions but cannot bypass the plan as
the authorization boundary.

## Consequences

Dry-run describes the actions that real execution would consume, and planning
can be tested without external mutation. Plans carry emitted data, ownership
snapshots, and checkpoints, so they are larger than simple action lists. A real
`--fresh` cache clear remains outside the pure transform because it must happen
before observation; fresh dry-run remains mutation-free.
