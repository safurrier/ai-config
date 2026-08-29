# Bound sync convergence across prerequisite and conversion stages

Status: Accepted
Date: 2026-08-21

## Context

A configured remote Claude plugin may lack a readable conversion source in a fresh environment. Claude must register its marketplace and install the plugin first. One immutable plan cannot authorize that mutation because it lacks the bytes needed to prepare artifacts.

Configured local marketplaces have a different authority contract. Their configured source tree is already inspectable. Claude's installed cache must never replace it. Installed paths as a universal fallback caused path-sensitive cache misses. Repeated whole-sync runs did too. Both forced fresh isolated verification into another invocation.

ADR 0006 requires observation, immutable planning, precondition checks, and exact-plan execution. The convergence workflow retains those properties across a real prerequisite boundary.

## Decision

Sync stays bounded and plan-driven. It can use two separately observed immutable plans:

1. Initial observation materializes a complete plan.
2. If an enabled non-local source is unavailable, the plan may have Claude prerequisites. Sync then projects and applies only that exact Claude prerequisite prefix.
3. After successful prerequisite application, sync re-observes once and materializes a new plan.
4. The second plan contains only conversion actions. If it still requires a Claude marketplace or plugin action, sync stops conversion. It never retries the prerequisite stage.
5. Optional verification runs one final read-only plan only after the aggregate apply succeeds.

Sync never runs recursively until quiet. It never replans inside an executor. Each stage has its own runtime, source, cache, and ownership snapshot. Each stage uses only its materialized actions and target batches.

Configured local marketplaces strictly control their conversion sources. A missing or unsafe local source remains unavailable. It never triggers installed-cache fallback or staged re-observation. Remote and marketplace-less plugins can use safely observed installed sources.

A dry run never crosses the prerequisite boundary. It reports exact Claude prerequisite actions. It also reports deferred source diagnostics. It never guesses at conversion artifacts beyond observation.

## Consequences

Fresh remote bootstrap can complete Claude installation and target conversion in one bounded invocation. It needs a successful prerequisite and a readable source. If parsing or conversion fails after installation, completed Claude actions stay visible. Target ownership remains subject to existing rules. Sync exits non-zero without verification. If the second observation still needs Claude reconciliation, the user must correct runtime state or retry. The same invocation never reinstalls repeatedly.

The conversion cache key uses the configured plugin selector and conversion signature. A cache hit also needs the observed physical source path, provenance, source digest, and generated Codex digest. The system drops legacy path-keyed entries. Validated output roots remain for ownership cleanup.
