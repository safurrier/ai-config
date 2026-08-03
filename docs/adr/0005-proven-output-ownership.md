# Require proven ownership for destructive cleanup

Status: Accepted
Date: 2026-07-26

## Context

Loose Pi conversion output had no durable owner record. Renaming, disabling, or removing a source could leave stale runtime-discoverable files, while blindly deleting by path risked removing user state. Codex package reconciliation faced the same general boundary between generated sources and runtime-owned installation state.

Evidence: [PR #24](https://github.com/safurrier/ai-config/pull/24), merged as `f3543417abda9296a7ebe2080e019a4f315fc3a7`, states the stale-output problem and the requirement to preserve unowned collisions and modified output. Codex's related boundary is recorded by [PR #19](https://github.com/safurrier/ai-config/pull/19).

## Decision

Destructive cleanup requires target-specific proof of ownership. Pi records the validated output root, source identity, relative path, digest, and executable mode and uses a pending transaction for retryable reconciliation. Codex limits generated cleanup to recorded package roots and delegates installed lifecycle operations to Codex. Generic Cursor and OpenCode path containment does not claim ownership of pre-existing files.

## Consequences

Removal can converge safely for recorded Codex and Pi state. Unowned collisions, changed owned Pi files, malformed ledgers, traversal, symlinks, and stale recovery inputs fail closed or are preserved. Historical unowned output may remain until a separate migration establishes authority.
