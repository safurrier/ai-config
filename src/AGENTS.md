# ai-config Source Code

Implementation of the declarative plugin manager and cross-tool converter.

## Module Overview

```
ai_config/
├── cli.py           # Click commands (entry point)
├── config.py        # YAML config loading + validation
├── operations.py    # sync/update/status + sync-driven conversion
├── init.py          # Interactive setup wizard
├── types.py         # Frozen dataclasses for config schema
├── watch.py         # File watcher for dev mode
├── adapters/        # External tool wrappers
│   └── claude.py    # Claude CLI subprocess calls
├── converters/      # Plugin conversion pipeline
│   ├── ir.py            # Tool-agnostic intermediate representation (Pydantic models)
│   ├── claude_parser.py # Claude plugin dir → PluginIR
│   ├── emitters.py      # PluginIR → target files (Codex, Cursor, OpenCode)
│   ├── convert.py       # Orchestrator (parse + emit + report)
│   └── report.py        # Structured conversion reports
└── validators/      # doctor command validation framework
    ├── base.py      # Validator protocol + result types
    ├── context.py   # Shared validation context
    ├── component/   # skill.py, hook.py, mcp.py
    ├── marketplace/ # validators.py (source type validation)
    ├── plugin/      # validators.py
    └── target/      # Output validators (codex.py, cursor.py, opencode.py)
```

## Key Patterns

**Frozen dataclasses for config** (`types.py`)
- All config types use `@dataclass(frozen=True)` for immutability
- Validation in `__post_init__` with clear error messages
- Use `tuple` for collections (not `list`) in frozen dataclasses

**Validator protocol** (`validators/base.py`)
- Validators implement `Validator` protocol with async `validate()` method
- Return `list[ValidationResult]` with status: `"pass"`, `"warn"`, or `"fail"`
- Include `fix_hint` when failures are actionable
- Validators run concurrently via `asyncio.gather()`

**Error hierarchy** (`config.py`)
- `ConfigError` base → `ConfigNotFoundError`, `ConfigParseError`, `ConfigValidationError`
- Parse errors include context (index, field name, valid options)

**CLI adapter pattern** (`adapters/claude.py`)
- Wraps `claude` CLI subprocess calls
- Parses JSON output, handles errors uniformly
- Never raises raw subprocess exceptions

**Converter pipeline** (`converters/`)
- Parse → IR → Emit architecture; see `ai_agent_docs/conversion-pipeline.md` for details
- Emitters use duck typing (same `emit(ir) -> EmitResult` shape) with a `get_emitter()` factory
- Diagnostic accumulation over exceptions — parsing/emitting never raises, collects `Diagnostic` objects
- `MappingStatus` tracks conversion fidelity per component (`native` → `unsupported`)

**Target output validators** (`validators/target/`)
- `CodexOutputValidator`, `CursorOutputValidator`, `OpenCodeOutputValidator`
- Validate converted output structure (skills dirs, config files, naming conventions)
- Used by `ai-config doctor --target <tool> <dir>`

## Adding a New Validator

1. Create class implementing `Validator` protocol in appropriate subdir
2. Define `name` and `description` attributes
3. Implement `async def validate(self, context: ValidationContext) -> list[ValidationResult]`
4. Register in `validators/__init__.py` under the right category

Example: `validators/component/skill.py`

## Adding a New Target Emitter

1. Create a class in `converters/emitters.py` with `target: TargetTool` and `emit(ir: PluginIR) -> EmitResult`
2. Add to the `get_emitter()` factory function
3. Create matching validator in `validators/target/<tool>.py`
4. Add to `get_output_validator()` in `validators/target/__init__.py`
5. Add CLI target choice in `cli.py` convert command

## Adding a New CLI Command

1. Add `@cli.command()` function in `cli.py`
2. Use `@click.option()` for flags, keep Click layer thin
3. Business logic goes in `operations.py` or dedicated module
4. Use `cli_render.py` for Rich output formatting

## Testing Conventions

- Unit tests mirror source structure: `tests/unit/test_<module>.py`
- Converter tests in `tests/unit/converters/test_conversion.py` and `test_emitter_protocol.py`
- Test frozen dataclasses with valid and invalid inputs
- Test validators with mock `ValidationContext`
- Integration tests in `tests/integration/` (marked, may need fixtures)
- E2E tests in `tests/e2e/` — see `ai_agent_docs/e2e-testing.md`
