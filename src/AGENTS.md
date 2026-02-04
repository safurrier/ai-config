# ai-config Source Code

Implementation of the declarative plugin manager for Claude Code.

## Module Overview

```
ai_config/
├── cli.py           # Click commands (entry point)
├── config.py        # YAML config loading + validation
├── operations.py    # sync/update/status business logic
├── init.py          # Interactive setup wizard
├── types.py         # Frozen dataclasses for config schema
├── watch.py         # File watcher for dev mode
├── adapters/        # External tool wrappers
│   └── claude.py    # Claude CLI subprocess calls
└── validators/      # doctor command validation framework
    ├── base.py      # Validator protocol + result types
    ├── context.py   # Shared validation context
    ├── component/   # skill.py, hook.py, mcp.py
    ├── marketplace/ # validators.py
    ├── plugin/      # validators.py
    └── target/      # claude.py
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

## Adding a New Validator

1. Create class implementing `Validator` protocol in appropriate subdir
2. Define `name` and `description` attributes
3. Implement `async def validate(self, context: ValidationContext) -> list[ValidationResult]`
4. Register in `validators/__init__.py` under the right category

Example: `validators/component/skill.py`

## Adding a New CLI Command

1. Add `@cli.command()` function in `cli.py`
2. Use `@click.option()` for flags, keep Click layer thin
3. Business logic goes in `operations.py` or dedicated module
4. Use `cli_render.py` for Rich output formatting

## Testing Conventions

- Unit tests mirror source structure: `tests/unit/test_<module>.py`
- Test frozen dataclasses with valid and invalid inputs
- Test validators with mock `ValidationContext`
- Integration tests in `tests/integration/` (marked, may need fixtures)
