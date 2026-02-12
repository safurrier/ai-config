# Plugin Conversion Feasibility Research Report

**Date**: 2026-02-04
**Branch**: `research/plugin-conversion-feasibility`
**Objective**: Validate feasibility of Claude Code Plugin Conversion to Codex, Cursor, and OpenCode

---

## Executive Summary

The spec describes a plugin conversion tool that transforms Claude Code plugins into equivalent artifacts for Codex, Cursor, and OpenCode. After thorough research across all four tool ecosystems, **the spec is fundamentally sound and feasible**, with several refinements recommended.

### Key Findings

| Aspect | Assessment | Confidence |
|--------|------------|------------|
| Skills conversion | **Highly feasible** - All 4 tools use compatible SKILL.md format | High |
| Commands conversion | **Feasible with transforms** - Different file formats but similar semantics | Medium-High |
| Hooks conversion | **Partially feasible** - Claude + Cursor have hooks; Codex/OpenCode need fallbacks | Medium |
| MCP conversion | **Feasible** - All tools support MCP with config transforms | High |
| LSP conversion | **Limited** - Only Claude + OpenCode support custom LSP | Medium |
| Agents conversion | **Not portable** - Only Claude has first-class agents | Low |

### Recommendation: **Proceed with implementation**, prioritizing skills and MCP conversion first.

---

## 1. Architecture Alignment with ai-config

The existing ai-config codebase provides excellent extension points for this capability:

### 1.1 Current Architecture Strengths

| Component | Assessment |
|-----------|------------|
| **Adapter pattern** (`adapters/claude.py`) | Readily extendable to new tools |
| **Validator framework** (`validators/`) | Protocol-based, async - perfect for validation steps |
| **Type system** (`types.py`) | Frozen dataclasses work well; could add Pydantic for complex validation |
| **Config parsing** | YAML-based, can define multi-target configs |
| **E2E Docker infrastructure** | Already supports multi-tool testing (Claude, Codex, OpenCode, Cursor) |

### 1.2 Recommended Extensions

```
src/ai_config/
├── converters/                 # NEW - Conversion logic
│   ├── base.py                # Converter protocol
│   ├── ir.py                  # Pydantic IR models from spec
│   ├── claude_parser.py       # Parse Claude plugins → IR
│   ├── codex_emitter.py       # IR → Codex artifacts
│   ├── cursor_emitter.py      # IR → Cursor artifacts
│   └── opencode_emitter.py    # IR → OpenCode artifacts
├── adapters/
│   ├── claude.py              # Existing
│   ├── codex.py               # NEW - Codex CLI wrapper
│   ├── cursor.py              # NEW - Cursor CLI wrapper
│   └── opencode.py            # NEW - OpenCode CLI wrapper
└── validators/
    ├── target/
    │   ├── claude.py          # Existing
    │   ├── codex.py           # NEW
    │   ├── cursor.py          # NEW
    │   └── opencode.py        # NEW
    └── conversion/            # NEW - Post-conversion validators
        └── validators.py
```

---

## 2. Component-by-Component Analysis

### 2.1 Skills - Highly Portable ✅

**Key Discovery**: All four tools use **nearly identical** SKILL.md format with YAML frontmatter.

| Tool | Path | Format | Frontmatter |
|------|------|--------|-------------|
| Claude | `.claude/skills/<name>/SKILL.md` | Markdown + YAML | `name`, `description`, many optional |
| Codex | `.codex/skills/<name>/SKILL.md` | Markdown + YAML | `name`, `description` required |
| Cursor | `.cursor/skills/<name>/SKILL.md` | Markdown + YAML | `name`, `description` required |
| OpenCode | `.opencode/skills/<name>/SKILL.md` | Markdown + YAML | `name`, `description` required |

**Conversion Strategy**: Direct copy with path adjustment. May need to:
1. Strip Claude-specific frontmatter fields (`context`, `agent`, `model`, `hooks`)
2. Validate name constraints (OpenCode: 64 chars max, lowercase only)
3. Validate description length (OpenCode/Cursor: 1024 chars max)

**Spec Accuracy**: ✅ Correct that skills are native across all tools

### 2.2 Commands - Portable with Transforms ⚠️

