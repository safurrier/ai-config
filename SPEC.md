# SPEC.md — Claude Code Plugin Conversion + Validation for Claude Code, Codex, Cursor, OpenCode

## 1) Purpose

Create a tool that:
1. Ingests a Claude Code plugin (the Claude "plugin bundle" format).
2. Normalizes it into a Pydantic-based Intermediate Representation (IR).
3. Emits equivalent artifacts to one or more targets:
   - Claude Code
   - OpenAI Codex (Codex CLI / IDE extension surfaces)
   - Cursor
   - OpenCode
4. Provides a post-conversion validator that can verify (via CLI where available, otherwise via TUI/UX steps) that each exported component is installed and functional.

This spec is intentionally explicit about:
- Component taxonomy
- On-disk locations and scope layers (only when supported by primary sources)
- What can be validated automatically vs what requires interactive confirmation

---

## 2) Design constraints and principles

### 2.1 Reliability over "perfect equivalence"

Some primitives exist in one tool but not another (notably hooks). The converter must support degradation policies and produce a report that states exactly what was mapped, emulated, or dropped.

### 2.2 Target surfaces vary (bundle vs split features)

Claude Code plugins are a single installable bundle with multiple component types. Other tools typically split functionality across:
- skills directories
- command/prompt directories
- hooks/event systems (if present)
- MCP config files (TOML/JSON/etc.)

Claude Code plugin system details and component schemas are defined in the official Plugins Reference and "Create plugins" docs.

---

## 3) Research: component model and supported target surfaces

### 3.1 Claude Code (source format)

#### 3.1.1 Plugin layout
Claude plugins are defined by plugin.json and can include component directories at the plugin root (e.g., skills/, commands/, agents/, hooks/, plus MCP/LSP definitions), with an explicit warning that only plugin.json goes inside .claude-plugin/ and component directories live at the plugin root.

#### 3.1.2 What components Claude plugins can contain
Claude plugin components include:
- Skills
- Commands
- Hooks
- Agents
- MCP servers
- LSP servers
(all defined by schemas and documented in the Plugins Reference).

#### 3.1.3 Debug and validation tooling
Claude provides developer tooling in the plugin system:
- `claude plugin validate` (and UI equivalents referenced in plugin documentation)
- `claude --debug` to see plugin loading, registration, and initialization details (including MCP initialization per plugin debug expectations)

Note: This spec does not assume a "list installed plugins" CLI exists as a stable command, because the authoritative plugin reference emphasizes validate/debug/installation surfaces rather than a guaranteed enumeration command.

---

### 3.2 OpenAI Codex (Codex CLI / IDE surfaces)

#### 3.2.1 Slash commands / interactive control
Codex provides a slash-command popup during interactive sessions. This is the primary "TUI validation" channel for capabilities like status and MCP visibility.

#### 3.2.2 Custom prompts (deprecated) — tightened
Codex supports "Custom Prompts" as top-level Markdown files invocable as slash commands, but they are deprecated in favor of skills. Custom prompts live under `~/.codex/prompts/` (top-level Markdown files only) and are invoked as `/prompts:<name>`. The converter may still emit these as an optional output, but must mark them as legacy/deprecated.

#### 3.2.3 Agent Skills (first-class)
Codex supports Agent Skills as reusable packages (instructions/resources/optional scripts) and positions them as the preferred reusable mechanism.

---

### 3.3 Cursor

#### 3.3.1 Commands
Cursor supports project commands by creating a `.cursor/commands` directory with Markdown files.

#### 3.3.2 Agent Skills
Cursor supports "Agent Skills" as portable packages that can include instructions and executable elements; this is documented as a first-class "skills" feature.

#### 3.3.3 Hooks
Cursor supports hooks as external processes that interact with the agent loop (stdio + JSON protocol) and documents the hooks system.

---

### 3.4 OpenCode

#### 3.4.1 Agent Skills
OpenCode supports Agent Skills via SKILL.md definitions and a native skill tool that loads them on demand.

#### 3.4.2 Config directory override
OpenCode supports overriding the config directory via `OPENCODE_CONFIG_DIR` and searches that directory for agents/commands/modes/plugins similarly to `.opencode`.

