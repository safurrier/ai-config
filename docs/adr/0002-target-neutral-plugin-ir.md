# Convert through a target-neutral plugin IR

Status: accepted
Date: 2026-02-12

## Context

The target tools share some concepts, but they differ in paths, schemas, lifecycle, and feature coverage. Direct target-to-target transforms would couple parsing to each emitter. They would also make it hard to report whether a skill, command, hook, Model Context Protocol server, agent, or Language Server Protocol server changed or lacked support. The conversion feasibility research recommends a normalized representation with independent emitters.

`.ai/plans/2026-02-04-1530-plugin-conversion-spec/RESEARCH_REPORT.md` and `.ai/plans/2026-02-05-0600-emitter-protocol-tmux-validation/SPEC.md` record that research. [PR #3](https://github.com/safurrier/ai-config/pull/3) introduced them in merge commit `a11b2c66134b3a6304d23d4dd2daea5910244b2d`.

## Decision

Parse each Claude plugin once into `PluginIR`. Run an independent target emitter over that immutable representation. Return per-component mappings and diagnostics with each target result.

## Consequences

The system shares parsing and source validation while keeping target semantics isolated. Adding a target requires an emitter and validator, not changes to every existing target. The IR doesn't promise semantic equivalence. Emitters still report degradation and unsupported features.
