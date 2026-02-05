# Implementation Learnings

**Date**: 2026-02-04
**Branch**: `research/plugin-conversion-feasibility`

This document captures sharp edges, surprises, and recommendations discovered during the prototype implementation of the plugin conversion system.

---

## 1. Sharp Edges Discovered

### 1.1 Path Handling: Dot-Prefixed Files

**Issue**: The `lstrip("./")` method strips ALL leading dots and slashes, not just the `./` prefix.

```python
# WRONG
"./.mcp.json".lstrip("./")  # Returns "mcp.json" (lost the dot!)

# CORRECT
path = "./.mcp.json"
if path.startswith("./"):
    path = path[2:]  # Returns ".mcp.json"
```

**Impact**: Any plugin referencing dot-prefixed config files (`.mcp.json`, `.lsp.json`) would fail to load.

**Recommendation**: Always use explicit prefix removal, never `lstrip()` for path handling.

### 1.2 Skill Name Validation Differences

**Issue**: Each tool has different name constraints, but they're not all documented equally:

| Tool | Max Length | Case | Pattern |
|------|------------|------|---------|
| Claude | None documented | Any | Any |
| Codex | 100 chars | Any | Not documented |
| Cursor | 64 chars | Any | No "anthropic"/"claude", no XML |
| OpenCode | 64 chars | Lowercase only | `^[a-z0-9]+(-[a-z0-9]+)*$` |

**Impact**: Skills that work in Claude may fail validation in OpenCode due to uppercase letters or length.

**Recommendation**:
- Normalize all skill names to lowercase kebab-case during conversion
- Add warning diagnostics when name normalization occurs
- Use OpenCode's constraints as the strictest common denominator

### 1.3 Command Variable Support Varies Wildly

**Issue**: Each tool handles template variables differently:

| Tool | `$ARGUMENTS` | `$1, $2, ...` | Named vars | Shell injection |
|------|--------------|---------------|------------|-----------------|
| Claude | ✅ | ✅ | ✅ | ✅ `!command` |
| Codex | ✅ | ✅ | ✅ | ❌ |
| Cursor | ❌ | ❌ | ❌ | ❌ |
| OpenCode | ✅ | ✅ | ❌ | ✅ `!command` |

**Impact**: A Claude command like `Run tests for $1` becomes useless in Cursor.

**Recommendation**:
- Detect and warn about variable usage during conversion
- For Cursor: Replace variables with placeholder text explaining the limitation
- For OpenCode: Preserve `$ARGUMENTS` and `$N` but warn about named variables

### 1.4 Hook Event Mapping is Incomplete

**Issue**: Claude has 12 hook events, Cursor has 11, but they don't map 1:1:

| Claude Event | Cursor Equivalent | Notes |
|--------------|-------------------|-------|
| `PreToolUse` | `beforeShellExecution`, `beforeMCPExecution`, `beforeReadFile` | 1:3 mapping |
| `PostToolUse` | `afterShellExecution`, `afterMCPExecution`, `afterFileEdit` | 1:3 mapping |
| `UserPromptSubmit` | `beforeSubmitPrompt` | Direct |
| `Stop` | `stop` | Direct |
| `SessionStart` | ❌ | No equivalent |
| `SessionEnd` | ❌ | No equivalent |
| `PermissionRequest` | ❌ | No equivalent |
| `SubagentStart/Stop` | ❌ | No equivalent |
| `PreCompact` | ❌ | No equivalent |
| `Notification` | ❌ | No equivalent |

**Impact**: Hooks relying on session lifecycle or permission events cannot be converted to Cursor.

**Recommendation**:
- Generate detailed warnings for unmappable events
- Consider generating a "manual checklist" skill as fallback

### 1.5 MCP Environment Variable Syntax Differs

**Issue**: Each tool uses different syntax for environment variable references:

| Tool | Syntax | Example |
|------|--------|---------|
| Claude | `${VAR}` | `"${API_KEY}"` |
| Codex | `${VAR}` or TOML env forwarding | `env_vars = ["API_KEY"]` |
| Cursor | `${env:VAR}` | `"${env:API_KEY}"` |
| OpenCode | `{env:VAR}` | `"{env:API_KEY}"` |

**Impact**: Environment variables won't resolve correctly without syntax transformation.

**Recommendation**: Add explicit env var syntax transformation during emission. This was identified but NOT implemented in the prototype - it's a **known gap**.

### 1.6 Binary Files in Skills

**Issue**: Skills may contain binary files (images, compiled assets). The IR distinguishes TextFile vs BinaryFile, but emitters currently only handle TextFile.

**Impact**: Binary assets in skill directories would be silently dropped.

**Recommendation**:
- Add base64 encoding/decoding for BinaryFile handling
- Use file extension heuristics to detect binary vs text

---

## 2. Architecture Observations

### 2.1 Pydantic Works Well for IR

