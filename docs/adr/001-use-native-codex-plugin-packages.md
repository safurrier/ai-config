# Use native Codex plugin packages

Status: Accepted
Date: 2026-07-17

## Context

Codex added an installable plugin package and marketplace lifecycle. ai-config's
earlier Codex conversion wrote loose skills, prompts, hooks, and shared MCP
configuration, which left ai-config responsible for imitating target-runtime
ownership and lifecycle behavior.

Historical evidence: [PR #19](https://github.com/safurrier/ai-config/pull/19),
merged as `9983cc993795fb24871e3f62f19517066356b830`, replaced loose output with
package sources and lifecycle reconciliation. The current boundary is described
in `ai_agent_docs/conversion-pipeline.md` and implemented by
`src/ai_config/converters/codex_package.py` and
`src/ai_config/codex_lifecycle.py`.

## Decision

Emit one deterministic Codex plugin package and local marketplace per source
plugin. Use the Codex CLI to inspect, register, install, update or reinstall,
and remove packages. Reinstall a disabled generated package to restore its
enabled state. ai-config owns generated package sources and its ownership
record; Codex owns installed cache, enablement, and shared runtime configuration.

Do not emit legacy loose Codex skills, prompts, hooks, or MCP tables.

## Consequences

Codex conversion follows the target's native package model and can reconcile a
whole plugin as one identity. Package manifests, selectors, SemVer, marketplace
state, and CLI response schemas become compatibility boundaries that require
validation. The 0.6.0 transition was intentionally breaking, and old loose
output remains outside automatic deletion when ownership cannot be proved.
