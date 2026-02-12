# Implementation Plan v2 - Plugin Conversion

**Date**: 2026-02-04
**Status**: Planning
**Branch**: `research/plugin-conversion-feasibility`

---

## Scope Clarification

### What's Done (from v1)

1. ✅ Core IR with Pydantic models
2. ✅ Claude plugin parser (source is always Claude plugins)
3. ✅ Emitters for Codex, Cursor, OpenCode
4. ✅ Conversion reports (JSON, Markdown, summary)
5. ✅ Dry-run support
6. ✅ Best-effort mode
7. ✅ CLI `convert` command
8. ✅ Unit tests (34 tests)
9. ✅ Basic E2E test infrastructure

### What's In Scope (v2)

1. **Target-specific validators** - Extend validator system to validate converted output
2. **Init wizard integration** - Add conversion target selection after plugin selection
3. **E2E validation with tool CLIs** - Validate converted output using actual tool CLIs in Docker
4. **Doctor command extension** - `ai-config doctor --target cursor ./output-dir`

### What's Deferred

1. ❌ Multi-source parsing (Codex→Claude, Cursor→Claude) - Only Claude as source
2. ❌ Env var syntax transformation - Known gap, document workaround
3. ❌ Binary file handling - Warn and skip
4. ❌ `ai-config sync` auto-conversion - Future feature

---

## Implementation Tasks

### Phase 1: Research Tool CLIs

**Goal**: Understand what validation is possible for each target tool

| Tool | Questions to Answer |
|------|---------------------|
| Codex | Does `codex` CLI exist? Can it list skills? What's the config format? |
| Cursor | Does `cursor-agent` expose skills/commands? How to validate hooks.json? |
| OpenCode | Does `opencode` CLI have validation commands? What's the expected structure? |

**Research Tasks**:
- [ ] Check locally installed tools: `which codex`, `which cursor-agent`, `which opencode`
- [ ] Run `--help` on each to find relevant commands
- [ ] Check tool documentation for config file schemas
- [ ] Determine minimum validation possible (file structure vs CLI verification)

### Phase 2: Target Validators

**Goal**: Create validators for each target tool's output format

```
src/ai_config/validators/
├── __init__.py
├── marketplace.py      # existing
├── plugin.py           # existing
├── skill.py            # existing (Claude skills)
├── hook.py             # existing (Claude hooks)
├── mcp.py              # existing (Claude MCP)
├── codex.py            # NEW - Codex output validation
├── cursor.py           # NEW - Cursor output validation
└── opencode.py         # NEW - OpenCode output validation
```

**Each validator checks**:
- File structure (directories exist, files present)
- File format (valid JSON/TOML/YAML)
- Schema compliance (required fields, valid values)
- Optional: CLI verification if tool supports it

### Phase 3: Doctor Command Extension

**Goal**: Allow `ai-config doctor` to validate converted output

```bash
# Validate Claude plugin (existing)
ai-config doctor

# Validate Codex output (new)
ai-config doctor --target codex ./output-dir

# Validate all targets
ai-config doctor --target all ./output-dir
```

**Implementation**:
- Add `--target` option to doctor command
- Route to target-specific validators
- Reuse existing report rendering

### Phase 4: Init Wizard Integration

**Goal**: Add conversion prompt after plugin selection

**Flow**:
```
1. Select marketplaces
2. Select plugins
3. NEW: "Convert to other tools?" → Yes/No
4. NEW: If yes, select targets (Codex, Cursor, OpenCode)
5. NEW: Select output directory
6. Write config
7. NEW: Run conversion if requested
```

**User might**:
- Only want Claude plugins (no conversion)
- Want Claude + Cursor conversion
- Want conversion to all targets

### Phase 5: E2E Tests with Tool Validation

**Goal**: Validate converted output actually works with target tools

**Test Strategy**:
1. Convert sample plugin to each target
2. Run target-specific validators
3. If tool CLI available, verify tool recognizes the output
4. Check specific files contain expected content

**Docker Image Requirements**:
- Claude Code: Already installed
- Codex: `npm install -g @openai/codex` (may not exist yet)
- Cursor: `curl -fsSL https://cursor.com/install | bash`
- OpenCode: `npm install -g opencode-ai`

---

## Research Findings (2026-02-04)

### Tool CLI Availability ✅

All three tools are installed and have CLIs:
- **Codex**: `codex` (aliased to `npx @openai/codex`)
- **Cursor**: `cursor-agent`
- **OpenCode**: `opencode`

### Configuration Locations

| Tool | Skills | Commands | MCP | Hooks |
|------|--------|----------|-----|-------|
| Codex | `.codex/skills/` | `.codex/prompts/` (deprecated) | `config.toml` | ❌ |
| Cursor | `.cursor/skills/` | `.cursor/commands/` | `mcp.json` | `hooks.json` |
| OpenCode | `.opencode/skills/` | `.opencode/commands/` | `opencode.json` | ❌ |

### SKILL.md Format (Shared - agentskills.io)

All three tools use the same SKILL.md format:
```yaml
---
name: skill-name          # Required: lowercase kebab-case, max 64 chars
description: ...          # Required: max 1024 chars
license: ...              # Optional
allowed-tools: [...]      # Optional (Claude-specific, stripped for others)
metadata: {...}           # Optional
---
Instructions in markdown...
```

**Key difference**: OpenCode enforces stricter name validation: `^[a-z0-9]+(-[a-z0-9]+)*$`

### MCP Configuration Differences

