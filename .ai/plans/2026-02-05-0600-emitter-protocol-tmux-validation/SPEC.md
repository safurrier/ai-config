# Emitter Protocol Refactor & Tmux-based Validation

## Problem Statement

Two architectural improvements needed for the plugin conversion system:

1. **Protocol Consistency**: Emitters use ABC inheritance while validators use Protocol (structural typing). This inconsistency makes the codebase harder to reason about and test.

2. **Validation Gap**: Current E2E tests only validate file structure, not that target tools actually recognize the converted output. We need tmux-based integration tests that launch real CLI tools and verify they load converted plugins.

## Requirements

### Protocol Refactor
- Refactor `BaseEmitter` ABC to `Emitter` Protocol
- Extract shared helpers (`_skill_to_markdown`) to module-level functions
- Maintain backward compatibility with existing tests
- Match the pattern used by validators in `ai_config/validators/base.py`

### Tmux-based Validation
- Port `TmuxTestSession` pattern from dots repo
- Create introspection tests for each target tool
- Validate each plugin component type is recognized by the tool
- Document which tools support which introspection commands

## Constraints

- Must work in Docker E2E environment (tmux available)
- Cannot require API keys for basic validation
- Should gracefully skip tests when tools aren't installed
- Tests should complete in reasonable time (<2 min per tool)

## Success Criteria

1. All emitters use Protocol pattern matching validators
2. E2E tests verify converted plugins are recognized by target CLIs
3. Clear documentation of each tool's validation capabilities
