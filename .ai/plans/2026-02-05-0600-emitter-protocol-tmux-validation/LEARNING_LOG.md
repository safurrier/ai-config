# Learning Log

## 2026-02-05: Plan Created

### Context
Created plan for emitter protocol refactor and tmux-based validation after discussion about:
1. Inconsistency between emitters (ABC) and validators (Protocol)
2. Gap in E2E tests - not actually validating with target tool CLIs
3. Prior art in dots repo for tmux-based testing

### Key Findings

**Protocol vs ABC:**
- Validators use `Protocol` from `typing` with `@runtime_checkable`
- Protocol is more Pythonic - structural typing, no inheritance required
- ABC requires inheritance, more Java-like
- Shared implementation can be module-level functions instead of inherited methods

**Existing tmux testing in dots:**
- `TmuxTestSession` class handles session lifecycle
- `wait_for_output()` with timeout/polling pattern
- Tests Claude, Codex, OpenCode setup and basic functionality
- Validates symlinks, config files, version commands

**Command support in emitters:**
- All three emitters have `_emit_command()` methods
- Codex emits to `prompts/` (deprecated format)
- Cursor emits to `.cursor/commands/`
- OpenCode emits to `.opencode/commands/`
- Need to verify these locations are actually read by tools

### Open Questions

1. Does Codex still support `prompts/` or only skills now?
2. What introspection commands does each tool support?
3. Can we validate MCP server loading without API keys?
4. How do we handle tools that have no CLI introspection?

### Next Steps

Start with Phase 2 (tool introspection research) to understand what's actually testable before implementing tmux infrastructure.

---

## Future entries will be added as work progresses
