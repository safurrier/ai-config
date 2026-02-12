# Implementation Plan

## Prior Art Reference

The tmux-based E2E testing pattern comes from the dots repository:
- **File**: `/Users/alex.furrier/git_repositories/dots/tests/e2e/ai_tools/test_ai_tools_e2e.py`
- **Key class**: `TmuxTestSession` - manages tmux sessions for testing
- **Skill reference**: `/Users/alex.furrier/git_repositories/dots/config/ai-config/plugins/alex-ai/skills/interacting-with-tmux/SKILL.md`

## Phase 1: Emitter Protocol Refactor

### 1.1 Define Emitter Protocol

```python
# src/ai_config/converters/protocol.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class Emitter(Protocol):
    """Protocol for plugin emitters."""

    target: TargetTool
    scope: InstallScope

    def emit(self, ir: PluginIR) -> EmitResult:
        """Emit the IR to target format."""
        ...
```

### 1.2 Extract Shared Helpers

Move `_skill_to_markdown` to module-level function:

```python
# src/ai_config/converters/emitters.py

def skill_to_markdown(skill: Skill, strip_claude_fields: bool = True) -> str:
    """Convert a skill to SKILL.md format."""
    # ... existing implementation
```

### 1.3 Refactor Emitter Classes

- Remove ABC inheritance
- Add explicit `target` and `scope` attributes
- Update to use module-level helpers
- Ensure they satisfy `Emitter` protocol

## Phase 2: Tool Introspection Research

### 2.1 Research Each Tool's CLI Capabilities

Create test scripts that exercise each tool to discover:
- How to list installed skills
- How to list MCP servers
- How to validate config without API key
- Error messages when config is invalid

### 2.2 Component Support Matrix

| Component | Claude | Codex | Cursor | OpenCode |
|-----------|--------|-------|--------|----------|
| Skills | ✓ `/skills` | ✓ `skills/` dir | ✓ `skills/` dir | ✓ `skills/` dir |
| Commands | ✓ `/commands` | ⚠ prompts (deprecated) | ✓ `commands/` | ✓ `commands/` |
| Hooks | ✓ `hooks.json` | ✗ Not supported | ✓ `hooks.json` | ✗ Not supported |
| MCP | ✓ `mcp.json` | ✓ `config.toml` | ✓ `mcp.json` | ✓ `opencode.json` |
| LSP | ✗ | ✗ | ✗ (internal) | ✓ `opencode.lsp.json` |
| Agents | ✓ | ✗ | ✗ | ✗ |

### 2.3 Introspection Commands (Researched 2026-02-05)

**Claude Code:**
```bash
claude --version                    # Verify installed
claude plugin list                  # List installed plugins with status
claude mcp list                     # List MCP servers with health check
claude plugin validate <path>       # Validate plugin manifest
# Skills/commands visible via /skills, /commands in session
```
- Config: `~/.claude/` (plugins, settings.json, mcp.json)
- MCP: `mcp.json` or per-plugin MCP servers
- No direct skill listing CLI (file-based discovery)

**Codex:**
```bash
codex --version                     # Verify installed
codex mcp list                      # List configured MCP servers
codex features list                 # List feature flags and status
# No config show command - uses ~/.codex/config.toml
```
- Config: `~/.codex/config.toml` (TOML format)
- MCP: configured via `codex mcp add`
- Skills: `~/.codex/skills/` directory (symlink supported)
- Prompts: `~/.codex/prompts/` directory (deprecated but still works)

**Cursor:**
```bash
cursor-agent --version              # Verify installed
cursor-agent mcp list               # List MCP servers from mcp.json
cursor-agent mcp list-tools <name>  # List tools for specific MCP
cursor-agent status                 # Check authentication status
# Limited introspection - mostly file-based validation
```
- Config: `~/.cursor/` or `.cursor/`
- MCP: `mcp.json` (project or user level)
- Skills: No dedicated skill discovery CLI
- Hooks: `hooks.json` (file-based only)
- Note: `cursor-agent ls` requires interactive terminal

