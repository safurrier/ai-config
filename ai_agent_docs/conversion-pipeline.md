# Conversion Pipeline

Architecture for converting Claude Code plugins to other AI coding tools.

## Pipeline Stages

```
Claude Plugin Directory
        │
   claude_parser.py    Parse: reads plugin.json, SKILL.md, hooks, MCP, LSP
        │
       ir.py            IR: tool-agnostic PluginIR (Pydantic models)
        │
   emitters.py          Emit: target-specific file generators
        │
   report.py            Report: structured conversion summary
        │
   convert.py           Orchestrator: ties all stages together
```

## Key Types (`converters/ir.py`)

- `PluginIR` — central type containing `PluginIdentity` + typed `components` list
  - Accessor methods: `.skills()`, `.commands()`, `.hooks()`, `.mcp_servers()`, `.agents()`, `.lsp_servers()`
  - Collects `Diagnostic` objects (never raises during parse/emit)
- `TargetTool` — enum: `claude`, `codex`, `cursor`, `opencode`, `pi`
- `InstallScope` — enum: `user`, `project`, `local`
- `MappingStatus` — fidelity tracking: `native` > `transform` > `emulate` > `fallback` > `unsupported`
- `Skill`, `Command`, `Hook`, `McpServer`, `Agent`, `LspServer` — component types
- `TextFile`, `BinaryFile` — file content carriers

## Emitters (`converters/emitters.py`)

Duck-typed classes sharing the same shape (no explicit Protocol ABC):

| Emitter | Target | Config Format | Env Var Syntax |
|---------|--------|---------------|----------------|
| `CodexEmitter` | `.codex/skills/` + `.codex/` | TOML (`config.toml` with `[mcp_servers.*]`) + JSON (`hooks.json`) | `${VAR}` |
| `CursorEmitter` | `.cursor/` | JSON (`mcp.json`, `hooks.json`) | `${env:VAR}` |
| `OpenCodeEmitter` | `.opencode/` | JSON (`opencode.json`, `opencode.lsp.json`) | `{env:VAR}` |
| `PiEmitter` | `.pi/` or `.pi/agent/` | Markdown skills/prompts + TypeScript extensions | `${VAR}` |

Factory: `get_emitter(target, scope, commands_as_skills) -> Emitter`

The Codex emitter owns loose files, not installable plugin packages. It writes namespaced skills,
deprecated prompts or command-as-skill output, MCP TOML, and hook JSON. `EmitResult.write_to()`
merges existing Codex `config.toml` and `hooks.json` data instead of replacing shared user state.
Target-native Codex files pass through the same loose output root and merge rules.

Each emitter returns `EmitResult` containing:
- `EmittedFile` list (path + content + binary flag)
- `ComponentMapping` list (fidelity tracking per component)
- `Diagnostic` list

## Orchestrator (`converters/convert.py`)

Three API tiers:

```python
# Full conversion with reports, optional file writing
convert_plugin(plugin_path, targets, output_dir, scope, dry_run, best_effort) -> dict[TargetTool, ConversionReport]

# Simple one-shot
convert_plugin_simple(plugin_path, target, output_dir) -> EmitResult

# Text preview only
preview_conversion(plugin_path, targets) -> str
```

## Reports (`converters/report.py`)

`ConversionReport` auto-categorizes components by `MappingStatus`:
- `NATIVE`/`TRANSFORM` → converted
- `FALLBACK`/`EMULATE` → degraded (with `lost_features`)
- `UNSUPPORTED` → skipped

Output: `.summary()`, `.to_json()`, `.to_markdown()`

Each requested target owns its own `EmitResult`, `ConversionReport`, mappings, and output paths.
Degraded Codex mappings do not change Cursor, OpenCode, or Pi mappings. An unexpected emitter
exception still aborts the multi-target conversion unless best-effort mode is enabled. This
per-target ownership boundary is also why an installable package must not silently replace the
existing Codex mode.

## Experimental Codex package boundary

Issue #13 proved a public Codex plugin manifest and marketplace lifecycle with the fixture under
`tests/fixtures/experimental/codex-plugin-marketplace/`. The fixture and
`tests/probes/probe_codex_plugin_package.py` do not add a `TargetTool`, emitter factory branch,
validator registration, config literal, sync path, or CLI choice.

The current IR can carry the package's tested skill and hook. It also carries MCP server definitions,
which the public package contract accepts through `mcpServers`. It does not model all marketplace
listing fields or published-plugin interface metadata. Commands need an explicit package mapping
because the public bundle contract documents skills rather than loose custom prompts. Agents and LSP
servers remain unsupported for Codex.

A package emitter would write an owned plugin directory and marketplace entry, not merge into shared
`config.toml` or `hooks.json`. A separate package validator would check manifest and marketplace
references; `CodexOutputValidator` must continue to check loose `.codex/` output. Existing mapping
statuses and reports can represent package files without a cross-tool package abstraction. See the
[compatibility baseline](target-compatibility-baseline.md#pluginpackage-contract) for the evidence,
single decision, and follow-up slices.

## Adding a New Target

1. Add enum value to `TargetTool` in `ir.py`
2. Create emitter class in `emitters.py` with `target` attr and `emit()` method
3. Register in `get_emitter()` factory
4. Create output validator in `validators/target/<tool>.py`
5. Register in `validators/target/__init__.py` → `get_output_validator()`
6. Add CLI choice in `cli.py` convert command
