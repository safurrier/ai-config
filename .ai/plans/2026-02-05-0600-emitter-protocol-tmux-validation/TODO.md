# TODO: Emitter Protocol Refactor & Tmux Validation

## Phase 1: Emitter Protocol Refactor ✅

- [x] **1.1 Create Emitter Protocol**
  - [x] Add Protocol pattern in `src/ai_config/converters/emitters.py`
  - [x] Match pattern from `src/ai_config/validators/base.py`
  - [x] Use `@runtime_checkable` decorator

- [x] **1.2 Extract Shared Helpers**
  - [x] Move `_skill_to_markdown()` to module-level `skill_to_markdown()`
  - [x] Update all emitters to use the module-level function
  - [x] Remove ABC inheritance from emitter classes

- [x] **1.3 Update Emitter Classes**
  - [x] Refactor `CodexEmitter` to satisfy Protocol
  - [x] Refactor `CursorEmitter` to satisfy Protocol
  - [x] Refactor `OpenCodeEmitter` to satisfy Protocol
  - [x] Update type hints in `get_emitter()` factory

- [x] **1.4 Update Tests**
  - [x] Add Protocol conformance tests (18 new tests)
  - [x] Verify existing tests still pass (476 total)
  - [x] Add test for structural typing (duck typing works)

## Phase 2: Tool Introspection Research

### 2.1 Claude Code Introspection

- [ ] **Research Claude CLI commands**
  - [ ] Test `claude mcp list` (or equivalent)
  - [ ] Test `claude plugin list` (if available)
  - [ ] Document skill/command visibility via `/skills`, `/commands`
  - [ ] Find config validation command (if any)

### 2.2 Codex CLI Introspection

- [ ] **Research Codex CLI commands**
  - [ ] Test `codex --version`
  - [ ] Test `codex config` commands
  - [ ] Test `codex skills` commands (if available)
  - [ ] Document MCP server visibility
  - [ ] Verify prompts vs skills directory structure

### 2.3 Cursor CLI Introspection

- [ ] **Research Cursor CLI commands**
  - [ ] Test `cursor-agent --version`
  - [ ] Test config validation commands
  - [ ] Document skill/command discovery mechanism
  - [ ] Test hooks.json loading verification

### 2.4 OpenCode CLI Introspection

- [ ] **Research OpenCode CLI commands**
  - [ ] Test `opencode --version`
  - [ ] Test `opencode config` commands
  - [ ] Test MCP server listing
  - [ ] Test LSP server listing
  - [ ] Verify commands directory reading

### 2.5 Document Findings

- [ ] **Create tool capabilities matrix**
  - [ ] Fill in actual introspection commands per tool
  - [ ] Document error messages for invalid config
  - [ ] Note which validations require API keys

## Phase 3: Tmux Test Infrastructure ✅

- [x] **3.1 Port TmuxTestSession**
  - [x] Create `tests/e2e/tmux_helper.py`
  - [x] Implement `create_session()`, `send_keys()`, `capture_pane()`
  - [x] Implement `wait_for_output()` with timeout
  - [x] Add `cleanup()` for teardown
  - [x] Reference: `dots/tests/e2e/ai_tools/test_ai_tools_e2e.py`

- [x] **3.2 Create Fixtures**
  - [x] `@pytest.fixture` for tmux session with cleanup
  - [x] `@pytest.mark.requires_tmux` marker
  - [x] Skip logic when tmux not available

- [ ] **3.3 Update Docker Images**
  - [ ] Add `tmux` to `Dockerfile.claude-only`
  - [ ] Add `tmux` to `Dockerfile.all-tools`
  - [ ] Verify tmux works in container

## Phase 4: Tool Validation Tests

### 4.1 Component Validation Checklist

**For each tool (Codex, Cursor, OpenCode), validate:**

#### Skills Validation
- [ ] **Codex**: Skills in `.codex/skills/` recognized
- [ ] **Cursor**: Skills in `.cursor/skills/` recognized
- [ ] **OpenCode**: Skills in `.opencode/skills/` recognized

#### Commands Validation
- [ ] **Codex**: Prompts in `prompts/` or commands recognized
- [ ] **Cursor**: Commands in `.cursor/commands/` recognized
- [ ] **OpenCode**: Commands in `.opencode/commands/` recognized

#### MCP Validation
- [ ] **Codex**: `mcp-config.toml` parsed correctly
- [ ] **Cursor**: `mcp.json` parsed correctly
- [ ] **OpenCode**: `opencode.json` MCP section parsed correctly

#### Hooks Validation
- [ ] **Cursor**: `hooks.json` loaded and events registered

#### LSP Validation
- [ ] **OpenCode**: `opencode.lsp.json` loaded correctly

### 4.2 Create Test Classes

- [x] `TestCodexValidation` - Codex tool integration (scaffold created)
- [x] `TestCursorValidation` - Cursor tool integration (scaffold created)
- [x] `TestOpenCodeValidation` - OpenCode tool integration (scaffold created)
- [x] `TestCrossToolValidation` - Same plugin works across tools (scaffold created)

## Phase 5: Gap Analysis & Fixes

### 5.1 Command/Prompt Support Gaps

- [ ] **Verify Codex command format**
  - [ ] Research current Codex skill vs prompt format
  - [ ] Update emitter if prompts are fully deprecated
  - [ ] Test that emitted commands are discoverable

- [ ] **Verify OpenCode command format**
  - [ ] Confirm OpenCode reads `commands/` directory
  - [ ] Test command frontmatter requirements
  - [ ] Update emitter if format differs

### 5.2 Missing Component Support

- [ ] **Audit all IR components vs emitters**
  - [ ] `Skill` - All emitters ✓
  - [ ] `Command` - All emitters ✓ (verify format)
  - [ ] `Hook` - Cursor ✓, others warn
  - [ ] `McpServer` - All emitters ✓
  - [ ] `Agent` - None supported (warn)
  - [ ] `LspServer` - OpenCode ✓

## Phase 6: Documentation & CI

- [x] **6.1 Update PR description**
  - [x] Add validation coverage matrix
  - [x] Document tmux test requirements
  - [x] Note known limitations per tool

- [ ] **6.2 Update CLAUDE.md**
  - [ ] Add E2E tmux test instructions
  - [ ] Document tool introspection commands

- [ ] **6.3 CI Updates**
  - [ ] Ensure tmux available in CI
  - [ ] Add tmux tests to E2E workflow
  - [ ] Set appropriate timeouts

## Notes

### Prior Art Locations

- **TmuxTestSession**: `~/git_repositories/dots/tests/e2e/ai_tools/test_ai_tools_e2e.py`
- **Tmux skill**: `~/git_repositories/dots/config/ai-config/plugins/alex-ai/skills/interacting-with-tmux/`
- **Validator Protocol**: `src/ai_config/validators/base.py:40` (`class Validator(Protocol)`)

### Key tmux Commands

```bash
# Create session
tmux new-session -d -s <name> -c <working_dir>

# Send keys
tmux send-keys -t <session> "command" Enter

# Capture output
tmux capture-pane -t <session> -p -S -100

# Kill session
tmux kill-session -t <session>
```
