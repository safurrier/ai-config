# Require proven ownership for destructive cleanup

Status: Accepted
Date: 2026-07-26

## Context

Pi conversion output once had no lasting owner record. A renamed, disabled, or removed source could leave stale files that a runtime could find. Deleting by path could also remove user state. Codex package reconciliation has a similar boundary between generated sources and runtime-owned installation state.

Evidence: [PR #24](https://github.com/safurrier/ai-config/pull/24), merged as `f3543417abda9296a7ebe2080e019a4f315fc3a7`, documents the stale-output problem. It requires preservation of unowned collisions and changed output. [PR #19](https://github.com/safurrier/ai-config/pull/19) records the related Codex boundary.

## Decision

Destructive cleanup requires target-specific ownership proof. Pi records the checked output root, source identity, relative path, digest, and executable mode. It uses a pending transaction so it can retry reconciliation. Codex cleans generated files only in recorded package roots. Codex also owns installed lifecycle operations. Path containment for Cursor and OpenCode never establishes ownership of existing files.

## Consequences

Recorded Codex and Pi state can converge safely. The system fails closed or preserves unowned collisions, changed Pi files, malformed ledgers, traversal, symlinks, and stale recovery input. Historical unowned output can remain until a separate migration establishes authority.
