# Plan sync before applying it

Status: Accepted
Date: 2026-07-29

## Context

Sync spans external Claude state, plugin sources, generated artifacts, target
lifecycle commands, caches, and ownership ledgers. When observation, decisions,
and mutation were interleaved, dry-run parity and partial-progress reporting
were difficult to establish, and changing state could invalidate later
decisions during the same run.

[PR #26](https://github.com/safurrier/ai-config/pull/26), merged as
`693442307dbd54b1c8e0f9bb4a17937f98539a2f`, introduced the current phase
boundary and characterization tests. The data contracts are in
`src/ai_config/sync_pipeline.py`; observation and execution are separated in
`src/ai_config/sync_orchestration.py` and `src/ai_config/sync_conversion.py`.

## Decision

Run normal sync as explicit observation, immutable snapshot construction,
deterministic planning, validation, apply, and reporting phases. Both dry-run
and real execution consume the same typed, ordered `SyncPlan`.

Planning is mutation-free. Apply validates its preconditions and executes the
materialized plan without rebuilding decisions. Target-specific lifecycle code
retains authority for its own preflight and actions, but cannot bypass the plan
as the authorization boundary.

## Consequences

Dry-run describes the actions that real execution would consume, and tests can
exercise planning without external mutation. The plan records enough emitted
data and ownership snapshots to be larger than a simple action list. A real
`--fresh` cache clear remains outside the pure transform because it must happen
before observation; fresh dry-run stays mutation-free.
