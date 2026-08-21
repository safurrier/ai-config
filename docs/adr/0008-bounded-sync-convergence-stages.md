# Bound sync convergence across prerequisite and conversion stages

Status: Accepted
Date: 2026-08-21

## Context

A configured remote Claude plugin may not have a readable conversion source in a fresh environment. The source becomes available only after Claude registers its marketplace and installs the plugin. A single immutable plan cannot both authorize that prerequisite mutation and precompute conversion artifacts from bytes that do not yet exist.

Configured local marketplaces have a different authority contract: their configured source tree is already inspectable and must not be replaced by Claude's installed cache merely because installation occurred. Treating either installed paths or repeated whole-sync execution as a universal fallback produced path-sensitive cache misses and made fresh isolated verification require another invocation.

ADR 0006 requires observation, immutable planning, precondition checks, and exact-plan execution. The convergence workflow must preserve those properties while acknowledging a real prerequisite boundary.

## Decision

Sync remains bounded and plan-driven, but may use two separately observed immutable plans:

1. The initial observation materializes a complete plan.
2. If an enabled non-local source is unavailable and the plan contains Claude marketplace or plugin prerequisites, sync projects and applies only that exact Claude prerequisite prefix.
3. After successful prerequisite application, sync performs one explicit re-observation and materializes a new plan.
4. The second plan is projected to conversion actions only. If it still requires any Claude marketplace or plugin action, conversion is blocked rather than retrying the prerequisite stage.
5. Optional verification performs one final read-only plan only after the aggregate apply succeeds.

Sync never recursively runs until quiet and never replans from inside an executor. Each applied stage has its own runtime, source, cache, and ownership snapshot and consumes only its materialized actions and target batches.

Configured local marketplaces are strict conversion-source authorities. Missing or unsafe configured local sources remain unavailable and never trigger installed-cache fallback or staged re-observation. Remote and marketplace-less plugins may use safely observed installed sources.

A dry run does not cross the prerequisite boundary. It reports exact Claude prerequisite actions and deferred source diagnostics without speculating about conversion artifacts that cannot yet be observed.

## Consequences

Fresh remote bootstrap can converge Claude installation and target conversion in one bounded invocation when the prerequisite succeeds and the source becomes readable. If post-install parsing or conversion fails, completed Claude actions remain visible, target ownership is retained according to existing rules, and sync exits non-zero without verification. If the second observation still needs Claude reconciliation, the user must correct the runtime state or retry; the same invocation will not reinstall repeatedly.

Conversion cache identity is the configured plugin selector plus conversion signature. Physical source path, provenance, source digest, and generated Codex digest remain observations required for a cache hit. Legacy path-keyed entries are discarded while validated tracked output roots remain available for ownership cleanup.
