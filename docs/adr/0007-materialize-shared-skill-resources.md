# Materialize shared plugin resources into generated skills

Status: Accepted
Date: 2026-08-20

## Context

A Claude plugin can keep scripts, references, and binary data once at its root while several skills refer to those files through `${CLAUDE_PLUGIN_ROOT}`. Codex, Cursor, OpenCode, and Pi discover generated skills independently, so retaining that source-time reference would make an emitted skill depend on files outside its own directory. Package-root deduplication would solve only some targets and would create a second runtime lookup contract.

Claude Code 2.1.231 was probed with `x-ai-config-includes` in skill frontmatter. Both `claude plugin validate --strict` and native inventory loading through `claude --plugin-dir ... plugin details include-probe` accepted the metadata and discovered the skill. The reproducible probe is `tests/probes/probe_claude_skill_includes.py`; exact evidence is recorded in `ai_agent_docs/target-compatibility-baseline.md`.

## Decision

A source skill declares exact plugin-root-relative regular files in `x-ai-config-includes`. Conversion captures those bytes and executable mode in immutable IR records, then one target-neutral projection materializes each file below `_shared/<plugin-relative-path>` in every consuming generated skill. Instruction Markdown rewrites only exact declared `${CLAUDE_PLUGIN_ROOT}/<path>` occurrences to that skill-root-relative path. Generated `SKILL.md` removes the build metadata.

The source remains deduplicated while generated copies are intentional regular files. V1 rejects globs, directories, recursion declarations, absolute or traversing paths, empty/dot components, backslashes, links, special files, duplicate declarations, projected collisions, and undeclared root placeholders. A declared transitive dependency may have zero direct rewrites. There is no package-root deduplication.

Every conversion source read uses the contained-source authority. It rejects final and in-root ancestor symlinks, traversal, resolved escape, and non-regular files before reading bytes. Plugin hashing covers every safely readable source file and fails closed on unsafe entries.

## Consequences

Each generated skill is portable and self-contained at the cost of deterministic per-consumer duplication. Reports expose the logical source, consumer, target-relative copy path, copied bytes, copy count, and direct rewrite count without calling zero-rewrite dependencies unused.

Pi copies participate in its digest ownership ledger, and Codex copies remain inside the generated package root. Cursor and OpenCode may create or update desired copies but do not gain deletion authority or stale-file provenance from containment alone.
