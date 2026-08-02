# Require proven ownership before managed output cleanup

Status: Accepted
Date: 2026-07-26

## Context

Converted files are runtime-discoverable state. Without durable ownership,
renaming, disabling, or removing a source can leave stale output, while broad
cleanup risks deleting files created or edited by the user or another tool.

The Codex package lifecycle introduced bounded ownership in
[PR #19](https://github.com/safurrier/ai-config/pull/19), merged as
`9983cc993795fb24871e3f62f19517066356b830`. Pi adopted the same safety boundary
in [PR #24](https://github.com/safurrier/ai-config/pull/24), merged as
`f3543417abda9296a7ebe2080e019a4f315fc3a7`, after loose Pi output was shown to
survive source removal. Current enforcement lives in
`src/ai_config/codex_lifecycle.py`, `src/ai_config/pi_ownership.py`, and
`src/ai_config/output_safety.py`.

## Decision

For Codex, record package and marketplace identities plus their reserved
generated roots. Limit lifecycle removal to recorded entries, reject unrelated
runtime identity collisions, and keep package writes beneath
`.ai-config/codex/`. Package emission may replace files inside that generated
root.

For Pi, record source identity, relative path, content digest, and executable
mode. Remove or replace only matching owned files; preserve locally modified
owned files. Reject unowned collisions and conflicting ownership domains.

Both paths reject malformed ownership records, traversal, and symlinked output.
Preserve historical unowned output for deliberate human cleanup. Cursor and
OpenCode output remains path-contained but is outside this ownership-ledger
decision.

## Consequences

Codex sync can reconcile package lifecycle without removing unrelated runtime
entries. Pi sync can repair, update, and remove recorded files without claiming
unrelated paths. Interrupted Pi reconciliation uses pending transaction state
so retry does not overwrite later user edits. Ownership schemas and recovery
rules are durable compatibility contracts; stricter safety may stop a sync and
require explicit cleanup instead of guessing.
