# Separate sync observation, planning, and application

Status: Accepted
Date: 2026-07-29

## Context

Claude reconciliation, multi-target conversion, ownership, cache checkpoints, and partial lifecycle failures had built up over time. Imperative sync code mixed observation with mutation. As a result, dry-run could differ from real execution. It was also hard to prove that later actions still had authority from the state used for planning.

Evidence: [PR #26](https://github.com/safurrier/ai-config/pull/26), merged as `693442307dbd54b1c8e0f9bb4a17937f98539a2f`, records the refactor's acceptance criteria. Those criteria cover plan parity, precondition drift, ownership, failure boundaries, and ordered phase ownership.

## Decision

Sync first observes desired configuration, runtime state, source state, cache, and ownership. A pure transform then creates an immutable, ordered `SyncPlan`. Validation checks blocking diagnostics and preconditions. An executor then applies that exact plan and reports completed and failed actions.

## Consequences

Dry-run and each real execution stage use the same immutable authorization artifact. Target-specific planners retain responsibility for their domains. The design adds snapshot and action records. In return, it exposes state drift, partial progress, and checkpoint eligibility. Real `--fresh` cache clearing stays outside the pure transform because it changes later observation. Fresh dry-run stays mutation-free.

[ADR 0008](0008-bounded-sync-convergence-stages.md) allows one explicit re-observation barrier after a successful Claude prerequisite plan. It forbids replanning during apply. The conversion stage uses a new snapshot and a separately checked immutable plan. The operation remains bounded.
