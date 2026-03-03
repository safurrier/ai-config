---
id: adding-a-target
title: Adding a New Conversion Target
description: >
  Step-by-step guide for adding a new AI coding tool as a conversion target.
  Covers the 18-file checklist, emitter pattern, validator pattern, and verification.
index:
  - id: prerequisites
  - id: files-to-modify-checklist
  - id: emitter-pattern
  - id: validator-pattern
  - id: verification
  - id: reference-pi-implementation
---

# Adding a New Conversion Target

Step-by-step guide for adding a new AI coding tool as a conversion target. Based on the Pi target implementation.

## Prerequisites

Before starting, understand the target tool's:
- **Skill/instruction format** — where do they live, what frontmatter is expected?
- **Command/prompt format** — can commands map to something? Prompt templates?
- **Hook support** — does the tool have lifecycle hooks?
- **MCP/LSP support** — does it support MCP servers or LSP configs?
- **Config format** — JSON, YAML, TOML? Where does it go?
- **Install method** — npm, pip, curl? What's the binary name?

## Files to Modify (Checklist)

### Core (required)

| # | File | Change |
|---|------|--------|
| 1 | `src/ai_config/converters/ir.py` | Add value to `TargetTool` enum |
| 2 | `src/ai_config/converters/emitters.py` | Create emitter class, add to `get_emitter()` factory + return type |
| 3 | `src/ai_config/converters/__init__.py` | Export new emitter in imports + `__all__` |
| 4 | `src/ai_config/validators/target/<tool>.py` | Create output validator class |
| 5 | `src/ai_config/validators/target/__init__.py` | Import + register in `get_output_validator()` dict + type alias |
| 6 | `src/ai_config/types.py` | Add to `ConversionConfig.targets` Literal + `valid_targets` set |
| 7 | `src/ai_config/cli.py` | Add to 3 `click.Choice` lists (convert, doctor, doctor `target=="all"`) + the `target_list` for `"all"` in convert |
| 8 | `src/ai_config/init.py` | Add to `target_choices` in `prompt_conversion_targets()` |
| 9 | `.gitignore` | Add output directory pattern (e.g., `.pi/`) |

### Tests (required)

| # | File | Change |
|---|------|--------|
| 10 | `tests/unit/converters/test_conversion.py` | Add `Test<Tool>Emitter` class with skill, command, hook, MCP tests |
| 11 | `tests/unit/converters/test_emitter_protocol.py` | Add attribute check, include in emit loop + scope test |
| 12 | `tests/unit/validators/test_target_validators.py` | Add `Test<Tool>Validator` class + factory test + integration test |
| 13 | `tests/e2e/test_conversion.py` | Add to help assertion, all-targets test, per-target tests, doctor tests |

### Infrastructure

| # | File | Change |
|---|------|--------|
| 14 | `tests/docker/Dockerfile.all-tools` | Add install command + verification echo |

### Documentation

| # | File | Change |
|---|------|--------|
| 15 | `AGENTS.md` | Multi-tool table, gitignore note |
| 16 | `README.md` | Conversion targets table |
| 17 | `docs/conversion.md` | Target table, config fields, component mapping, options reference |
| 18 | `CHANGELOG.md` | Release entry |

## Emitter Pattern

Follow the duck-typed emitter pattern (no base class):

```python
class <Tool>Emitter:
    target = TargetTool.<TOOL>  # class attribute

    def __init__(self, scope: InstallScope = InstallScope.PROJECT):
        self.scope = scope

    def emit(self, ir: PluginIR) -> EmitResult:
        result = EmitResult(target=self.target)
        plugin_id = ir.identity.plugin_id
        # Emit each component type
        for skill in ir.skills(): self._emit_skill(result, skill, plugin_id)
        for cmd in ir.commands(): self._emit_command(result, cmd, plugin_id)
        # Mark unsupported components
        for _hook in ir.hooks():
            result.add_mapping("hook", "hooks", MappingStatus.UNSUPPORTED, notes="...")
        # ... same for mcp_servers, agents, lsp_servers
        return result
```

Use `MappingStatus.NATIVE` for 1:1 mappings, `TRANSFORM` for format changes, `UNSUPPORTED` for no equivalent.

## Validator Pattern

```python
class <Tool>OutputValidator:
    name = "<tool>_output"
    description = "Validates <Tool> converted output"

    def validate_skills(self, output_dir: Path) -> list[ValidationResult]: ...
    def validate_all(self, output_dir: Path) -> list[ValidationResult]: ...
```

Check: directory exists, required files present, frontmatter valid, required fields populated.

## Verification

```bash
# Unit tests (fast, no Docker)
uv run ruff check src/ && uv run ty check src/ && uv run pytest tests/unit/ -v

# Manual conversion test
uv run ai-config convert --plugin <path> --target <tool> --output /tmp/<tool>-test
ls -la /tmp/<tool>-test/

# E2E (requires Docker rebuild)
python tests/docker/test_in_docker.py --rebuild
uv run pytest tests/e2e/test_conversion.py -v
```

## Reference: Pi Implementation

Pi was added in v0.4.0. Key commits and decisions:
- Skills map NATIVE (Agent Skills standard, same as Claude's SKILL.md format)
- Commands map as TRANSFORM to Pi prompt templates (`.pi/prompts/<name>.md`)
- Hooks, MCP, agents, LSP all UNSUPPORTED (Pi uses TypeScript extensions instead)
- Pi requires `description` in skill frontmatter (skills without it won't load)
- Pi supports `disable-model-invocation` (part of Agent Skills standard)
