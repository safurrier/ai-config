# ai-config specification

## Purpose

ai-config makes an AI coding-tool setup reproducible from one versioned YAML
configuration. It reconciles Claude Code marketplaces and plugins, then can
convert Claude plugin bundles for Codex, Cursor, OpenCode, and Pi.

## Scope

ai-config owns:

- configuration discovery and validation for the version 1 schema;
- Claude marketplace and plugin observation, planning, reconciliation, status,
  update, and watch workflows;
- parsing Claude plugin bundles into a target-independent representation;
- emitting and validating target-specific output for Codex, Cursor, OpenCode,
  and Pi; and
- ownership-aware lifecycle and cleanup for generated Codex and Pi state.

It does not define a universal plugin standard, promise exact feature parity
between tools, own unrelated target-tool state, or remove historical output
whose ownership cannot be established.

## Invariants

- The selected YAML configuration is the desired state for `sync`; observed
  runtime state never silently becomes configuration.
- Normal dry-run and apply consume the same ordered `SyncPlan`. Planning does
  not write files, clear caches, delete output, or call state-changing tool
  commands.
- Apply checks that observed state and conversion inputs still match the plan
  before mutation.
- Codex removal is limited by its package ownership ledger and reserved
  `.ai-config/codex/` root; package emission may replace files inside that
  generated root. Pi create, update, and removal use per-file ownership and
  content evidence, preserving locally modified owned files. Both paths reject
  traversal and symlinked output. Cursor and OpenCode writes are path-contained
  but do not have equivalent durable ownership ledgers.
- A conversion records each component as `native`, `transform`, `emulate`,
  `fallback`, or `unsupported`. Target gaps are reported rather than presented
  as exact equivalence.
- Cache and ownership checkpoints are committed only after their authorized
  actions succeed. Completed and failed actions remain distinguishable when a
  later phase fails.
- Each target emitter receives the same parsed plugin representation and owns
  an independent result; emitters do not mutate the shared representation.

## Interfaces

- `ai-config init` creates a configuration interactively or from a minimal
  non-interactive path.
- `ai-config sync` reconciles configured Claude plugin state;
  `sync --dry-run` is the mutation-free preview boundary.
- `ai-config status` inspects installed state. With `--config` or `--verify`, it
  also plans and reports drift from configuration.
- `ai-config update` refreshes named installed plugins or all installed plugins.
  `ai-config watch` reruns sync after relevant configuration or source changes.
- `ai-config convert <plugin>` parses one Claude plugin and emits selected
  target formats. `--dry-run` previews paths and mappings without writing.
- `ai-config doctor` validates configured plugin health;
  `doctor --target <target> <output>` validates converted output.
- `.ai-config/config.yaml` and `.ai-config/config.yml` are the project-local
  configuration surfaces; the same names under `~/.ai-config/` are the global
  fallback. An explicit `--config` path takes precedence.
- The version 1 schema accepts a Claude source target with marketplaces,
  plugins, and optional conversion settings for `codex`, `cursor`, `opencode`,
  and `pi`.
- JSON and terminal reports expose planned, completed, failed, and no-op action
  evidence where the command supports lifecycle reporting.

## Validation

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/
uv run ty check src/
uv run pytest tests/unit -q
uv run mkdocs build --strict
```

Real target-runtime changes also require the applicable probes and Docker E2E
lanes selected by `.agents/skills/ai-config-target-refresh/SKILL.md` and recorded
in `ai_agent_docs/target-compatibility-baseline.md`.
