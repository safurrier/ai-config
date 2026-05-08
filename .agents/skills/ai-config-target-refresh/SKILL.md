---
name: ai-config-target-refresh
description: This skill audits and refreshes ai-config target-tool compatibility for Claude, Codex, Cursor, OpenCode, Pi, and similar AI coding CLIs. Use when upstream tool releases may have changed skill discovery, MCP config, hooks, prompts, plugin schemas, or when updating ai-config converters, validators, docs, or E2E coverage for target runtimes.
---

# ai-config Target Refresh

Audit and refresh ai-config's understanding of AI coding tool capabilities. Treat the work as a compatibility investigation first, then an implementation task.

## Core rule

Prove every target-tool capability with at least one of:

1. current upstream documentation or release notes,
2. a real local/runtime probe in an isolated temp directory,
3. a Docker E2E test using the real tool.

Do not rely only on generated file shape when the target runtime has an auth-free introspection path.

## Workflow

1. Snapshot ai-config's current support matrix.
   - Read `README.md`, `docs/index.md`, `docs/conversion.md`, `SPEC.md`, `docs/commands.md`.
   - Inspect `src/ai_config/converters/emitters.py`, `src/ai_config/converters/claude_parser.py`, and `src/ai_config/validators/target/`.
   - Inspect `tests/e2e/test_tool_validation.py` and `tests/e2e/test_conversion.py` for current real-tool coverage.
   - Load `references/compatibility-audit-workflow.md` for the full audit procedure.

2. Capture tool versions and evidence date.
   - Record versions for every relevant installed tool: `claude`, `codex`, `pi`, `cursor-agent`, `opencode`.
   - Update or create a compatibility baseline when behavior changes. Use `ai_agent_docs/target-compatibility-baseline.md` as the baseline location.

3. Research upstream behavior.
   - Check official docs, release notes, changelogs, package pages, and local installed docs.
   - Prefer primary sources over blog posts or stale examples.
   - For each claim, keep source URL/path, checked date, and observed implication for ai-config.

4. Probe real runtimes.
   - Use isolated temp directories and explicit env vars such as `CODEX_HOME` and `PI_CODING_AGENT_DIR`.
   - Treat named probe commands as version-specific candidates: first confirm the installed CLI still exposes the command with `--help` or equivalent, then run it. If a documented probe no longer exists, do not count generated file shape as proof; classify the missing introspection as an E2E/probe gap.
   - Prefer auth-free introspection: Codex `debug prompt-input`, Pi RPC `get_commands`, OpenCode `debug skill`, Claude `plugin validate`, target `mcp list` commands.
   - Load `references/runtime-probes.md` before running probes.

5. Compare claims against reality.
   - Compare ai-config docs/code, upstream docs, and runtime probes.
   - Classify each gap as: stale output path, newly supported surface, unsupported-but-diagnosed surface, docs-only correction, validator gap, E2E gap, or config-write safety issue.

6. Plan implementation and validation together.
   - For every code change, name the matching unit, validator, docs, and real-tool E2E checks before editing.
   - Load `references/validation-matrix.md` for target-specific validation patterns.
   - If the user asks for an audit/plan only or says not to edit code, stop after the pre-implementation outputs. Explicitly state that no files were changed and include the HK validation/review evidence that should be recorded later.

7. Implement in slices.
   - Update parser/IR diagnostics before emitters when source components need explicit handling.
   - Update emitters and validators together.
   - Update docs/help output alongside behavior.
   - Preserve existing user config when writing shared config files. Merge, do not clobber, unless the target file is owned only by generated output.

8. Validate and record evidence.
   - Use focused tests while iterating.
   - Run static checks and CI parity before handoff.
   - Run Docker all-tools E2E when target runtime behavior changes.
   - If local Docker is unavailable, record a dangerous skip with mitigation and ensure GitHub E2E runs.
   - Use HK evidence with explicit rationale: `hk validate --why '<why this check proves the changed surface>' -- <command>`, `hk dangerously-skip validation --label <check> --reason <why unavailable> --mitigation <how covered>`, `hk review add ...`, `hk ready --target .`, and `hk summary --target .`.

9. Review from the right perspectives.
   - Request target-runtime-assumption review for stale tool behavior.
   - Request conversion-safety review for config writes, path placeholders, idempotency, and diagnostics.
   - Request agent-friendly CLI review when CLI UX/help/JSON output changes.

10. Capture durable lessons.
    - Update `ai_agent_docs/target-compatibility-baseline.md` when observed target behavior changes.
    - Add new probes to E2E tests when they prevent a regression.
    - Add source-of-truth notes to `AGENTS.md` only for stable repo workflow rules.

## Required outputs

Produce these before implementation:

- current compatibility matrix,
- observed tool versions and checked date,
- upstream source summary,
- runtime probe plan,
- gap list with classifications,
- implementation slices,
- validation plan mapped to each changed surface.

Produce these before handoff:

- files changed,
- validation evidence,
- skipped validation and mitigation,
- compatibility baseline updates,
- review findings and dispositions.

## References

- `references/compatibility-audit-workflow.md` — detailed audit procedure.
- `references/runtime-probes.md` — auth-free runtime probe commands.
- `references/validation-matrix.md` — changed surface to validation mapping.
- `references/pr12-case-study.md` — concrete lessons from the Codex/Pi refresh PR.
