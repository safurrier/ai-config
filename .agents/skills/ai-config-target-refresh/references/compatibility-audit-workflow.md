# Compatibility Audit Workflow


## Contents

- [1. Build the current ai-config matrix](#1-build-the-current-ai-config-matrix)
- [2. Capture observed tool versions](#2-capture-observed-tool-versions)
- [3. Research upstream sources](#3-research-upstream-sources)
- [4. Probe installed runtimes](#4-probe-installed-runtimes)
- [5. Classify gaps](#5-classify-gaps)
- [6. Plan implementation slices](#6-plan-implementation-slices)
- [7. Handoff checklist](#7-handoff-checklist)

Use this reference to audit ai-config's target-tool support before changing converters or validators.

## 1. Build the current ai-config matrix

Read these files first:

- `README.md`
- `docs/conversion.md`
- `docs/index.md`
- `docs/commands.md`
- `SPEC.md`
- `src/ai_config/converters/emitters.py`
- `src/ai_config/converters/claude_parser.py`
- `src/ai_config/validators/target/`
- `tests/e2e/test_tool_validation.py`
- `tests/e2e/test_conversion.py`

Produce a matrix with one row per target:

| Target | Skills | Commands/prompts | MCP | Hooks | Agents | LSP | Config merge behavior | Real-tool tests |
|---|---|---|---|---|---|---|---|---|

For each cell, record whether support is native, transformed, emulated, unsupported, or diagnosed-only.

## 2. Capture observed tool versions

Run version commands where available:

```bash
claude --version
codex --version
pi --version
cursor-agent --version || cursor --version
opencode --version
```

Record:

- command,
- output,
- date checked,
- whether command ran locally, in Docker, or both.

Update `ai_agent_docs/target-compatibility-baseline.md` when behavior or validation evidence changes.

## 3. Research upstream sources

For each target, check primary sources first:

- official docs,
- release notes / changelog,
- GitHub releases,
- npm package page or source package docs,
- installed local docs when the tool ships docs.

Search for:

- skill discovery paths,
- plugin/package format,
- MCP config location and shape,
- hook support and event names,
- prompt/command template support,
- config merge semantics,
- debug/introspection commands,
- auth-free ways to validate discovery.

Use citation discipline:

```text
Claim: Codex loads project Agent Skills from .agents/skills.
Source: <URL or local doc path>
Observed with: codex -C <tmp> debug prompt-input "test"
Implication: CodexEmitter should emit project skills to .agents/skills, not .codex/skills.
```

## 4. Probe installed runtimes

Use isolated temp directories. Do not test by mutating real home config unless explicitly dogfooding.

Preferred patterns:

- `CODEX_HOME=<tmp>/.codex` for Codex config isolation.
- `PI_CODING_AGENT_DIR=<tmp>/.pi/agent` for Pi user-scope isolation.
- `HOME=<tmp>` only when a tool does not expose a narrower config env var.
- Generated fixture plugins under `mktemp -d`.

Prefer probes that do not invoke a model or require API auth.

## 5. Classify gaps

Use these categories:

1. **stale output path** — ai-config emits to an old path.
2. **newly supported surface** — target now supports something ai-config marks unsupported.
3. **unsupported-but-diagnosed surface** — target still lacks support, but ai-config should emit a visible diagnostic.
4. **docs-only correction** — code is right, docs/help/spec are stale.
5. **validator gap** — generated output works, but doctor/validator does not check it.
6. **E2E gap** — file-shape tests exist but no real runtime test proves loading.
7. **config-write safety issue** — generated output clobbers shared config or mishandles quoting/merging.

## 6. Plan implementation slices

For each gap, produce:

```text
Gap:
Impact:
Files likely to change:
Unit tests:
Real-tool E2E:
Docs:
Reviewer to run:
Risk / rollback:
```

Prefer small slices:

1. parser/report diagnostics,
2. emitter behavior,
3. validator/doctor behavior,
4. docs/help text,
5. E2E runtime probe,
6. dogfood rollout.

## 7. Handoff checklist

Before handoff, include:

- matrix before/after,
- version/date baseline,
- upstream sources checked,
- runtime probes run,
- validation evidence,
- skipped validation and mitigation,
- review findings and dispositions,
- docs/baseline updates.
