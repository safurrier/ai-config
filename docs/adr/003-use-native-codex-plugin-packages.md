# Use native Codex plugin packages

Status: Accepted
Date: 2026-07-17

## Context

ai-config's first Codex target wrote loose skills, prompts, hooks, and shared
MCP configuration. Codex later added installable plugin packages and
marketplaces, providing a native lifecycle with one package identity. The loose
model left ai-config imitating ownership and mutating shared configuration.

[PR #17](https://github.com/safurrier/ai-config/pull/17) evaluated keeping loose
output, adding an opt-in package target, or moving to packages. After runtime
proof, [PR #19](https://github.com/safurrier/ai-config/pull/19), merged as
`9983cc993795fb24871e3f62f19517066356b830`, made packages the sole Codex target.

## Decision

Emit one deterministic Codex plugin package and local marketplace per source
plugin. Use the Codex CLI to inspect, register, install, update, repair, and
remove packages. ai-config owns generated package sources and its ownership
record; Codex owns installed cache, enablement, and shared runtime configuration.

Do not emit legacy loose Codex skills, prompts, hooks, or MCP tables.

## Consequences

Codex conversion follows the target's native lifecycle and reconciles a plugin
as one identity. Package manifests, selectors, SemVer, marketplace state, and
Codex CLI response schemas are compatibility boundaries. The 0.6.0 transition
was intentionally breaking, and old loose output remains outside automatic
deletion when ownership cannot be proved.