**OpenCode:**
```bash
opencode --version                  # Verify installed
opencode mcp list                   # List MCP servers with status
opencode agent list                 # List all agents with permissions
opencode debug skill                # List available skills (returns [])
opencode debug config               # Show resolved configuration (JSON)
opencode debug paths                # Show global paths (data, config, cache)
```
- Config: `~/.config/opencode/opencode.json` (JSON format)
- MCP: configured in opencode.json or via `opencode mcp add`
- Skills: `~/.config/opencode/skills/` (symlink supported)
- Commands: `~/.config/opencode/command/` (symlink supported)
- Agents: `~/.config/opencode/agent/` (symlink supported)

### 2.4 Key Validation Strategies

| Tool | MCP Validation | Skill Validation | Config Validation |
|------|----------------|------------------|-------------------|
| Claude | `claude mcp list` | File check + plugin list | `claude plugin validate` |
| Codex | `codex mcp list` | File check | TOML parse check |
| Cursor | `cursor-agent mcp list` | File check | JSON parse check |
| OpenCode | `opencode mcp list` | `opencode debug skill` | `opencode debug config` |

## Phase 3: Tmux Test Infrastructure

### 3.1 Port TmuxTestSession

Create `tests/e2e/tmux_helper.py`:

```python
class TmuxTestSession:
    """Manages a tmux test session for E2E testing."""

    def __init__(self, session_name: str):
        self.session_name = session_name
        self.session_active = False

    def create_session(self, working_dir: str | None = None) -> None:
        """Create a new tmux session."""

    def send_keys(self, keys: str, enter: bool = True) -> None:
        """Send keys to the tmux session."""

    def capture_pane(self, scrollback: int = 100) -> str:
        """Capture the current pane content."""

    def wait_for_output(self, expected: str, timeout: float = 10.0) -> bool:
        """Wait for expected output to appear in the pane."""

    def cleanup(self) -> None:
        """Clean up the tmux session."""
```

### 3.2 Create Tool Validation Tests

```python
# tests/e2e/test_tool_validation.py

@pytest.mark.e2e
@pytest.mark.requires_tmux
class TestCodexValidation:
    """Validate Codex recognizes converted plugins."""

    def test_codex_starts_with_converted_skills(self, tmux_session):
        """Test Codex starts without errors after conversion."""
        # Convert plugin to Codex format
        # Start Codex in tmux
        # Verify no errors on startup
        # Check skill files are accessible

    def test_codex_mcp_config_loads(self, tmux_session):
        """Test Codex loads MCP configuration."""
        # Convert plugin with MCP servers
        # Start Codex
        # Verify MCP servers are registered
```

## Phase 4: Missing Command Support

### Current State

All three emitters have `_emit_command()` methods:
- **Codex**: Emits as deprecated prompts to `prompts/<name>.md`
- **Cursor**: Emits to `commands/<name>.md` (no variable support)
- **OpenCode**: Emits to `commands/<name>.md`

### Gaps to Address

1. **Codex prompts location**: Currently emits to `prompts/` which is deprecated. Research current Codex command/skill format.

2. **OpenCode command discovery**: Verify OpenCode actually reads from `commands/` directory.

3. **Command variable handling**: Document which tools support `$ARGUMENTS` and positional vars.

## Phase 5: Integration & Documentation

### 5.1 Update Docker Images

Ensure E2E Docker images have:
- tmux installed
- All AI tools available
- Test plugins pre-converted for validation

### 5.2 CI Integration

Add tmux-based tests to CI workflow:
- Install tmux in CI environment
- Run validation tests with extended timeout
- Report which tools passed/failed validation

### 5.3 Documentation

Update PR description and docs with:
- Validation coverage per tool
- Known limitations
- How to add new tool validators