| Tool | Path | Format | Features |
|------|------|--------|----------|
| Claude | Plugin `commands/` | Markdown + frontmatter | `$ARGUMENTS`, description |
| Codex | `~/.codex/prompts/` (deprecated) | Markdown + frontmatter | `$1-$9`, `$ARGUMENTS`, named placeholders |
| Cursor | `.cursor/commands/` | Plain Markdown | No variables, static content |
| OpenCode | `.opencode/commands/` | Markdown + frontmatter | `$ARGUMENTS`, `$1-$N`, shell injection |

**Key Insight**: Cursor commands are **static Markdown** with no variable interpolation. Arguments are appended as context, not substituted.

**Conversion Strategy**:
- Claude → Codex: Nearly 1:1, mark as deprecated
- Claude → Cursor: Strip frontmatter, note limitations
- Claude → OpenCode: Direct, preserve template syntax

**Spec Accuracy**: ⚠️ Needs refinement - Cursor commands are simpler than spec suggests

### 2.3 Hooks - Limited Portability ⚠️

| Tool | Support | Format | Events |
|------|---------|--------|--------|
| Claude | **Native** | `hooks.json` | 12 events, command/prompt/agent handlers |
| Codex | **None** | N/A | N/A |
| Cursor | **Native** | `hooks.json` | 11 events, command handlers only |
| OpenCode | **None** (plugins exist) | N/A | N/A |

**Key Discovery**: Claude and Cursor share similar hook concepts but with differences:

| Claude Event | Cursor Equivalent |
|--------------|-------------------|
| `PreToolUse` | `beforeShellExecution`, `beforeMCPExecution`, `beforeReadFile` |
| `PostToolUse` | `afterShellExecution`, `afterMCPExecution`, `afterFileEdit` |
| `UserPromptSubmit` | `beforeSubmitPrompt` |
| `Stop` | `stop` |
| `SessionStart` | (none) |

**Conversion Strategy**:
- Claude → Cursor: Map events, convert handler format
- Claude → Codex/OpenCode: Generate fallback skill with hook logic as checklist

**Spec Accuracy**: ✅ Correct about Codex/OpenCode limitations

### 2.4 MCP Servers - Good Portability ✅

All tools support MCP with different config formats:

| Tool | Config | Format | Notes |
|------|--------|--------|-------|
| Claude | `.mcp.json` or plugin inline | JSON | `mcpServers.<name>.command/args/env` |
| Codex | `~/.codex/config.toml` | TOML | `[mcp_servers.<name>]` section |
| Cursor | `.cursor/mcp.json` | JSON | `mcpServers.<name>` with `type` field |
| OpenCode | `opencode.json` | JSON | `mcp.<name>` with `type: local/remote` |

**Conversion Strategy**: Schema transformation, all support stdio transport:

```python
# Claude → Codex (JSON → TOML)
{
  "mcpServers": {
    "myserver": {"command": "node", "args": ["server.js"]}
  }
}
# becomes
[mcp_servers.myserver]
command = "node"
args = ["server.js"]
```

**Spec Accuracy**: ✅ Correct

### 2.5 LSP Servers - Limited Portability ⚠️

| Tool | Support | Config |
|------|---------|--------|
| Claude | Native | `.lsp.json` - `command`, `extensionToLanguage` |
| Codex | **None** | N/A |
| Cursor | **None** (Editor handles LSP) | N/A |
| OpenCode | Native | `opencode.json` lsp section - `command`, `extensions` |

**Conversion Strategy**:
- Claude → OpenCode: Schema transform (similar structure)
- Claude → Codex/Cursor: Skip with diagnostic

**Spec Accuracy**: ✅ Correct

### 2.6 Agents - Not Portable ❌

Only Claude has first-class agent definitions. Other tools:
- Codex: No equivalent (skills can be complex but not "agents")
- Cursor: "Multi-agents" are internal, not user-defined
- OpenCode: Agents are internal configurations, not user-defined files

**Conversion Strategy**: Skip with diagnostic, or convert to skill as degraded alternative.

**Spec Accuracy**: ✅ Correct that agents are unsupported

---

## 3. Validation Architecture Assessment

### 3.1 CLI-Based Validation

| Tool | CLI Validation Available | Commands |
|------|-------------------------|----------|
| Claude | Yes | `claude plugin validate`, `claude --debug` |
| Codex | Limited | `codex mcp list`, `codex login status` |
| Cursor | None | No validation CLI |
| OpenCode | Limited | `opencode mcp list`, `opencode mcp debug` |

