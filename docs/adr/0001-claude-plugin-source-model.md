# Use Claude Code plugins as the source model

Status: Accepted
Date: 2026-02-03

## Context

The project began to replace repeated manual `claude plugin marketplace add` and `claude plugin install` operations with a version-controlled YAML configuration. Claude Code already supplied the bundle model for skills, hooks, commands, agents, MCP servers, and LSP servers. When cross-tool conversion was explored, that model also contained the richest component set; other tools could accept subsets or transformations of it.

Evidence: repository genesis `499cb2b612d26909c6787775401b76e806384310` in `README.md`, followed by the feasibility research and implementation merged as [PR #3](https://github.com/safurrier/ai-config/pull/3) at `a11b2c66134b3a6304d23d4dd2daea5910244b2d`.

## Decision

Config version 1 treats Claude Code as the only top-level runtime target. Cross-tool support consumes a Claude Code plugin as source and converts it to Codex, Cursor, OpenCode, or Pi output. It does not define independent desired-state schemas for those runtimes.

## Consequences

One source bundle and one declarative marketplace/plugin model remain authoritative. Conversion can reuse the source plugin's structure, but fidelity is asymmetric: target-only capabilities are not inputs, and unsupported Claude features must be diagnosed rather than silently claimed as portable.
