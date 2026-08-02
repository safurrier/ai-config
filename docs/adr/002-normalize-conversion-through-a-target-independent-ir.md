# Normalize conversion through a target-independent IR

Status: Accepted
Date: 2026-02-12

## Context

Direct source-to-target transformations would repeat parsing, naming, fidelity,
and diagnostic rules for every target. As target count grows, pairwise
conversion paths would make it difficult to compare behavior or add a target
without changing existing emitters.

[PR #3](https://github.com/safurrier/ai-config/pull/3), merged as
`a11b2c66134b3a6304d23d4dd2daea5910244b2d`, introduced the Parse → IR → Emit
pipeline and independent target results. The current contracts live in
`src/ai_config/converters/ir.py`, `claude_parser.py`, and `emitters.py`.

## Decision

Parse a source plugin into one typed `PluginIR` containing normalized identity,
components, source paths, and diagnostics. Give the same immutable logical
representation to each target emitter. Each emitter produces its own
`EmitResult`, mappings, files, cleanup candidates, and diagnostics.

Record conversion fidelity with the shared `MappingStatus` vocabulary instead
of treating a written file as proof of semantic equivalence. Keep target
lifecycle and installation decisions outside the IR.

## Consequences

Parsers and emitters have separate ownership, new targets reuse one normalized
input, and reports can compare fidelity consistently. The IR becomes a durable
internal compatibility seam: adding a component or changing normalization can
affect every emitter and requires cross-target tests. Target-only concepts stay
in emitters, lifecycle plans, or native override files rather than distorting
the shared model.
