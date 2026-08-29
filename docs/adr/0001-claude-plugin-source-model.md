# Use Claude Code plugins as the source model

Status: accepted
Date: 2026-02-03

## Context

The project replaced repeated manual `claude plugin marketplace add` and `claude plugin install` operations with version-controlled YAML configuration. Claude Code provides a bundle model for skills, hooks, commands, agents, Model Context Protocol servers, and Language Server Protocol servers. During feasibility research for cross-tool conversion, that model offered the richest component set. Other tools can use subsets or transformations of it.

Repository genesis `499cb2b612d26909c6787775401b76e806384310` in `README.md` provides the initial evidence. [PR #3](https://github.com/safurrier/ai-config/pull/3) added the feasibility research and implementation in merge commit `a11b2c66134b3a6304d23d4dd2daea5910244b2d`.

## Decision

Configuration version 1 uses Claude Code as its only top-level runtime target. Cross-tool support consumes a Claude Code plugin as source and converts it to Codex, Cursor, OpenCode, or Pi output. It defines no independent desired-state schemas for those runtimes.

## Consequences

One source bundle and one declarative marketplace/plugin model remain authoritative. Conversion can reuse the source plugin's structure, but fidelity is asymmetric. Target-only capabilities aren't inputs. The converter reports unsupported Claude features instead of falsely claiming portability.
