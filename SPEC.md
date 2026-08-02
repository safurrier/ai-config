# ai-config specification

## Summary

ai-config makes AI coding-tool setup reproducible from one versioned YAML
configuration. It reconciles Claude Code marketplaces and plugins, and it can
convert Claude plugin bundles for Codex, Cursor, OpenCode, and Pi without
presenting lossy mappings as exact equivalence.

## Goals / Non-Goals

Goals:

- Reconcile configured Claude marketplace and plugin state predictably.
- Let one Claude plugin source produce independently validated target outputs.
- Preview mutations, preserve evidence about degraded mappings, and clean up
  generated state only when ownership is established.
- Keep target-runtime compatibility explicit and testable.

Non-goals:

- Define a universal plugin standard or support arbitrary source formats.
- Promise feature parity across tools with different component models.
- Own unrelated target-tool state or silently adopt historical generated files.
- Replace the target CLIs that own installation, enablement, or runtime behavior.

## Requirements

- Configuration discovery MUST prefer an explicit `--config` path, then
  project-local `.ai-config/config.yaml` or `.yml`, then the corresponding
  user-level files under `~/.ai-config/`.
- `sync` MUST treat the selected version 1 configuration as desired state and
  MUST NOT silently convert observed runtime state into configuration.
- Normal dry-run and apply MUST consume the same ordered `SyncPlan`; planning
  MUST NOT write files, clear caches, delete output, or invoke state-changing
  target commands.
- Apply MUST verify that the observed state and conversion inputs still match
  the plan before mutation.
- Conversion MUST parse Claude plugin bundles into one target-independent
  `PluginIR`, and each emitter MUST produce an independent `EmitResult` without
  mutating the shared IR.
- Conversion MUST use `native`, `transform`, `emulate`, `fallback`, and
  `unsupported` mappings plus diagnostics to describe fidelity; a written file
  MUST NOT be presented as proof of semantic equivalence.
- Target-native files under `targets/<target>/` MUST override generated files
  only inside the selected target output boundary.
- Codex package removal and Pi file cleanup MUST require durable ownership
  evidence, preserve unrelated state, and reject traversal, symlink, and
  ownership-collision ambiguity. Pi cleanup MUST additionally preserve locally
  modified owned files by content digest.
- Cache and ownership checkpoints MUST be committed only after their authorized
  actions succeed; reports MUST distinguish completed, failed, planned, and
  no-op actions when later phases fail.
- Operators SHOULD use `--dry-run` as the inspection path before a mutating
  sync or standalone conversion.
- Callers MAY select any supported conversion subset from Codex, Cursor,
  OpenCode, and Pi.

## Interfaces & Contracts

- `ai-config init` creates configuration interactively or through its supported
  non-interactive inputs.
- `ai-config sync` reconciles configured state; `sync --dry-run` is the
  mutation-free preview boundary.
- `ai-config status`, `update`, and `watch` inspect drift, refresh installed
  plugins, and re-run reconciliation after relevant changes.
- `ai-config convert <plugin>` parses one Claude plugin and emits selected target
  formats; `--dry-run` previews paths and mappings without writing.
- `ai-config doctor` validates configured plugin health, while
  `doctor --target <target> <output>` validates converted output.
- The version 1 YAML schema accepts Claude marketplaces/plugins plus optional
  conversion settings for `codex`, `cursor`, `opencode`, and `pi`.
- `.claude-plugin/plugin.json` is the canonical source manifest boundary;
  `PluginIR` is the internal conversion boundary; `EmitResult` and lifecycle
  plans are target-specific output boundaries.
- Codex installation is delegated to the Codex plugin CLI. Cursor and OpenCode
  receive path-contained files. Pi receives project `.pi/` or user
  `~/.pi/agent/` files governed by ai-config's Pi ownership ledger.

## Invariants

- Desired, observed, planned, applied, and reported state remain distinct.
- A failed or unavailable source cannot authorize cleanup of previously owned
  output merely because it is absent from the current observation.
- Generated identities and paths are normalized deterministically and remain
  contained beneath their validated output roots.
- Unowned collisions fail closed; historical unowned output remains a human
  cleanup decision.
- Conversion diagnostics accumulate instead of hiding unsupported or degraded
  behavior behind a successful file write.
- Target-specific lifecycle code may validate and execute its own actions but
  cannot bypass the materialized sync plan as the authorization boundary.

## Acceptance

Current behavior is accepted when all of the following pass:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/
uv run ty check src/
uv run pytest tests/ -q
uv run mkdocs build --strict
```

Changes to a real target contract also require the applicable Docker lane and
runtime probe selected by `.agents/skills/ai-config-target-refresh/SKILL.md`.
Contract changes must keep this specification, the relevant ADR, and the
architecture/reference docs aligned with code and tests.