#### 3.4.3 Native skills provenance
OpenCode's skills support is explicitly described as native (graduated from a plugin into core support), providing confidence that "skills" are a stable surface.

Note: This spec does not hardcode an "official skill listing debug command" for OpenCode because the authoritative docs shown here focus on skills behavior and configuration, not a guaranteed `opencode debug skill` CLI surface.

---

## 4) Canonical component taxonomy (IR-level)

The converter normalizes a Claude plugin into these component kinds:
- Skill
- Command
- Hook
- MCP server
- Agent
- LSP server
- Arbitrary files (pass-through payload)

This matches Claude's plugin reference categories for plugin contents.

---

## 5) Intermediate Representation (Pydantic schema)

### 5.1 Pydantic types (authoritative schema for the tool)

```python
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class TargetTool(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"
    CURSOR = "cursor"
    OPENCODE = "opencode"


class InstallScope(str, Enum):
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"  # uncommitted machine-local where supported


class ComponentKind(str, Enum):
    SKILL = "skill"
    COMMAND = "command"
    HOOK = "hook"
    MCP_SERVER = "mcp_server"
    AGENT = "agent"
    LSP_SERVER = "lsp_server"
    FILE = "file"


class MappingStatus(str, Enum):
    NATIVE = "native"
    TRANSFORM = "transform"
    EMULATE = "emulate"
    FALLBACK = "fallback"
    UNSUPPORTED = "unsupported"


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class EvidenceType(str, Enum):
    CLI = "cli"
    TUI = "tui"
    FILESYSTEM = "filesystem"
    LOG = "log"


class Diagnostic(BaseModel):
    severity: Severity
    message: str
    component_ref: Optional[str] = None  # e.g. "skill:my-skill"


class PluginIdentity(BaseModel):
    plugin_id: str = Field(..., description="Stable ID for namespacing")
    name: str
    version: Optional[str] = None
    description: Optional[str] = None


class TextFile(BaseModel):
    relpath: str
    content: str
    executable: bool = False


class BinaryFile(BaseModel):
    relpath: str
    content_b64: str
    executable: bool = False


AnyFile = Union[TextFile, BinaryFile]


class Skill(BaseModel):
    kind: Literal[ComponentKind.SKILL] = ComponentKind.SKILL
    name: str
    scope_hint: InstallScope = InstallScope.USER
    entrypoint: str = "SKILL.md"
    files: List[AnyFile] = Field(default_factory=list)


class Command(BaseModel):
    kind: Literal[ComponentKind.COMMAND] = ComponentKind.COMMAND
    name: str
    scope_hint: InstallScope = InstallScope.USER
    markdown: str


class HookHandlerType(str, Enum):
    COMMAND = "command"
    PROMPT = "prompt"


class HookHandler(BaseModel):
    type: HookHandlerType
    command: Optional[str] = None
    prompt: Optional[str] = None
    timeout_sec: Optional[int] = None


class HookEvent(BaseModel):
    # Canonical event names follow Claude's hook event taxonomy.
    name: str
    matcher: Optional[str] = None
    handlers: List[HookHandler] = Field(default_factory=list)


class Hook(BaseModel):
    kind: Literal[ComponentKind.HOOK] = ComponentKind.HOOK
    scope_hint: InstallScope = InstallScope.USER
    events: List[HookEvent] = Field(default_factory=list)


class McpTransport(str, Enum):
    STDIO = "stdio"
    HTTP = "http"
    STREAMING_HTTP = "streaming_http"


class McpServer(BaseModel):
    kind: Literal[ComponentKind.MCP_SERVER] = ComponentKind.MCP_SERVER
    name: str
    scope_hint: InstallScope = InstallScope.USER
    transport: McpTransport
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    cwd: Optional[str] = None


class Agent(BaseModel):
    kind: Literal[ComponentKind.AGENT] = ComponentKind.AGENT
    name: str
    scope_hint: InstallScope = InstallScope.USER
    markdown: str


class LspServer(BaseModel):
    kind: Literal[ComponentKind.LSP_SERVER] = ComponentKind.LSP_SERVER
    name: str
    scope_hint: InstallScope = InstallScope.USER
    config: Dict[str, Any] = Field(default_factory=dict)


Component = Union[Skill, Command, Hook, McpServer, Agent, LspServer]


class PluginIR(BaseModel):
    identity: PluginIdentity
    components: List[Component] = Field(default_factory=list)
    diagnostics: List[Diagnostic] = Field(default_factory=list)
```

