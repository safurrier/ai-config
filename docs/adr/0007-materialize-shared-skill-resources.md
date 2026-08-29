# Materialize shared plugin resources into generated skills

Status: Accepted
Date: 2026-08-20

## Context

A Claude plugin can store scripts, references, and binary data at its root. Several skills can refer to those files through `${CLAUDE_PLUGIN_ROOT}`. Codex, Cursor, OpenCode, and Pi discover generated skills. That source-time reference would point outside an emitted skill directory. Package-root deduplication would help only some targets. It would also add a second runtime lookup contract.

The team probed Claude Code 2.1.231 with `x-ai-config-includes` in skill frontmatter. Both `claude plugin validate --strict` and native inventory loading through `claude --plugin-dir ... plugin details include-probe` accepted the metadata. Both found the skill. The reproducible probe is `tests/probes/probe_claude_skill_includes.py`. Exact evidence is in `ai_agent_docs/target-compatibility-baseline.md`.

## Decision

A source skill lists exact plugin-root-relative regular files in `x-ai-config-includes`. Conversion captures their bytes and executable modes in immutable IR records. One target-neutral projection places each file in `_shared/<plugin-relative-path>` below every consuming skill. Instruction Markdown rewrites only exact declared `${CLAUDE_PLUGIN_ROOT}/<path>` occurrences to skill-root-relative paths. Generated `SKILL.md` removes the build metadata.

The source stays deduplicated. Generated copies are intentional regular files. V1 rejects globs, directories, recursion declarations, absolute paths, and traversing paths. It also rejects empty or dot components, backslashes, links, special files, duplicate declarations, projected collisions, and undeclared root placeholders. A declared transitive dependency can have zero direct rewrites and remains used. V1 forbids package-root deduplication.

Every conversion source read uses the contained-source authority. It rejects final and in-root ancestor symlinks, traversal, and resolved escape. It rejects non-regular files before reading bytes. Plugin hashing covers every safe source file. It fails closed on unsafe entries.

## Consequences

Each generated skill is portable. Each is self-contained. This costs one copy for each consumer. Reports show the logical source and consumer. They show the target-relative copy path and copied bytes. They also show the copy count and direct rewrite count.

Pi copies enter its digest ownership ledger. Codex copies stay inside the generated package root. Cursor and OpenCode can create or update desired copies. Containment alone gives them neither deletion authority nor stale-file provenance.