**Key Discovery**: Cursor lacks any CLI validation. The spec's TUI-based validation steps are necessary.

### 3.2 Recommended Validation Steps

```python
# Refined validation step types
class ValidationMethod(Enum):
    CLI = "cli"           # Fully automated via command
    FILESYSTEM = "fs"     # Check files exist with expected content
    TUI_MANUAL = "tui"    # Requires user interaction (with tmux automation option)
```

**Spec Accuracy**: ✅ TUI validation approach is correct

### 3.3 Docker + tmux Feasibility

The spec's Docker + tmux validation harness is feasible for:
- Codex: `/` slash command menu is terminal-based
- Claude: `--debug` output is capturable
- OpenCode: TUI-based, tmux can send keystrokes

**Not feasible** for:
- Cursor: Electron-based, not terminal-accessible

---

## 4. Gaps and Issues in Spec

### 4.1 Corrections Needed

| Section | Issue | Correction |
|---------|-------|------------|
| §3.2.2 | Custom prompts path | Should be `~/.codex/prompts/` not `~/.codex/prompts/` (directory, top-level only) |
| §6 Mapping | Cursor commands | Mark as "transform" not "native" - no variable substitution |
| §7.3 | Command emission | Cursor commands are plain markdown, no frontmatter parsing |
| §9.2 X4 | Codex skills path | Primary path is `.codex/skills/` not `.agents/skills/` |

### 4.2 Missing Information

1. **Codex skill discovery precedence**: Needs explicit priority order (CWD > parent > repo root > user > admin > system)
2. **Cursor version gating**: Skills require v2.4+; hooks require v1.7+
3. **OpenCode Claude compatibility**: OpenCode also searches `.claude/skills/` for compatibility

### 4.3 Spec Improvements

1. **Add version requirements table**:
   | Tool | Minimum Version | Features |
   |------|-----------------|----------|
   | Cursor | v2.4 | Skills |
   | Cursor | v1.7 | Hooks |
   | Codex | Current | All features |
   | OpenCode | Current | All features |

2. **Add scope-to-path mapping table** for clarity

3. **Expand fallback strategies** for hooks on Codex/OpenCode

---

## 5. Alternative Designs Considered

### 5.1 Alternative: Direct File Copy with Config Templates

Instead of IR-based conversion:
- Pros: Simpler, less abstraction
- Cons: Loses validation opportunity, harder to maintain

**Verdict**: Spec's IR approach is better for maintainability and diagnostics

### 5.2 Alternative: Runtime Shim Layers

Create a "compatibility shim" that wraps each tool:
- Pros: Single plugin format everywhere
- Cons: Runtime overhead, fragile, tool-dependent

**Verdict**: Static conversion (spec approach) is more reliable

### 5.3 Alternative: AgentSkills.io Universal Format

Use the AgentSkills.io specification as the universal IR:
- Pros: Industry-emerging standard, OpenCode already supports it
- Cons: Skills-only, doesn't cover hooks/MCP/commands

**Verdict**: Could use AgentSkills.io for skills subset, keep full IR for other components

### 5.4 Alternative: Plugin-as-a-Service

Host converted plugins in a registry service:
- Pros: Always up-to-date conversions
- Cons: Requires infrastructure, network dependency

**Verdict**: Out of scope for this tool, but could be future extension

---

## 6. Implementation Recommendations

### 6.1 Phased Approach

**Phase 1: Skills + MCP** (Highest Value, Lowest Risk)
- Skills: Near-identical format across tools
- MCP: Config transformation only
- Timeline: Start here for quick wins

**Phase 2: Commands + Hooks**
- Commands: Handle Cursor's limitations
- Hooks: Claude ↔ Cursor mapping
- Timeline: After Phase 1 validates approach

**Phase 3: LSP + Validation Harness**
- LSP: Claude → OpenCode only
- Docker + tmux automation
- Timeline: Nice-to-have

### 6.2 Key Design Decisions

1. **Use Pydantic for IR** (as spec suggests) - existing codebase doesn't use it but benefits from validation
2. **Preserve file trees** - don't flatten skills, maintain directory structure
3. **Emit diagnostics always** - even for "native" mappings, report what was done
4. **Install manifest pattern** - track every file written for clean uninstall

### 6.3 Integration with ai-config

The converter should integrate as:

