# Require proven ownership before generated output cleanup

Status: Accepted
Date: 2026-07-26

## Context

Converted files are runtime-discoverable state. Without durable ownership,
renaming, disabling, or removing a source can leave stale output, while broad
cleanup risks deleting files created or edited by the user or another tool.

The Codex package lifecycle introduced bounded ownership in
[PR #19](https://github.com/safurrier/ai-config/pull/19). Pi adopted per-file
ownership in [PR #24](https://github.com/safurrier/ai-config/pull/24), merged as
`f3543417abda9296a7ebe2080e019a4f315fc3a7`, after loose Pi output was shown to
survive source removal.

## Decision

Require target-appropriate ownership evidence before cleanup. For Codex, record
package and marketplace identities plus reserved generated roots. For Pi,
record source identity, relative path, content digest, and executable mode.

Remove or replace only matching owned state and preserve historical unowned
output. Pi additionally preserves locally modified owned files by comparing
content digests. Codex owns its complete generated marketplace root and may
replace or remove that root once its recorded identity and path match. Reject
unowned collisions, malformed records, traversal, symlinked output, and
conflicting ownership domains. Cursor and OpenCode remain path-contained but do
not gain an ownership ledger without a separately evidenced lifecycle design.

## Consequences

Codex and Pi can reconcile removals without claiming unrelated runtime state.
Interrupted Pi work retains transaction evidence for safe retry. Ownership
schemas and recovery behavior are compatibility contracts, and ambiguous state
stops sync for deliberate human cleanup instead of guessing.