The Pydantic-based IR provides:
- **Clear validation**: Field validators catch invalid names/descriptions at parse time
- **Type safety**: Union types for components enable exhaustive matching
- **Serialization**: Built-in JSON export for debugging/logging
- **Documentation**: Field descriptions serve as schema documentation

**Minor Issue**: The existing ai-config codebase uses frozen dataclasses, not Pydantic. This creates two validation patterns. Consider migrating types.py to Pydantic for consistency.

### 2.2 Emitter Pattern is Clean

The `BaseEmitter` + tool-specific subclass pattern works well:
- Easy to add new target tools
- `EmitResult` with files + mappings + diagnostics provides complete output
- Factory function enables CLI integration

**Suggested Extension**: Add a `--dry-run` mode that shows what would be written without writing.

### 2.3 Parser/Emitter Separation is Correct

Having `ClaudePluginParser` separate from emitters allows:
- Parsing once, emitting to multiple targets
- Testing parser and emitters independently
- Adding new source formats (e.g., AgentSkills.io format) without touching emitters

---

## 3. Spec Accuracy Assessment

### 3.1 Correct in Spec

- ✅ SKILL.md format is portable across all tools
- ✅ MCP configuration is transformable
- ✅ Hooks are Claude + Cursor only
- ✅ LSP is Claude + OpenCode only
- ✅ Agents are Claude-only (not portable)

### 3.2 Needs Refinement in Spec

- ⚠️ Cursor commands don't support variables (spec implied more parity)
- ⚠️ Codex custom prompts are truly deprecated (spec noted this but could emphasize more)
- ⚠️ OpenCode command paths differ from spec (`.opencode/commands/` not mentioned in spec, but exists)

### 3.3 Missing from Spec

- ❌ Env var syntax transformation requirements
- ❌ Binary file handling in skills
- ❌ Name normalization strategies
- ❌ Version requirements for tool features (e.g., Cursor v2.4+ for skills)

---

## 4. Test Coverage Analysis

### 4.1 What's Tested

- ✅ Complete plugin parsing (all component types)
- ✅ Skill emission to all three targets
- ✅ Command emission with variable handling
- ✅ Hook transformation (Claude → Cursor)
- ✅ MCP config transformation
- ✅ LSP config transformation (OpenCode)
- ✅ Edge cases (name validation, plugin ID normalization)

### 4.2 What Needs More Testing

- ⚠️ Binary file handling (not implemented)
- ⚠️ Env var syntax transformation (not implemented)
- ⚠️ Multiple skills per plugin
- ⚠️ Nested skill directory structures
- ⚠️ Error recovery (partial failures)

---

## 5. Recommendations for Production

### 5.1 Before Release

1. **Add env var transformation** - Critical for MCP configs to work
2. **Add binary file support** - Skills often include images
3. **Add `--dry-run` mode** - Users need to preview changes
4. **Add `--validate-only` mode** - Check without emitting

### 5.2 CLI Integration

Suggested commands:

```bash
# Convert a plugin to one or more targets
ai-config convert <plugin-path> --to codex,cursor,opencode --output <dir>

# Convert and install
ai-config convert <plugin-path> --to codex --install --scope user

# Validate conversion without writing
ai-config convert <plugin-path> --to cursor --dry-run

# Show conversion report
ai-config convert <plugin-path> --to codex --report
```

### 5.3 Integration with Existing ai-config

The converter module should integrate with the existing config system:

```yaml
# .ai-config/config.yaml
version: 1
targets:
  - type: claude
    config:
      plugins:
        - id: my-plugin
          scope: user

  - type: codex
    config:
      convert_from:
        - claude:my-plugin  # Auto-convert from Claude plugin
```

This would enable `ai-config sync` to automatically convert and install plugins across tools.

---

## 6. Files Created in This Spike

```
src/ai_config/converters/
├── __init__.py        # Module exports
├── ir.py              # Pydantic IR models (618 lines)
├── claude_parser.py   # Claude plugin parser (520 lines)
└── emitters.py        # Target emitters (650 lines)

tests/unit/converters/
├── __init__.py
└── test_conversion.py # 24 tests, all passing

tests/fixtures/sample-plugins/complete-plugin/
├── .claude-plugin/plugin.json
├── skills/code-review/SKILL.md
├── skills/test-writer/SKILL.md
├── commands/commit.md
├── agents/security-reviewer.md
├── hooks/hooks.json
├── .mcp.json
├── .lsp.json
└── scripts/check-dangerous-commands.sh
```

**Total new code**: ~1,800 lines of implementation + ~400 lines of tests

---

## 7. Conclusion

The prototype validates that the spec is **implementable** and the conversion approach is **sound**. The main surprises were:

1. Path handling edge cases (dot-prefixed files)
2. Greater variance in command variable support than expected
3. Env var syntax differences not called out in spec

The core value proposition - **skills are highly portable** - is confirmed. A production implementation should prioritize:

1. Skills + MCP conversion (highest value)
2. Commands with proper variable handling
3. Hooks for Claude ↔ Cursor
4. Comprehensive diagnostics for users
