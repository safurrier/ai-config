# Add a conversion target

Use this guide to add an AI coding tool as a conversion target. The Pi target is the reference implementation.

## Prerequisites

Identify the target tool's:

- skill and instruction format, including locations and frontmatter
- command and prompt format, including prompt templates
- hook support
- Model Context Protocol (MCP) and Language Server Protocol (LSP) support
- configuration format and location
- install method and binary name

## Files to change

### Core requirements

| # | File | Change |
|---|---|---|
| 1 | `src/ai_config/converters/ir.py` | Add a `TargetTool` enum value. |
| 2 | `src/ai_config/converters/emitters.py` | Create the emitter and add it to the `get_emitter()` factory and return type. |
| 3 | `src/ai_config/converters/__init__.py` | Export the emitter in the imports and `__all__`. |
| 4 | `src/ai_config/validators/target/<tool>.py` | Create the output validator. |
| 5 | `src/ai_config/validators/target/__init__.py` | Import and register the validator in `get_output_validator()` and its type alias. |
| 6 | `src/ai_config/types.py` | Add the target to `ConversionConfig.targets` and `valid_targets`. |
| 7 | `src/ai_config/cli.py` | Add it to the three `click.Choice` lists and the convert `target_list` for `"all"`. |
| 8 | `src/ai_config/init.py` | Add it to `target_choices` in `prompt_conversion_targets()`. |
| 9 | `.gitignore` | Add the output directory pattern, such as `.pi/`. |

### Required tests

| # | File | Change |
|---|---|---|
| 10 | `tests/unit/converters/test_conversion.py` | Add `Test<Tool>Emitter` tests for skills, commands, hooks, and MCP. |
| 11 | `tests/unit/converters/test_emitter_protocol.py` | Check its attribute, include it in the emit loop, and test scope. |
| 12 | `tests/unit/validators/test_target_validators.py` | Add `Test<Tool>Validator`, factory, and integration tests. |
| 13 | `tests/e2e/test_conversion.py` | Add help, all-target, per-target, and doctor tests. |

### Infrastructure

| # | File | Change |
|---|---|---|
| 14 | `tests/docker/Dockerfile.all-tools` | Add installation and verification commands. |

### Documentation

| # | File | Change |
|---|---|---|
| 15 | `AGENTS.md`, `.gitignore` | Update the project summary's target list and add target-specific generated paths to `.gitignore` when needed. |
| 16 | `README.md` | Update the conversion-target table. |
| 17 | `docs/conversion.md` | Update the target table, configuration fields, component mapping, and option reference. |
| 18 | `CHANGELOG.md` | Add the release entry. |

## Emitter pattern

Use the duck-typed emitter pattern. Don't add a base class.

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

Use `MappingStatus.NATIVE` for one-to-one mappings, `TRANSFORM` for format changes and `UNSUPPORTED` when the tool has no equivalent.

## Validator pattern

```python
class <Tool>OutputValidator:
    name = "<tool>_output"
    description = "Validates <Tool> converted output"

    def validate_skills(self, output_dir: Path) -> list[ValidationResult]: ...
    def validate_all(self, output_dir: Path) -> list[ValidationResult]: ...
```

Check that the directory exists, required files exist, frontmatter is valid, and required fields have values.

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

## Pi reference implementation

Pi arrived in v0.4.0. Its design made these decisions:

- Skills map as `NATIVE` through the Agent Skills `SKILL.md` format.
- Commands map as `TRANSFORM` to Pi prompt templates in `.pi/prompts/<name>.md`.
- Hooks map as `EMULATE` to generated Pi TypeScript extensions for supported command hooks. MCP, agents, and LSP remain `UNSUPPORTED`.
- Pi requires `description` in skill frontmatter. Skills without it don't load.
- Pi supports `disable-model-invocation` from the Agent Skills standard.
