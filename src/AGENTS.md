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
├── scaffold.py      # Plugin scaffold generation
├── watch.py         # File watcher for dev mode
├── adapters/        # External tool wrappers
│   └── claude.py    # Claude CLI subprocess calls
├── converters/      # Plugin conversion pipeline
│   ├── ir.py            # Tool-agnostic intermediate representation (Pydantic models)
│   ├── claude_parser.py # Claude plugin dir → PluginIR
│   ├── emitters.py      # PluginIR → target files (Codex, Cursor, OpenCode, Pi)
│   ├── convert.py       # Orchestrator (parse + emit + report)
│   └── report.py        # Structured conversion reports
└── validators/      # doctor command validation framework
    ├── base.py      # Validator protocol + result types
    ├── context.py   # Shared validation context
    ├── component/   # skill.py, hook.py, mcp.py
    ├── marketplace/ # validators.py (source type validation)
    ├── plugin/      # validators.py
    └── target/      # Output validators (codex.py, cursor.py, opencode.py, pi.py)
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
- Parse → IR → Emit architecture; see `docs/conversion-pipeline.md` for details
- Emitters use duck typing (same `emit(ir) -> EmitResult` shape) with a `get_emitter()` factory
- Diagnostic accumulation over exceptions — parsing/emitting never raises, collects `Diagnostic` objects
- `MappingStatus` tracks conversion fidelity per component (`native` → `unsupported`)

**Init wizard — Prompter protocol** (`init.py`)
- `Prompter` protocol defines `select`, `checkbox`, `text`, `confirm` methods
- `QuestionaryPrompter` is the production implementation (wraps questionary + escape binding)
- Tests inject a `ScriptedPrompter` fake — no mocking/patching of prompts needed
- `GoBack` exception + `GO_BACK` sentinel distinguish Escape (go back) from Ctrl+C (cancel)
- `run_init_wizard` uses a step-based state machine (steps 0–5); go-back decrements the step
- `_run_marketplace_loop` extracted as a helper with its own sub-step tracking

**Target output validators** (`validators/target/`)
- `CodexOutputValidator`, `CursorOutputValidator`, `OpenCodeOutputValidator`, `PiOutputValidator`
- Validate converted output structure (skills dirs, config files, naming conventions)
- Used by `ai-config doctor --target <tool> <dir>`

## Adding a New Validator

1. Create class implementing `Validator` protocol in appropriate subdir
2. Define `name` and `description` attributes
3. Implement `async def validate(self, context: ValidationContext) -> list[ValidationResult]`
4. Register in `validators/__init__.py` under the right category

Example: `validators/component/skill.py`

## Adding a New Target Emitter

See `docs/adding-a-target.md` for the full checklist (19 files). Summary:

1. Add to `TargetTool` enum in `converters/ir.py`
2. Create emitter class in `converters/emitters.py`, register in `get_emitter()` factory
3. Create validator in `validators/target/<tool>.py`, register in `__init__.py`
4. Add to `types.py` Literal + valid_targets, `cli.py` Choice lists (3 places), `init.py` target_choices
5. Add tests (unit emitter + protocol + validator + E2E), Docker install, docs

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
- E2E tests in `tests/e2e/` — see `docs/e2e-testing.md`