| Aspect | Codex | Cursor | OpenCode |
|--------|-------|--------|----------|
| Format | TOML | JSON | JSON |
| Location | `config.toml` | `mcp.json` | `opencode.json` |
| Server key | `[mcp_servers.name]` | `mcpServers.name` | `mcp.name` |
| Command | `command = "..."` | `"command": "..."` | `"command": ["..."]` (array) |
| Args | `args = [...]` | `"args": [...]` | Part of command array |
| Env vars | `env = {...}` | `"env": {...}` | `"environment": {...}` |
| Env syntax | `${VAR}` | `${env:VAR}` | `{env:VAR}` |

### Hooks (Cursor Only)

**hooks.json schema**:
```json
{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [{ "command": "...", "args": [], "timeoutMs": 3000 }],
    "afterShellExecution": [...],
    "beforeMCPExecution": [...],
    "afterMCPExecution": [...],
    "beforeReadFile": [...],
    "afterFileEdit": [...],
    "beforeSubmitPrompt": [...],
    "stop": [...]
  }
}
```

### CLI Validation Commands

| Tool | Command | Purpose |
|------|---------|---------|
| Codex | `codex mcp list` | List configured MCP servers |
| Codex | `codex mcp list --json` | JSON output for parsing |
| OpenCode | `opencode mcp list` | List MCP servers and status |
| OpenCode | `opencode agent list` | List configured agents |
| Cursor | Limited CLI | No skill/command listing |

**Key insight**: Only Codex and OpenCode have CLI commands for listing configs. Cursor validation will be file-based only.

---

## Validation Matrix

| Target | File Validation | Schema Validation | CLI Validation |
|--------|-----------------|-------------------|----------------|
| Codex | ✅ Check `.codex/` paths | ✅ TOML format | ✅ `codex mcp list --json` |
| Cursor | ✅ Check `.cursor/` paths | ✅ JSON schemas | ❌ File-based only |
| OpenCode | ✅ Check `.opencode/` paths | ✅ JSON format | ✅ `opencode mcp list` |

---

## Decisions Made

### 1. Nested Skills Misunderstanding

The "nested skill directories" feature was a misunderstanding. Skills are NOT nested in categories. Instead, skills have **internal** `resources/` and `scripts/` directories:

```
skills/my-skill/
├── SKILL.md
├── resources/     # Reference docs within the skill
└── scripts/       # Helper scripts within the skill
```

The existing implementation correctly handles this via `rglob("*")` which collects all files within a skill directory. The test fixture named "nested-skill" is misleading and should be renamed or removed.

### 2. Source is Always Claude

ai-config manages Claude plugins. The conversion feature converts FROM Claude TO other tools. Users select which targets they want (Codex, Cursor, OpenCode, or any subset).

### 3. Validators Enable Both Doctor and E2E

By implementing target validators, we get:
- `ai-config doctor --target X` for users
- Reusable validation logic for E2E tests
- Consistent error reporting

---

## Next Steps

1. ~~**Research tool CLIs**~~ ✅ Complete
2. ~~**Update plan**~~ ✅ Complete
3. **Implement validators** - Create CodexValidator, CursorValidator, OpenCodeValidator
4. **Extend doctor** command with `--target` option
5. **Add wizard integration** - Conversion prompt after plugin selection
6. **Write E2E tests** - Use validators + CLI checks in Docker

---

## Open Questions (Resolved)

1. ~~Does Codex CLI even exist publicly?~~ → **Yes**, `codex` works via `npx @openai/codex`
2. ~~What's the Cursor CLI binary name?~~ → **`cursor-agent`**
3. ~~Does OpenCode have any validation commands?~~ → **Yes**, `opencode mcp list`, `opencode agent list`
4. ~~Should we support validating against JSON schemas?~~ → **Yes**, file-based validation for Cursor since no skill listing CLI

---

## Implementation Order

### Phase 1: Target Validators (Estimated: 2-3 hours)

Create three new validator modules:

```python
# src/ai_config/validators/targets/codex.py
class CodexValidator:
    def validate_skills(output_dir: Path) -> ValidationReport
    def validate_mcp(output_dir: Path) -> ValidationReport
    def validate_via_cli(output_dir: Path) -> ValidationReport  # Uses `codex mcp list --json`

# src/ai_config/validators/targets/cursor.py
class CursorValidator:
    def validate_skills(output_dir: Path) -> ValidationReport
    def validate_commands(output_dir: Path) -> ValidationReport
    def validate_hooks(output_dir: Path) -> ValidationReport  # JSON schema check
    def validate_mcp(output_dir: Path) -> ValidationReport

# src/ai_config/validators/targets/opencode.py
class OpenCodeValidator:
    def validate_skills(output_dir: Path) -> ValidationReport
    def validate_commands(output_dir: Path) -> ValidationReport
    def validate_mcp(output_dir: Path) -> ValidationReport
    def validate_via_cli(output_dir: Path) -> ValidationReport  # Uses `opencode mcp list`
```

### Phase 2: Doctor Extension (Estimated: 1 hour)

```bash
# New CLI options
ai-config doctor --target codex ./output-dir
ai-config doctor --target cursor ./output-dir
ai-config doctor --target opencode ./output-dir
ai-config doctor --target all ./output-dir
```

### Phase 3: Init Wizard (Estimated: 1-2 hours)

Add to `run_init_wizard()`:
1. After plugin selection, prompt: "Convert plugins to other tools?"
2. If yes, show checkbox: Codex, Cursor, OpenCode
3. Run conversion after config write

### Phase 4: E2E Tests (Estimated: 2-3 hours)

```python
# tests/e2e/test_conversion_validation.py
class TestConversionValidation:
    def test_codex_output_valid(container):
        # Convert, then run codex mcp list --json, check output

    def test_cursor_output_valid(container):
        # Convert, then validate file structure + JSON schemas

    def test_opencode_output_valid(container):
        # Convert, then run opencode mcp list, check output
```
