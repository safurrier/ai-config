# Use Claude plugins as the canonical conversion source

Status: Accepted
Date: 2026-08-01
Original implementation: 2026-02-12

## Context

ai-config began as a declarative manager for Claude Code marketplaces and
plugins. When cross-tool conversion was added, the project needed one authoring
format from which Codex, Cursor, and OpenCode output could be derived. The
existing Claude bundle already carried identity, skills, commands, hooks,
agents, MCP servers, LSP servers, and support files.

[PR #3](https://github.com/safurrier/ai-config/pull/3), merged as
`a11b2c66134b3a6304d23d4dd2daea5910244b2d`, established the implemented
Claude-plugin-to-target pipeline while still listing bidirectional conversion
as possible future work. The current parser in
`src/ai_config/converters/claude_parser.py` retains the one-way source boundary;
this ADR ratifies it as the supported contract.

## Decision

Treat a Claude Code plugin bundle, rooted at `.claude-plugin/plugin.json`, as
the canonical conversion source. Parse that bundle once and emit selected
target formats. Report Claude-only semantics that cannot be preserved rather
than inventing an equivalent.

Do not introduce a second neutral authoring format or bidirectional conversion
contract without a new architectural decision. A target may supply native
override files for behavior that cannot be expressed portably, but those files
remain additions to the Claude source bundle rather than a new source authority.

## Consequences

Existing Claude plugin repositories can add target output without duplicating
their core skills and configuration. The parser necessarily follows Claude's
component vocabulary, so new Claude manifest fields require explicit parser
support or diagnostics. Native target projects and reverse conversion remain
outside the current contract.
