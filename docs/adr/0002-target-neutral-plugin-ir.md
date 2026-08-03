# Convert through a target-neutral plugin IR

Status: Accepted
Date: 2026-02-12

## Context

The target tools shared some concepts but differed in paths, schemas, lifecycle, and feature coverage. Direct target-to-target transforms would have coupled parsing to each emitter and made it difficult to report when a skill, command, hook, MCP server, agent, or LSP server was transformed or unsupported. The conversion feasibility research recommended a normalized representation and independent emitters.

Evidence: `.ai/plans/2026-02-04-1530-plugin-conversion-spec/RESEARCH_REPORT.md` and `.ai/plans/2026-02-05-0600-emitter-protocol-tmux-validation/SPEC.md` as introduced by [PR #3](https://github.com/safurrier/ai-config/pull/3), merge SHA `a11b2c66134b3a6304d23d4dd2daea5910244b2d`.

## Decision

Parse each Claude plugin once into `PluginIR`. Invoke an independent target emitter over that immutable representation, and return per-component mappings and diagnostics with each target result.

## Consequences

Parsing and source validation are shared, while target semantics remain isolated. Adding a target requires an emitter and validator rather than changes to every existing target. The IR cannot guarantee semantic equivalence; emitters still own degradation and unsupported-feature reporting.
