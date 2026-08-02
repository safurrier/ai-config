# Architecture

ai-config separates declarative intent, observed runtime state, conversion,
target lifecycle, and mutation. This keeps a preview useful without letting a
generated file or a target CLI response silently become configuration.

## System boundaries

```text
versioned YAML configuration
          |
          v
configuration + source discovery -----> Claude runtime observation
          |                                      |
          +--------------+-----------------------+
                         v
               immutable sync planning
                         |
              +----------+-----------+
              |                      |
              v                      v
       Claude reconciliation   conversion planning
                                      |
                           Claude bundle -> PluginIR
                                      |
                       +--------------+-------------+
                       v              v             v
                    Codex       Cursor/OpenCode     Pi
                   package          files          files
                       |                             |
                 Codex CLI                    Pi ownership
```

The Click CLI in `src/ai_config/cli.py` is a thin entrypoint. Configuration
parsing lives in `config.py` and frozen schema types in `types.py`. Stable
operations delegate sync work to `sync_orchestration.py`, while
`sync_pipeline.py` owns immutable desired, observed, plan, action, diagnostic,
and report records.

## Sync flow

Normal sync has five boundaries:

1. Observe configured sources, Claude state, caches, target output, and
   ownership records.
2. Build immutable `DesiredState`, `RuntimeSnapshot`, and `SourceBatch` values.
3. Produce and structurally validate one ordered `SyncPlan`.
4. Recheck preconditions and apply only the materialized actions.
5. Report completed, failed, skipped, and checkpoint outcomes.

Planning performs no state-changing calls. A real `--fresh` clears Claude cache
before observation because that changes the observable input; fresh dry-run
does not clear it. The detailed data flow is documented in the repository's
[`ai_agent_docs/conversion-pipeline.md`](https://github.com/safurrier/ai-config/blob/main/ai_agent_docs/conversion-pipeline.md).

## Conversion flow

`ClaudePluginParser` reads `.claude-plugin/plugin.json` and supported component
directories into a `PluginIR`. The IR normalizes identity and component shapes
but retains source paths and diagnostics. Independent emitters then return
target-specific `EmitResult` objects; they never mutate the shared IR.

Mapping status is part of the result: `native`, `transform`, `emulate`,
`fallback`, or `unsupported`. Target-native files under `targets/<target>/`
overlay generated output at the target's natural root and are still subject to
path and ownership safety.

## Target ownership

| Target | Output and lifecycle authority | Cleanup boundary |
|---|---|---|
| Claude | Claude marketplaces and plugin CLI | Desired-vs-observed reconciliation |
| Codex | Generated package/marketplace sources plus Codex plugin CLI | Recorded package identity and reserved generated root |
| Cursor | `.cursor/` files and JSON configuration | Validated output-root containment |
| OpenCode | `.opencode/` plus JSON configuration | Validated output-root containment |
| Pi | Project `.pi/` or user `~/.pi/agent/` files | Recorded source, path, digest, and mode |

Codex and Pi can remove only state proven to belong to ai-config. Cursor and
OpenCode writes are contained but do not currently have equivalent durable
ownership ledgers. An unavailable source retains prior ownership and cannot
authorize cleanup merely by disappearing from observation.

## Extension and proof seams

New source components extend `PluginIR` and every affected emitter. New targets
add an emitter, output validator, configuration/CLI choice, tests, docs, and a
runtime probe when the target exposes one. The repo-local
`ai-config-target-refresh` skill owns compatibility audits for external tool
changes.

Unit tests cover pure planning, parsing, emission, validation, and safety
boundaries. Integration tests exercise local workflows. Docker E2E and isolated
target probes supply real-tool evidence for contracts that file inspection
cannot prove.
