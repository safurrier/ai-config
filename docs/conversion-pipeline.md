---
id: conversion-pipeline
title: Conversion Pipeline
description: >
  Architecture for converting Claude Code plugins to other AI coding tools.
  Covers the Parse-IR-Emit pipeline stages, key types, emitters, and orchestrator.
index:
  - id: pipeline-stages
  - id: key-types-convertersirpy
  - id: emitters-convertersemitterspy
  - id: orchestrator-convertersconvertpy
  - id: reports-convertersreportpy
  - id: adding-a-new-target
---

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
- `TargetTool` — enum: `claude`, `codex`, `cursor`, `opencode`
- `InstallScope` — enum: `user`, `project`, `local`
- `MappingStatus` — fidelity tracking: `native` > `transform` > `emulate` > `fallback` > `unsupported`
- `Skill`, `Command`, `Hook`, `McpServer`, `Agent`, `LspServer` — component types
- `TextFile`, `BinaryFile` — file content carriers

## Emitters (`converters/emitters.py`)

Duck-typed classes sharing the same shape (no explicit Protocol ABC):

| Emitter | Target | Config Format | Env Var Syntax |
|---------|--------|---------------|----------------|
| `CodexEmitter` | `.codex/` | TOML (`mcp-config.toml`) | `${env:VAR}` |
| `CursorEmitter` | `.cursor/` | JSON (`mcp.json`, `hooks.json`) | `${env:VAR}` |
| `OpenCodeEmitter` | `.opencode/` | JSON (`opencode.json`, `opencode.lsp.json`) | `{env:VAR}` |

Factory: `get_emitter(target, scope, commands_as_skills) -> Emitter`

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

## Adding a New Target

1. Add enum value to `TargetTool` in `ir.py`
2. Create emitter class in `emitters.py` with `target` attr and `emit()` method
3. Register in `get_emitter()` factory
4. Create output validator in `validators/target/<tool>.py`
5. Register in `validators/target/__init__.py` → `get_output_validator()`
6. Add CLI choice in `cli.py` convert command
