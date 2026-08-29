# Emit Codex plugin packages instead of loose files

Status: accepted
Date: 2026-07-17

## Context

Early Codex conversion wrote loose skills, prompts, hooks, and Model Context Protocol configuration. Codex later introduced installable plugin packages and local marketplaces with a native lifecycle. A spike first recommended loose output while package contracts remained experimental. Later stable command-line interface and package evidence made the native package path viable.

[PR #17](https://github.com/safurrier/ai-config/pull/17) records the cautious spike in merge commit `89dc84ad9f45c6c5c0da56ef86a026abaf4a021c`. [PR #19](https://github.com/safurrier/ai-config/pull/19) records the adoption in merge commit `9983cc993795fb24871e3f62f19517066356b830`.

## Decision

Codex conversion emits one deterministic plugin package and local marketplace per source plugin under `.ai-config/codex/marketplaces/`. ai-config owns those generated sources and their ownership record. The Codex command-line interface handles marketplace registration and plugin install, list, repair, and removal operations.

## Consequences

Skills, supported hooks, and Model Context Protocol servers travel through Codex's native package boundary. Claude commands become package skills, and the converter diagnoses unsupported semantics. ai-config no longer emits new loose Codex skills, prompts, hooks, or direct Model Context Protocol tables. Codex owns its installed cache, enablement, and shared configuration.