### 5.2 Canonicalization rules
- Treat Claude's SKILL.md-based skills as the canonical "skill" primitive across all targets that support skills (Codex/Cursor/OpenCode all document skills).
- Use Claude hook event names as canonical in IR (Claude defines these in the plugin reference); targets may translate to their event systems where feasible.
- Preserve original file trees in skills whenever possible; do not flatten unless a target forces it (e.g., legacy prompts).

---

## 6) Mapping matrix (component × target × status)

Statuses:
- **native**: direct representation exists
- **transform**: config/schema conversion required
- **emulate**: implement as a plugin/hook wrapper mechanism
- **fallback**: degrade to a prompt/command/flattened file
- **unsupported**: no documented equivalent in target surfaces

| Component | Claude Code | Codex | Cursor | OpenCode |
|-----------|-------------|-------|--------|----------|
| Skill | native (Claude plugin skills) | native (skills are preferred; custom prompts deprecated) | native (Agent Skills) | native (Agent Skills + skill tool) |
| Command | native (plugin commands exist, though skills are recommended) | fallback/transform (emit deprecated custom prompts optionally) | native (.cursor/commands) | native (OpenCode supports markdown-backed commands in .opencode/commands/ and ~/.config/opencode/commands/; optionally also supports JSON-defined commands in config). |
| Hook | native (Claude hooks in plugin system) | unsupported (no documented first-class hook surface in the cited Codex docs) | native (Cursor hooks) | emulate (OpenCode has plugins; implement hook-like behavior via plugins if needed, but this spec does not claim a specific hook event API beyond what OpenCode documents as plugin/config extensibility) |
| MCP server | native (Claude plugin MCP support) | transform (Codex uses slash-command UX and configuration; MCP is a supported surface) | transform (Cursor supports MCP) | native/transform (OpenCode supports MCP; config directory overridable) |
| Agent | native (Claude plugin agents) | unsupported (no documented matching file schema in cited sources) | unsupported | unsupported |
| LSP | native (Claude plugin LSP servers) | unsupported | unsupported | transform (OpenCode supports LSP configuration via the lsp section in opencode.json, including custom LSP servers by command + extensions). |

---

## 7) Emission rules (what the converter writes)

### 7.1 Core output conventions
- Use a deterministic namespace prefix derived from `plugin_id` for all emitted assets to prevent collisions.
- Maintain an install manifest recording every file write so uninstall is deterministic (especially for targets without a bundle lifecycle).

### 7.2 Skill emission
- Prefer skills as the universal export mechanism when possible (Codex recommends skills for reusable prompts; OpenCode and Cursor also support skills).
- Preserve the skill directory file tree; only transform metadata if the target requires additional frontmatter keys (not assumed by this spec unless a primary source demands it).

### 7.3 Command emission
- **Cursor**: emit project commands under `.cursor/commands/<plugin_id>-<command>.md`.
- **Codex**: optionally emit legacy custom prompts, marked deprecated in output and in diagnostics.
- **OpenCode**: emit markdown commands under `.opencode/commands/<plugin_id>-<command>.md` (project scope) or `~/.config/opencode/commands/` (user scope). Use YAML frontmatter for metadata when needed (description/agent/model). Alternatively (optional), emit JSON-defined commands into opencode.json under command.