```yaml
# .ai-config/config.yaml extension
version: 1
targets:
  - type: claude
    config:
      plugins:
        - id: my-plugin
          scope: user

  - type: codex       # NEW
    config:
      convert_from:
        - claude:my-plugin
      skills:
        - scope: user

  - type: cursor      # NEW
    config:
      convert_from:
        - claude:my-plugin
      commands:
        - scope: project
```

### 6.4 CLI Extension

```bash
# New commands
ai-config convert my-plugin --to codex,cursor,opencode --output ./converted/
ai-config convert my-plugin --to codex --scope user --install
ai-config validate --target codex --plugin converted/my-plugin
```

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Tool API changes | Medium | High | Version pinning, graceful degradation |
| Incomplete hook mapping | High | Medium | Clear fallback documentation |
| Cursor GUI-only features | Medium | Low | Mark as TUI-manual validation |
| User confusion on scope | Medium | Medium | Clear error messages, validation |

---

## 8. Conclusion

The spec is **well-researched and feasible**. The core insight - that skills are highly portable across all four tools - is correct and represents the highest-value conversion target.

### Summary of Spec Assessment

| Section | Status |
|---------|--------|
| §1-2 Purpose & Principles | ✅ Sound |
| §3 Component Research | ⚠️ Minor corrections needed |
| §4-5 IR Design | ✅ Good approach |
| §6 Mapping Matrix | ⚠️ Cursor commands need adjustment |
| §7 Emission Rules | ⚠️ Cursor specifics need refinement |
| §8-9 Validation | ✅ Well-designed |
| §10 Docker/tmux | ⚠️ Cursor not feasible |
| §11-12 Deliverables & Gaps | ✅ Appropriate scope |

### Recommended Next Steps

1. **Create implementation plan** based on phased approach
2. **Build skills converter first** - high value, low risk proof of concept
3. **Add to existing ai-config** - use adapter and validator patterns
4. **Write E2E tests** using existing Docker infrastructure

---

## Appendix A: Authoritative Sources Used

### Claude Code
- https://code.claude.com/docs/en/plugins
- https://code.claude.com/docs/en/plugins-reference
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/skills

### Codex
- https://developers.openai.com/codex/skills
- https://developers.openai.com/codex/mcp
- https://developers.openai.com/codex/cli/reference
- https://developers.openai.com/codex/custom-prompts (deprecated)

### Cursor
- https://cursor.com/docs
- https://cursor.com/changelog
- https://forum.cursor.com

### OpenCode
- https://opencode.ai/docs/skills
- https://opencode.ai/docs/commands
- https://opencode.ai/docs/mcp-servers
- https://opencode.ai/docs/lsp
- https://agentskills.io/specification

---

## Appendix B: File Path Reference

### Skills
| Tool | Project | User |
|------|---------|------|
| Claude | `.claude/skills/<name>/SKILL.md` | `~/.claude/skills/<name>/SKILL.md` |
| Codex | `.codex/skills/<name>/SKILL.md` | `~/.codex/skills/<name>/SKILL.md` |
| Cursor | `.cursor/skills/<name>/SKILL.md` | `~/.cursor/skills/<name>/SKILL.md` |
| OpenCode | `.opencode/skills/<name>/SKILL.md` | `~/.config/opencode/skills/<name>/SKILL.md` |

### Commands
| Tool | Project | User |
|------|---------|------|
| Claude | Plugin `commands/` dir | N/A (plugin-scoped) |
| Codex | N/A | `~/.codex/prompts/<name>.md` (deprecated) |
| Cursor | `.cursor/commands/<name>.md` | `~/.cursor/commands/<name>.md` |
| OpenCode | `.opencode/commands/<name>.md` | `~/.config/opencode/commands/<name>.md` |

### MCP
| Tool | Project | User |
|------|---------|------|
| Claude | `.mcp.json` or inline | `~/.claude/settings.json` |
| Codex | `.codex/config.toml` | `~/.codex/config.toml` |
| Cursor | `.cursor/mcp.json` | `~/.cursor/mcp.json` |
| OpenCode | `opencode.json` | `~/.config/opencode/opencode.json` |

### Hooks
| Tool | Project | User |
|------|---------|------|
| Claude | Plugin `hooks.json` | N/A |
| Codex | N/A | N/A |
| Cursor | `.cursor/hooks.json` | `~/.cursor/hooks.json` |
| OpenCode | N/A | N/A |
