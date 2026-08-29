# ai-config source

`src/ai_config/` implements configuration parsing, Claude lifecycle orchestration, and cross-tool conversion. Start at `cli.py`; keep command handlers thin and place behavior behind typed boundaries.

## Commands

```bash
uv run --frozen --no-sync ruff check src/
uv run --frozen --no-sync ty check src/
uv run --frozen --no-sync pytest tests/unit/ -v
```

## Gotchas

- **DO** use frozen dataclasses and tuples for configuration and sync records. **NOT** put mutable collections in frozen contracts. **BECAUSE** planning depends on immutable, comparable inputs.
- **DO** observe state, materialize a `SyncPlan`, then apply that plan. **NOT** parse sources, choose cache state, or create replacement actions during execution. **BECAUSE** the plan is the mutation authorization boundary.
- **DO** use `source_safety.py` for every plugin-source read. **NOT** add a direct `Path.read_*` path for conversion input. **BECAUSE** source containment rejects links, traversal, and special files before bytes are read.
- **DO** keep target behavior in emitters, validators, and lifecycle modules. **NOT** encode a target-specific exception in `PluginIR`. **BECAUSE** the IR remains the shared source contract.
- **DO** delete only through target ownership evidence. **NOT** treat a contained Cursor or OpenCode path as owned. **BECAUSE** path containment does not prove provenance.

## Related Context

| Path | Purpose |
|---|---|
| `../SPEC.md` | Normative product and safety requirements. |
| `../ai_agent_docs/conversion-pipeline.md` | Sync and conversion implementation boundary. |
| `../docs/architecture.md` | System-level data flow and ownership. |
| `../tests/unit/` | Unit tests that mirror source seams. |

<!-- generated-by: context-engineering@2.6.5 | last-updated: 2026-08-22 -->