### 7.4 Hooks emission
- **Claude**: emit hooks as Claude plugin hooks per schema.
- **Cursor**: emit Cursor hooks (implementation requires Cursor hook configuration schema; Cursor documents the hooks subsystem but this spec does not hardcode file formats beyond what's explicitly documented).
- **Codex**: hooks are unsupported; generate a fallback skill/command describing the hook logic as a manual checklist.

### 7.5 MCP emission
- Convert Claude plugin MCP entries to each target's MCP configuration surface.
- For OpenCode, allow `OPENCODE_CONFIG_DIR` support: emit into the selected config directory, so validation can be done against that directory.

### 7.6 LSP emission (OpenCode)

Convert Claude LSP entries to OpenCode's `opencode.json` lsp map. For each server, set `command` and `extensions`; carry over environment variables and initialization options where representable. OpenCode supports custom LSP servers via `lsp.<name>.command` and `lsp.<name>.extensions`.

---

## 8) Validation: run-after-conversion checks

### 8.1 Validator architecture

The tool emits a set of `ValidationSteps`, then runs them to produce a `ValidationReport`.
- Prefer CLI checks.
- Use TUI/UX checks only where CLI enumeration is not documented.
- Each step must record:
  - command or UI steps
  - expected output (substring/regex)
  - captured evidence (stdout/stderr/screenshot/text capture)
  - pass/fail/skip

### 8.2 Validator Pydantic models

```python
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class CheckResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"

class ValidationStep(BaseModel):
    id: str
    target: TargetTool
    scope: InstallScope
    component_kind: ComponentKind
    component_name: Optional[str] = None
    evidence_type: EvidenceType
    command: Optional[str] = None
    tui_steps: Optional[List[str]] = None
    expected: str
    notes: Optional[str] = None

class ValidationEvidence(BaseModel):
    captured_stdout: Optional[str] = None
    captured_stderr: Optional[str] = None
    files_checked: List[str] = Field(default_factory=list)
    extra: Dict[str, str] = Field(default_factory=dict)

class ValidationRecord(BaseModel):
    step: ValidationStep
    result: CheckResult
    evidence: Optional[ValidationEvidence] = None
    diagnostics: List[Diagnostic] = Field(default_factory=list)

class ValidationReport(BaseModel):
    plugin: PluginIdentity
    records: List[ValidationRecord] = Field(default_factory=list)
    summary: Dict[str, int] = Field(default_factory=dict)
```

---

## 9) Concrete validation steps (only those supported by cited sources)

### 9.1 Claude Code validation steps

**C1 — Validate plugin manifest**
- Evidence: CLI
- Command: `claude plugin validate <path-to-plugin>`
- Expect: exit 0 / "valid"
- Source: Claude plugin reference includes developer tools and validate flows.

**C2 — Load plugin with debug and verify registration**
- Evidence: CLI/LOG
- Command: `claude --debug ...` (categories as needed)
- Expect: debug indicates plugin loaded and components registered (including MCP initialization details)
- Source: plugin reference describes --debug output for plugin loading/initialization.

**C3 — Skills/commands discoverable (interactive smoke test)**
- Evidence: TUI
- Steps:
  1. Start Claude Code interactive session
  2. Type `/` and verify plugin skill/command appears
  3. Invoke `/skill-name` (or command)
- Expect: selection shows component; invocation works
- Source: plugin reference states skills/commands are discovered when plugin is installed.

**C4 — Hooks fire (debug-driven)**
- Evidence: LOG
- Steps:
  1. Start with `claude --debug ...`
  2. Trigger a tool-use path that the hook matches
- Expect: hook event lines in debug/log output
- Source: hooks are a defined plugin component and part of plugin debug surface.

### 9.2 Codex validation steps

**X1 — Validate interactive slash command surface is reachable**
- Evidence: TUI
- Steps:
  1. Start Codex interactive session
  2. Type `/` to open slash popup
- Expect: slash popup opens
- Source: Codex slash commands guide.

**X2 — MCP status visible**
- Evidence: TUI
- Steps:
  1. In Codex session, run `/mcp`
- Expect: MCP status/control output appears
- Source: Codex slash commands guide documents `/mcp` and related control surfaces.

**X3 — Skill availability and usage**
- Evidence: TUI
- Steps:
  1. Ensure exported skills are installed (per tool's configured skills discovery)
  2. Use the UI flow to invoke skills (converter should provide a specific "how to invoke" note per Codex surface used)
- Expect: skill can be invoked / recognized
- Source: Codex skills docs establish skills as first-class.

**X4 — Custom prompts (deprecated) listed/invocable (optional)**
- Evidence: FILESYSTEM + TUI
- Steps:
  1. Verify `~/.codex/prompts/<name>.md` exists (top-level; no subdirectories).
  2. Restart Codex.
  3. Confirm the prompt appears as `/prompts:<name>` in the slash command menu and is invocable.
- Expect: prompt usable
- Source: Custom Prompts page (deprecated).

### 9.3 Cursor validation steps

**U1 — Commands discoverable**
- Evidence: FILESYSTEM + TUI
- Steps:
  1. Ensure `.cursor/commands/<name>.md` exists
  2. In Cursor agent/chat, type `/` to view commands
- Expect: command appears
- Source: Cursor commands doc specifies `.cursor/commands` and Markdown file format.

**U2 — Skills available**
- Evidence: TUI
- Steps:
  1. Install/export skills into Cursor's supported skills surface
  2. Use Cursor's documented skills UX to invoke skill
- Expect: skill works
- Source: Cursor Agent Skills docs.

**U3 — Hooks operational**
- Evidence: LOG/TUI
- Steps:
  1. Configure hook per Cursor hooks docs
  2. Trigger matching agent-loop activity
- Expect: hook executes as expected
- Source: Cursor hooks docs.

### 9.4 OpenCode validation steps

**O1 — Skills functional (runtime smoke test)**
- Evidence: TUI
- Steps:
  1. Place skill in configured directory (default `.opencode` or `OPENCODE_CONFIG_DIR`)
  2. Trigger skill loading via OpenCode skill tool (on-demand)
- Expect: skill is discoverable/loadable by the skill tool
- Source: OpenCode skills docs explain on-demand loading and skill tool behavior; config override is documented.

**O2 — Commands discoverable (runtime smoke test)**
- Evidence: FILESYSTEM + TUI
- Steps:
  1. Place command file in `.opencode/commands/` (project) or `~/.config/opencode/commands/` (user).
  2. In OpenCode, type `/` and confirm the command appears; invoke it.
- Expect: command appears and runs
- Source: OpenCode commands docs (markdown commands + locations + invocation).

**O3 — LSP server configured and starts (optional / best-effort)**
- Evidence: FILESYSTEM + LOG/TUI
- Steps:
  1. Write `opencode.json` with `lsp.<server>.command` and `lsp.<server>.extensions`.
  2. Open a file matching an extension.
  3. Confirm LSP starts (via OpenCode logs/diagnostics if exposed) or by observing features that depend on LSP.
- Source: OpenCode LSP docs (custom LSP config + behavior).
- Notes: Mark best-effort if the log/diagnostic surface varies by version/build; the configuration surface itself is documented.

---

## 10) Optional: Docker + tmux validation harness

### 10.1 Rationale

Some validations are inherently TUI-driven (`/` menus, slash commands). tmux can:
- start a TUI in a session
- send keystrokes
- capture pane output
- run regex assertions against captured output

### 10.2 What is feasible per documented surfaces
- Codex slash-command-based checks are explicitly documented, making tmux automation plausible.
- Claude debug output checks are plausible via non-interactive `--debug` logs; plugin validate is CLI-based.
- Cursor/OpenCode checks may require UI layers not intended for headless Docker; do not promise full automation without confirming headless support and stable CLIs.

---

## 11) Deliverables

### 11.1 Converter outputs
- Emitted file tree(s) for each target
- An install manifest (for uninstall/re-run)
- Diagnostics describing mapping status per component

### 11.2 Validator outputs
- `ValidationReport` JSON (dumped from Pydantic)
- Human-readable report (table + highlighted failures)
- Evidence blobs (captured stdout/stderr/pane output)

---

## 12) Explicit gaps / TODOs (must be resolved by additional primary research before claiming full automation)

1. **Codex skill discovery is documented**: Codex reads skills from `.agents/skills` in `$HOME` and within repositories (including repo-root and parent-folder scanning), plus `/etc/codex/skills` for admin-installed skills. The remaining "gap" is choosing which of these locations this converter targets by default for each scope (user/project/admin).

2. **Cursor skills path/version behavior is version-dependent**: Cursor indicates Agent Skills are compatible with Claude Skills format, but rollout/activation can vary (some users report it only enables when `~/.claude/skills` already exists). Do not hardcode user-global paths without primary Cursor docs confirming them; treat as conditional and include a "detection + instructions" step.

3. **OpenCode CLI enumeration for skills** (not assumed; add only when documented as stable).

These gaps are intentionally surfaced so the tool does not claim guarantees it cannot verify from authoritative sources.
