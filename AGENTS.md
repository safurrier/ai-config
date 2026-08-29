# Project guidance

ai-config manages Claude Code plugins from declarative YAML. It converts a
Claude plugin source into Codex, Cursor, OpenCode, and Pi artifacts.

## Commands

Run checks without changing the lockfile:

```bash
uv run --frozen --no-sync ruff check src/
uv run --frozen --no-sync ty check src/
uv run --frozen --no-sync pytest tests/unit/ -v
uv run --frozen --no-sync mkdocs build --strict
```

## Gotchas

- **DO** preserve the target-neutral IR and report target degradation or unsupported
  features. **NOT** add a target exception to the shared source model. **BECAUSE**
  conversion fidelity differs by runtime.
- **DO** retain observe-plan-apply boundaries and exact-plan preconditions. **NOT**
  replan in an executor or loop sync until quiet. **BECAUSE** dry-run parity and
  bounded convergence depend on immutable plans.
- **DO** prove ownership before cleanup and preserve unowned or changed output.
  **NOT** infer ownership from a contained path. **BECAUSE** containment does not
  authorize deletion.
- **DO** treat configured local marketplaces as the conversion source authority.
  **NOT** use an installed cache when that local source is missing or unsafe.
  **BECAUSE** stale installed bytes are not the configured source.
- **DO** use `uv run --frozen --no-sync` for validation in this worktree. **NOT**
  run lock-updating dependency commands. **BECAUSE** `uv.lock` is not part of
  documentation work.

## Releases

Before a release, finalize the version and release notes together. Move `[Unreleased]` entries to a new version section with the actual release date. Keep the version in `pyproject.toml` and the release notes aligned.

## Related context

| Path | Purpose |
|---|---|
| `SPEC.md` | Current correctness envelope and acceptance evidence. |
| `docs/architecture.md` | Current boundaries and data flow. |
| `docs/adr/README.md` | Lasting decisions and historical rationale. |
| `docs/project-evolution.md` | Provenance-backed phases and supersession. |
| `src/AGENTS.md` | Source-level patterns and extension points. |

<!-- generated-by: context-engineering@2.6.5 | last-updated: 2026-08-22 -->
