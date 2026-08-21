# Separate sync observation, planning, and application

Status: Accepted
Date: 2026-07-29

## Context

As Claude reconciliation, multi-target conversion, ownership, cache checkpoints, and partial lifecycle failures accumulated, imperative sync code mixed observation with mutation. Dry-run could diverge from real execution, and it was difficult to prove that a later action was still authorized by the state used to plan it.

Evidence: [PR #26](https://github.com/safurrier/ai-config/pull/26), merged as `693442307dbd54b1c8e0f9bb4a17937f98539a2f`, records plan parity, precondition drift, ownership, failure boundaries, and ordered phase ownership as the refactor's acceptance criteria.

## Decision

Sync first observes desired configuration, runtime state, source state, cache, and ownership. A pure transform produces an immutable, ordered `SyncPlan`. Validation checks blocking diagnostics and preconditions before an executor applies that exact plan and reports completed or failed actions.

## Consequences

Dry-run and each real execution stage share an immutable authorization artifact, and target-specific planners remain responsible for their domains. The design adds explicit snapshot and action records, but makes state drift, partial progress, and checkpoint eligibility observable. Real `--fresh` cache clearing remains outside the pure transform because it changes subsequent observation; fresh dry-run remains mutation-free.

[ADR 0008](0008-bounded-sync-convergence-stages.md) permits one explicit re-observation barrier after a successfully applied Claude prerequisite plan. It does not permit apply-time replanning: the conversion stage receives a new snapshot and separately validated immutable plan, and the operation remains bounded.
