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

## Phase 2: Tool Introspection Research ✅

### 2.1 Claude Code Introspection ✅

- [x] **Research Claude CLI commands**
  - [x] Test `claude mcp list` - Lists MCP servers with health check
  - [x] Test `claude plugin list` - Lists installed plugins with status
  - [x] Document skill/command visibility via `/skills`, `/commands`
  - [x] Found `claude plugin validate <path>` for config validation

### 2.2 Codex CLI Introspection ✅

- [x] **Research Codex CLI commands**
  - [x] Test `codex --version` - Works
  - [x] Test `codex mcp list` - Lists configured MCP servers
  - [x] Test `codex features list` - Lists feature flags
  - [x] Document MCP server visibility
  - [x] Verified: skills in `~/.codex/skills/`, prompts in `~/.codex/prompts/`

### 2.3 Cursor CLI Introspection ✅

- [x] **Research Cursor CLI commands**
  - [x] Test `cursor-agent --version` - Works
  - [x] Test `cursor-agent mcp list` - Lists MCP from mcp.json
  - [x] Test `cursor-agent mcp list-tools <name>` - Lists tools for MCP
  - [x] Document hooks.json loading verification (file-based only)
  - [x] Note: `cursor-agent ls` requires interactive terminal

### 2.4 OpenCode CLI Introspection ✅

- [x] **Research OpenCode CLI commands**
  - [x] Test `opencode --version` - Works
  - [x] Test `opencode mcp list` - Lists MCP servers
  - [x] Test `opencode agent list` - Lists agents with permissions
  - [x] Test `opencode debug skill` - Lists available skills
  - [x] Test `opencode debug config` - Shows resolved config (JSON)
  - [x] Test `opencode debug paths` - Shows global paths

### 2.5 Document Findings ✅

- [x] **Create tool capabilities matrix** - Added to IMPLEMENTATION.md
  - [x] Fill in actual introspection commands per tool
  - [x] Document error messages for invalid config
  - [x] Note which validations require API keys (none for basic validation)

## Phase 3: Tmux Test Infrastructure ✅

- [x] **3.1 Port TmuxTestSession**
  - [x] Create `tests/e2e/tmux_helper.py`
  - [x] Implement `create_session()`, `send_keys()`, `capture_pane()`
  - [x] Implement `wait_for_output()` with timeout
  - [x] Add `cleanup()` for teardown
  - [x] Reference: `dots/tests/e2e/ai_tools/test_ai_tools_e2e.py`

- [x] **3.2 Create Fixtures**
  - [x] `@pytest.fixture` for tmux session with cleanup
  - [x] Changed to fail loudly if tmux unavailable (not skip)
  - [x] Added `_require_tmux()` helper

- [x] **3.3 Verify Docker Images**
  - [x] Confirmed `tmux` in `Dockerfile.claude-only` (line 19)
  - [x] Confirmed `tmux` in `Dockerfile.all-tools` (line 28)
  - [x] Verified tmux works in container: `tmux 3.4`

## Phase 4: Tool Validation Tests ✅

### 4.1 Component Validation Tests

**Claude Code:**
- [x] `test_claude_version_check` - Verify installation
- [x] `test_claude_plugin_list_command` - Test plugin list
- [x] `test_claude_mcp_list_command` - Test MCP list

**Codex:**
- [x] `test_codex_version_check` - Verify installation
- [x] `test_codex_skills_directory_recognized` - Skills in `.codex/skills/`
- [x] `test_codex_mcp_config_valid_toml` - Valid TOML syntax
- [x] `test_codex_mcp_list_command` - Test `codex mcp list`
- [x] `test_codex_features_list_command` - Test `codex features list`

**Cursor:**
- [x] `test_cursor_agent_version_check` - Verify installation
- [x] `test_cursor_skills_directory_recognized` - Skills in `.cursor/skills/`
- [x] `test_cursor_hooks_json_valid` - Valid JSON syntax
- [x] `test_cursor_mcp_json_valid` - Valid JSON syntax
- [x] `test_cursor_mcp_list_command` - Test `cursor-agent mcp list`

**OpenCode:**
- [x] `test_opencode_version_check` - Verify installation
- [x] `test_opencode_skills_directory_recognized` - Skills in `.opencode/skills/`
- [x] `test_opencode_json_valid` - Valid JSON syntax
- [x] `test_opencode_mcp_list_command` - Test `opencode mcp list`
- [x] `test_opencode_debug_config_command` - Test `opencode debug config`
- [x] `test_opencode_debug_paths_command` - Test `opencode debug paths`

### 4.2 Cross-Tool Validation Tests ✅

- [x] `test_convert_to_all_targets_produces_valid_output` - All targets produce valid dirs
- [x] `test_doctor_validates_each_target` - Doctor validates with JSON output

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
  - [x] `Skill` - All emitters ✓
  - [ ] `Command` - All emitters ✓ (verify format)
  - [x] `Hook` - Cursor ✓, others warn
  - [x] `McpServer` - All emitters ✓
  - [x] `Agent` - None supported (warn)
  - [x] `LspServer` - OpenCode ✓

## Phase 6: Documentation & CI

- [x] **6.1 Update PR description**
  - [x] Add validation coverage matrix
  - [x] Document tmux test requirements
  - [x] Note known limitations per tool

- [ ] **6.2 Update CLAUDE.md**
  - [ ] Add E2E tmux test instructions
  - [ ] Document tool introspection commands

- [ ] **6.3 CI Updates**
  - [x] Tmux already available in Docker images
  - [ ] Add tmux tests to E2E workflow
  - [ ] Set appropriate timeouts

## Summary

**Completed:**
- Phase 1: Emitter Protocol Refactor ✅
- Phase 2: Tool Introspection Research ✅
- Phase 3: Tmux Test Infrastructure ✅
- Phase 4: Tool Validation Tests ✅
- Phase 6.1: PR Description Update ✅

**Remaining (future work):**
- Phase 5: Gap Analysis & Fixes
- Phase 6.2-6.3: CLAUDE.md & CI Updates

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

### Introspection Commands Summary

| Tool | Version | MCP List | Config/Debug |
|------|---------|----------|--------------|
| Claude | `claude --version` | `claude mcp list` | `claude plugin list` |
| Codex | `codex --version` | `codex mcp list` | `codex features list` |
| Cursor | `cursor-agent --version` | `cursor-agent mcp list` | N/A (file-based) |
| OpenCode | `opencode --version` | `opencode mcp list` | `opencode debug config` |
