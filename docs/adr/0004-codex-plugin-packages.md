# Emit Codex plugin packages instead of loose files

Status: Accepted
Date: 2026-07-17

## Context

Early Codex conversion wrote loose skills, prompts, hooks, and MCP configuration. Codex later introduced installable plugin packages and local marketplaces with a native lifecycle. A spike initially recommended retaining loose output while package contracts were experimental; later stable CLI and package evidence made the native package path viable.

Evidence: the cautious spike in [PR #17](https://github.com/safurrier/ai-config/pull/17), merge SHA `89dc84ad9f45c6c5c0da56ef86a026abaf4a021c`, and the adoption in [PR #19](https://github.com/safurrier/ai-config/pull/19), merge SHA `9983cc993795fb24871e3f62f19517066356b830`.

## Decision

Codex conversion emits one deterministic plugin package and local marketplace per source plugin under `.ai-config/codex/marketplaces/`. ai-config owns those generated sources and its ownership record. It delegates marketplace registration and plugin install, list, repair, and removal operations to the Codex CLI.

## Consequences

Skills, supported hooks, and MCP servers travel through Codex's native package boundary; Claude commands become package skills and unsupported semantics are diagnosed. ai-config no longer emits new loose Codex skills, prompts, hooks, or direct MCP tables. Installed cache, enablement, and shared Codex configuration remain Codex-owned.
