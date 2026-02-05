"""Emitters for converting IR to target tool formats.

Each emitter takes a PluginIR and produces files for a specific tool.
Emitters follow the Protocol pattern (structural typing) - any class with
the right shape satisfies the Emitter interface.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ai_config.converters.ir import (
    Command,
    Diagnostic,
    Hook,
    InstallScope,
    LspServer,
    MappingStatus,
    McpServer,
    McpTransport,
    PluginIR,
    Severity,
    Skill,
    TargetTool,
    TextFile,
)


@dataclass
class EmittedFile:
    """A file to be written by the emitter."""

    path: Path  # Relative path from output root
    content: str
    executable: bool = False


@dataclass
class ComponentMapping:
    """Record of how a component was mapped."""

    component_kind: str
    component_name: str
    status: MappingStatus
    target_path: Path | None = None
    notes: str | None = None


@dataclass
class EmitResult:
    """Result of emitting a plugin to a target format."""

    target: TargetTool
    files: list[EmittedFile] = field(default_factory=list)
    mappings: list[ComponentMapping] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def add_file(self, path: Path | str, content: str, executable: bool = False) -> None:
        """Add a file to emit."""
        self.files.append(EmittedFile(path=Path(path), content=content, executable=executable))

    def add_mapping(
        self,
        kind: str,
        name: str,
        status: MappingStatus,
        target_path: Path | None = None,
        notes: str | None = None,
    ) -> None:
        """Record a component mapping."""
        self.mappings.append(
            ComponentMapping(
                component_kind=kind,
                component_name=name,
                status=status,
                target_path=target_path,
                notes=notes,
            )
        )

    def add_diagnostic(
        self,
        severity: Severity,
        message: str,
        component_ref: str | None = None,
    ) -> None:
        """Add a diagnostic message."""
        self.diagnostics.append(
            Diagnostic(
                severity=severity,
                message=message,
                component_ref=component_ref,
            )
        )

    def write_to(self, output_dir: Path, dry_run: bool = False) -> list[Path]:
        """Write all files to the output directory.

        Args:
            output_dir: Directory to write files to
            dry_run: If True, don't actually write files

        Returns list of file paths that were/would be written.
        """
        written = []
        for f in self.files:
            full_path = output_dir / f.path
            if not dry_run:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(f.content)
                if f.executable:
                    full_path.chmod(full_path.stat().st_mode | 0o111)
            written.append(full_path)
        return written

    def preview(self, output_dir: Path | None = None) -> str:
        """Generate preview of what would be written.

        Args:
            output_dir: Optional base directory for path display

        Returns formatted string showing files and sizes.
        """
        lines = [f"Files to write ({len(self.files)} total):"]
        lines.append("")

        total_bytes = 0
        for f in self.files:
            size = len(f.content.encode("utf-8"))
            total_bytes += size

            if output_dir:
                display_path = output_dir / f.path
            else:
                display_path = f.path

            action = "[CREATE]"
            if output_dir and (output_dir / f.path).exists():
                action = "[UPDATE]"

            exec_flag = " (exec)" if f.executable else ""
            lines.append(f"  {action} {display_path}{exec_flag}")
            lines.append(f"         {size:,} bytes")

        lines.append("")
        lines.append(f"Total: {total_bytes:,} bytes")

        # Add mapping summary
        if self.mappings:
            lines.append("")
            lines.append("Component mappings:")
            for m in self.mappings:
                status_icon = {
                    MappingStatus.NATIVE: "✓",
                    MappingStatus.TRANSFORM: "~",
                    MappingStatus.FALLBACK: "↓",
                    MappingStatus.EMULATE: "≈",
                    MappingStatus.UNSUPPORTED: "✗",
                }.get(m.status, "?")
                lines.append(
                    f"  {status_icon} {m.component_kind}:{m.component_name} → {m.status.value}"
                )

        # Add diagnostics
        errors = [d for d in self.diagnostics if d.severity == Severity.ERROR]
        warnings = [d for d in self.diagnostics if d.severity == Severity.WARN]

        if errors:
            lines.append("")
            lines.append(f"Errors ({len(errors)}):")
            for e in errors:
                lines.append(f"  ✗ {e.message}")

        if warnings:
            lines.append("")
            lines.append(f"Warnings ({len(warnings)}):")
            for w in warnings:
                lines.append(f"  ⚠ {w.message}")

        return "\n".join(lines)

    def has_errors(self) -> bool:
        """Check if any error-level diagnostics exist."""
        return any(d.severity == Severity.ERROR for d in self.diagnostics)


# Module-level helper function (extracted from BaseEmitter for Protocol pattern)
def skill_to_markdown(skill: Skill, strip_claude_fields: bool = True) -> str:
    """Convert a skill to SKILL.md format.

    Args:
        skill: The skill to convert.
        strip_claude_fields: If True, remove Claude-specific fields like
            allowed-tools, model, context, agent, etc.

    Returns:
        Markdown string with YAML frontmatter.
    """
    # Build frontmatter
    meta: dict[str, Any] = {
        "name": skill.name,
    }
    if skill.description:
        meta["description"] = skill.description

    # Include portable fields only when not stripping
    if not strip_claude_fields:
        if skill.allowed_tools:
            meta["allowed-tools"] = skill.allowed_tools
        if skill.model:
            meta["model"] = skill.model
        if skill.context:
            meta["context"] = skill.context
        if skill.agent:
            meta["agent"] = skill.agent
        if not skill.user_invocable:
            meta["user-invocable"] = False
        if skill.disable_model_invocation:
            meta["disable-model-invocation"] = True

    # Find SKILL.md content
    body = ""
    for f in skill.files:
        if f.relpath == "SKILL.md" and isinstance(f, TextFile):
            # Extract body from content (TextFile only)
            file_content = f.content
            if file_content.startswith("---"):
                parts = file_content.split("---", 2)
                if len(parts) >= 3:
                    body = parts[2].strip()
            else:
                body = file_content
            break

    # Build markdown
    frontmatter = yaml.dump(meta, default_flow_style=False, sort_keys=False)
    return f"---\n{frontmatter}---\n\n{body}"


class CodexEmitter:
    """Emit plugins in Codex format.

    Satisfies the Emitter protocol with target, scope, and emit() method.
    """

    target = TargetTool.CODEX

    def __init__(
        self, scope: InstallScope = InstallScope.PROJECT, commands_as_skills: bool = False
    ) -> None:
        self.scope = scope
        self.commands_as_skills = commands_as_skills

    def emit(self, ir: PluginIR) -> EmitResult:
        """Emit IR to Codex format."""
        result = EmitResult(target=self.target)
        plugin_id = ir.identity.plugin_id

        # Emit skills
        for skill in ir.skills():
            self._emit_skill(result, skill, plugin_id)

        # Emit commands as deprecated custom prompts
        for cmd in ir.commands():
            self._emit_command(result, cmd, plugin_id)

        # Emit MCP servers to config.toml
        mcp_servers = ir.mcp_servers()
        if mcp_servers:
            self._emit_mcp_config(result, mcp_servers, plugin_id)

        # Hooks not supported
        for _hook in ir.hooks():
            result.add_mapping(
                "hook",
                "hooks",
                MappingStatus.UNSUPPORTED,
                notes="Codex does not support hooks",
            )
            result.add_diagnostic(
                Severity.WARN,
                "Hooks are not supported in Codex - consider converting to a skill",
                component_ref="hook:*",
            )

        # Agents not supported
        for agent in ir.agents():
            result.add_mapping(
                "agent",
                agent.name,
                MappingStatus.UNSUPPORTED,
                notes="Codex does not support agent definitions",
            )

        # LSP not supported
        for lsp in ir.lsp_servers():
            result.add_mapping(
                "lsp",
                lsp.name,
                MappingStatus.UNSUPPORTED,
                notes="Codex does not support custom LSP servers",
            )

        return result

    def _emit_skill(self, result: EmitResult, skill: Skill, plugin_id: str) -> None:
        """Emit a skill to Codex format."""
        # Codex skills go to .codex/skills/<name>/SKILL.md
        skill_dir = Path(".codex") / "skills" / f"{plugin_id}-{skill.name}"
        skill_path = skill_dir / "SKILL.md"

        # Convert to markdown, stripping Claude-specific fields
        content = skill_to_markdown(skill, strip_claude_fields=True)

        result.add_file(skill_path, content)

        # Copy other skill files
        for f in skill.files:
            if f.relpath != "SKILL.md" and isinstance(f, TextFile):
                result.add_file(skill_dir / f.relpath, f.content, f.executable)

        result.add_mapping(
            "skill",
            skill.name,
            MappingStatus.NATIVE,
            target_path=skill_path,
        )

    def _emit_command(self, result: EmitResult, cmd: Command, plugin_id: str) -> None:
        """Emit a command to Codex format.

        By default, commands are emitted as prompts (deprecated but 1:1 with Claude commands).
        With commands_as_skills=True, they're emitted as skills (auto-discoverable).
        """
        if self.commands_as_skills:
            self._emit_command_as_skill(result, cmd, plugin_id)
        else:
            self._emit_command_as_prompt(result, cmd, plugin_id)

    def _emit_command_as_prompt(self, result: EmitResult, cmd: Command, plugin_id: str) -> None:
        """Emit a command as a deprecated custom prompt (default, 1:1 with Claude).

        Prompts provide explicit invocation via /prompts:<name>, matching Claude's
        /command behavior. This is deprecated in Codex but preserves user expectations.
        """
        # Codex custom prompts go to ~/.codex/prompts/<name>.md
        # For project scope, we'll use .codex/prompts/
        prompt_name = f"{plugin_id}-{cmd.name}"
        if self.scope == InstallScope.USER:
            prompt_path = Path("prompts") / f"{prompt_name}.md"
        else:
            prompt_path = Path(".codex") / "prompts" / f"{prompt_name}.md"

        # Build frontmatter
        meta: dict[str, Any] = {}
        if cmd.description:
            meta["description"] = cmd.description
        if cmd.argument_hint:
            meta["argument-hint"] = cmd.argument_hint

        if meta:
            frontmatter = yaml.dump(meta, default_flow_style=False)
            content = f"---\n{frontmatter}---\n\n{cmd.markdown}"
        else:
            content = cmd.markdown

        result.add_file(prompt_path, content)

        result.add_mapping(
            "command",
            cmd.name,
            MappingStatus.FALLBACK,
            target_path=prompt_path,
            notes=f"Invoke with /prompts:{prompt_name} (prompts are deprecated in Codex)",
        )

        result.add_diagnostic(
            Severity.INFO,
            f"Command '{cmd.name}' → /prompts:{prompt_name} (use --commands-as-skills for auto-discovery)",
            component_ref=f"command:{cmd.name}",
        )

    def _emit_command_as_skill(self, result: EmitResult, cmd: Command, plugin_id: str) -> None:
        """Emit a command as a skill (opt-in, auto-discoverable).

        Skills are auto-discoverable and can be implicitly invoked by Codex.
        Use --commands-as-skills flag to enable this mode.
        """
        # Emit as a skill directory with SKILL.md
        skill_name = f"{plugin_id}-cmd-{cmd.name}"
        skill_dir = Path(".codex") / "skills" / skill_name
        skill_path = skill_dir / "SKILL.md"

        # Build SKILL.md with frontmatter
        meta: dict[str, Any] = {"name": skill_name}
        if cmd.description:
            meta["description"] = cmd.description

        content = cmd.markdown

        # Add argument hint as part of the skill description if present
        if cmd.argument_hint:
            meta["description"] = f"{cmd.description or ''} Arguments: {cmd.argument_hint}".strip()

        frontmatter = yaml.dump(meta, default_flow_style=False)
        skill_content = f"---\n{frontmatter}---\n\n{content}"

        result.add_file(skill_path, skill_content)

        # Determine mapping status based on variable usage
        if cmd.has_arguments_var or cmd.has_positional_vars:
            status = MappingStatus.TRANSFORM
            notes = "Command variables ($ARGUMENTS, $N) preserved in skill instructions"
        else:
            status = MappingStatus.NATIVE
            notes = None

        result.add_mapping(
            "command",
            cmd.name,
            status,
            target_path=skill_path,
            notes=notes,
        )

        result.add_diagnostic(
            Severity.INFO,
            f"Command '{cmd.name}' converted to skill '{skill_name}' (auto-discoverable)",
            component_ref=f"command:{cmd.name}",
        )

    def _emit_mcp_config(
        self, result: EmitResult, servers: list[McpServer], plugin_id: str
    ) -> None:
        """Emit MCP configuration as TOML."""
        # Build TOML content (manual since tomli-w may not be available)
        lines = [f"# MCP servers from plugin: {plugin_id}", ""]

        for server in servers:
            section_name = f"{plugin_id}-{server.name}"
            lines.append(f"[mcp_servers.{section_name}]")

            if server.command:
                lines.append(f'command = "{server.command}"')
            if server.args:
                args_str = ", ".join(f'"{a}"' for a in server.args)
                lines.append(f"args = [{args_str}]")
            if server.url:
                lines.append(f'url = "{server.url}"')
            if server.cwd:
                lines.append(f'cwd = "{server.cwd}"')
            if server.env:
                lines.append(
                    "env = {" + ", ".join(f'"{k}" = "{v}"' for k, v in server.env.items()) + "}"
                )
            lines.append("")

            result.add_mapping(
                "mcp_server",
                server.name,
                MappingStatus.TRANSFORM,
                notes="Converted to TOML format",
            )

        config_path = Path(".codex") / "mcp-config.toml"
        result.add_file(config_path, "\n".join(lines))

        result.add_diagnostic(
            Severity.INFO,
            f"MCP config written to {config_path} - merge into ~/.codex/config.toml",
            component_ref="mcp:*",
        )


class CursorEmitter:
    """Emit plugins in Cursor format.

    Satisfies the Emitter protocol with target, scope, and emit() method.
    """

    target = TargetTool.CURSOR

    def __init__(self, scope: InstallScope = InstallScope.PROJECT) -> None:
        self.scope = scope

    def emit(self, ir: PluginIR) -> EmitResult:
        """Emit IR to Cursor format."""
        result = EmitResult(target=self.target)
        plugin_id = ir.identity.plugin_id

        # Emit skills
        for skill in ir.skills():
            self._emit_skill(result, skill, plugin_id)

        # Emit commands (plain markdown, no variables)
        for cmd in ir.commands():
            self._emit_command(result, cmd, plugin_id)

        # Emit hooks (Cursor supports them!)
        hooks = ir.hooks()
        if hooks:
            self._emit_hooks(result, hooks, plugin_id)

        # Emit MCP servers
        mcp_servers = ir.mcp_servers()
        if mcp_servers:
            self._emit_mcp_config(result, mcp_servers, plugin_id)

        # Agents not supported
        for agent in ir.agents():
            result.add_mapping(
                "agent",
                agent.name,
                MappingStatus.UNSUPPORTED,
                notes="Cursor does not support custom agent definitions",
            )

        # LSP not supported (Cursor handles LSP internally)
        for lsp in ir.lsp_servers():
            result.add_mapping(
                "lsp",
                lsp.name,
                MappingStatus.UNSUPPORTED,
                notes="Cursor handles LSP internally",
            )

        return result

    def _emit_skill(self, result: EmitResult, skill: Skill, plugin_id: str) -> None:
        """Emit a skill to Cursor format."""
        skill_dir = Path(".cursor") / "skills" / f"{plugin_id}-{skill.name}"
        skill_path = skill_dir / "SKILL.md"

        content = skill_to_markdown(skill, strip_claude_fields=True)
        result.add_file(skill_path, content)

        for f in skill.files:
            if f.relpath != "SKILL.md" and isinstance(f, TextFile):
                result.add_file(skill_dir / f.relpath, f.content, f.executable)

        result.add_mapping(
            "skill",
            skill.name,
            MappingStatus.NATIVE,
            target_path=skill_path,
        )

    def _emit_command(self, result: EmitResult, cmd: Command, plugin_id: str) -> None:
        """Emit a command to Cursor format."""
        # Cursor commands are plain markdown, no variables
        cmd_path = Path(".cursor") / "commands" / f"{plugin_id}-{cmd.name}.md"

        # Strip variable references since Cursor doesn't support them
        content = cmd.markdown
        if cmd.has_arguments_var or cmd.has_positional_vars:
            # Add a note about lost functionality
            result.add_diagnostic(
                Severity.WARN,
                f"Command '{cmd.name}' uses template variables which Cursor doesn't support",
                component_ref=f"command:{cmd.name}",
            )
            # Replace $ARGUMENTS with a placeholder note
            content = re.sub(
                r"\$ARGUMENTS|\$\{ARGUMENTS\}",
                "[user arguments will be appended]",
                content,
            )
            content = re.sub(
                r"\$[1-9]|\$\{[1-9]\}",
                "[positional arg]",
                content,
            )

        result.add_file(cmd_path, content)

        status = (
            MappingStatus.NATIVE
            if not (cmd.has_arguments_var or cmd.has_positional_vars)
            else MappingStatus.TRANSFORM
        )
        result.add_mapping(
            "command",
            cmd.name,
            status,
            target_path=cmd_path,
            notes="Cursor commands don't support variable substitution"
            if status == MappingStatus.TRANSFORM
            else None,
        )

    def _emit_hooks(self, result: EmitResult, hooks: list[Hook], plugin_id: str) -> None:
        """Emit hooks configuration for Cursor."""
        # Map Claude events to Cursor events
        event_map = {
            "PreToolUse": ["beforeShellExecution", "beforeMCPExecution", "beforeReadFile"],
            "PostToolUse": ["afterShellExecution", "afterMCPExecution", "afterFileEdit"],
            "UserPromptSubmit": ["beforeSubmitPrompt"],
            "Stop": ["stop"],
        }

        cursor_hooks: dict[str, list[dict[str, Any]]] = {}

        for hook in hooks:
            for event in hook.events:
                cursor_events = event_map.get(event.name, [])
                if not cursor_events:
                    result.add_diagnostic(
                        Severity.WARN,
                        f"Hook event '{event.name}' has no Cursor equivalent",
                        component_ref=f"hook:{event.name}",
                    )
                    continue

                for cursor_event in cursor_events:
                    if cursor_event not in cursor_hooks:
                        cursor_hooks[cursor_event] = []

                    for handler in event.handlers:
                        if handler.type.value == "command" and handler.command:
                            cursor_hooks[cursor_event].append({"command": handler.command})
                        else:
                            result.add_diagnostic(
                                Severity.WARN,
                                f"Hook handler type '{handler.type}' not supported in Cursor",
                                component_ref=f"hook:{event.name}",
                            )

        if cursor_hooks:
            hooks_config = {"version": 1, "hooks": cursor_hooks}
            hooks_path = Path(".cursor") / "hooks.json"
            result.add_file(hooks_path, json.dumps(hooks_config, indent=2))
            result.add_mapping(
                "hook",
                "hooks",
                MappingStatus.TRANSFORM,
                target_path=hooks_path,
                notes="Event names mapped to Cursor equivalents",
            )

    def _emit_mcp_config(
        self, result: EmitResult, servers: list[McpServer], plugin_id: str
    ) -> None:
        """Emit MCP configuration for Cursor."""
        mcp_servers: dict[str, dict[str, Any]] = {}

        for server in servers:
            name = f"{plugin_id}-{server.name}"
            config: dict[str, Any] = {}

            if server.transport == McpTransport.STDIO:
                config["type"] = "stdio"
                if server.command:
                    config["command"] = server.command
                if server.args:
                    config["args"] = server.args
            else:
                # HTTP/SSE
                if server.url:
                    config["url"] = server.url

            if server.env:
                config["env"] = server.env

            mcp_servers[name] = config

            result.add_mapping(
                "mcp_server",
                server.name,
                MappingStatus.TRANSFORM,
                notes="Converted to Cursor MCP format",
            )

        mcp_path = Path(".cursor") / "mcp.json"
        result.add_file(mcp_path, json.dumps({"mcpServers": mcp_servers}, indent=2))


class OpenCodeEmitter:
    """Emit plugins in OpenCode format.

    Satisfies the Emitter protocol with target, scope, and emit() method.
    """

    target = TargetTool.OPENCODE

    def __init__(self, scope: InstallScope = InstallScope.PROJECT) -> None:
        self.scope = scope

    def emit(self, ir: PluginIR) -> EmitResult:
        """Emit IR to OpenCode format."""
        result = EmitResult(target=self.target)
        plugin_id = ir.identity.plugin_id

        # Emit skills
        for skill in ir.skills():
            self._emit_skill(result, skill, plugin_id)

        # Emit commands
        for cmd in ir.commands():
            self._emit_command(result, cmd, plugin_id)

        # Hooks not natively supported
        for _hook in ir.hooks():
            result.add_mapping(
                "hook",
                "hooks",
                MappingStatus.EMULATE,
                notes="OpenCode doesn't have hooks - consider using plugins",
            )
            result.add_diagnostic(
                Severity.WARN,
                "Hooks are not natively supported in OpenCode",
                component_ref="hook:*",
            )

        # Emit MCP servers
        mcp_servers = ir.mcp_servers()
        if mcp_servers:
            self._emit_mcp_config(result, mcp_servers, plugin_id)

        # Emit LSP servers (OpenCode supports them!)
        for lsp in ir.lsp_servers():
            self._emit_lsp_config(result, lsp, plugin_id)

        # Agents not supported
        for agent in ir.agents():
            result.add_mapping(
                "agent",
                agent.name,
                MappingStatus.UNSUPPORTED,
                notes="OpenCode does not support custom agent definitions",
            )

        return result

    def _emit_skill(self, result: EmitResult, skill: Skill, plugin_id: str) -> None:
        """Emit a skill to OpenCode format."""
        skill_dir = Path(".opencode") / "skills" / f"{plugin_id}-{skill.name}"
        skill_path = skill_dir / "SKILL.md"

        content = skill_to_markdown(skill, strip_claude_fields=True)
        result.add_file(skill_path, content)

        for f in skill.files:
            if f.relpath != "SKILL.md" and isinstance(f, TextFile):
                result.add_file(skill_dir / f.relpath, f.content, f.executable)

        result.add_mapping(
            "skill",
            skill.name,
            MappingStatus.NATIVE,
            target_path=skill_path,
        )

    def _emit_command(self, result: EmitResult, cmd: Command, plugin_id: str) -> None:
        """Emit a command to OpenCode format.

        OpenCode commands support:
        - Markdown with YAML frontmatter (description, agent, model)
        - Placeholders using $NAME syntax (uppercase)
        - Located in .opencode/commands/ (project) or ~/.config/opencode/commands/ (user)
        """
        cmd_path = Path(".opencode") / "commands" / f"{plugin_id}-{cmd.name}.md"

        # Build frontmatter
        meta: dict[str, Any] = {}
        if cmd.description:
            meta["description"] = cmd.description

        # Transform Claude's $ARGUMENTS to OpenCode's $ARGS placeholder
        # and $1, $2 etc to $ARG1, $ARG2 (OpenCode uses uppercase)
        content = cmd.markdown
        if cmd.has_arguments_var:
            content = re.sub(r"\$ARGUMENTS|\$\{ARGUMENTS\}", "$ARGS", content)
        if cmd.has_positional_vars:
            # Convert $1 to $ARG1, $2 to $ARG2, etc.
            content = re.sub(r"\$([1-9])|\$\{([1-9])\}", r"$ARG\1\2", content)

        if meta:
            frontmatter = yaml.dump(meta, default_flow_style=False)
            full_content = f"---\n{frontmatter}---\n\n{content}"
        else:
            full_content = content

        result.add_file(cmd_path, full_content)

        # Determine mapping status
        if cmd.has_arguments_var or cmd.has_positional_vars:
            status = MappingStatus.TRANSFORM
            notes = "Variables transformed: $ARGUMENTS→$ARGS, $N→$ARGN"
        else:
            status = MappingStatus.NATIVE
            notes = None

        result.add_mapping(
            "command",
            cmd.name,
            status,
            target_path=cmd_path,
            notes=notes,
        )

    def _emit_mcp_config(
        self, result: EmitResult, servers: list[McpServer], plugin_id: str
    ) -> None:
        """Emit MCP configuration for OpenCode."""
        mcp_config: dict[str, dict[str, Any]] = {}

        for server in servers:
            name = f"{plugin_id}-{server.name}"
            config: dict[str, Any] = {"enabled": True}

            if server.transport == McpTransport.STDIO:
                config["type"] = "local"
                cmd_parts = []
                if server.command:
                    cmd_parts.append(server.command)
                cmd_parts.extend(server.args)
                if cmd_parts:
                    config["command"] = cmd_parts
            else:
                config["type"] = "remote"
                if server.url:
                    config["url"] = server.url

            if server.env:
                config["environment"] = server.env
            if server.timeout_ms:
                config["timeout"] = server.timeout_ms

            mcp_config[name] = config

            result.add_mapping(
                "mcp_server",
                server.name,
                MappingStatus.TRANSFORM,
                notes="Converted to OpenCode MCP format",
            )

        # Emit to opencode.json at output root
        opencode_config = {"mcp": mcp_config}
        config_path = Path("opencode.json")
        result.add_file(config_path, json.dumps(opencode_config, indent=2))

        result.add_diagnostic(
            Severity.INFO,
            f"MCP config written to {config_path}",
            component_ref="mcp:*",
        )

    def _emit_lsp_config(self, result: EmitResult, lsp: LspServer, plugin_id: str) -> None:
        """Emit LSP configuration for OpenCode."""
        name = f"{plugin_id}-{lsp.name}"

        config: dict[str, Any] = {}
        if lsp.command:
            cmd_parts = [lsp.command] + lsp.args
            config["command"] = cmd_parts
        if lsp.extensions:
            config["extensions"] = lsp.extensions
        if lsp.env:
            config["env"] = lsp.env
        if lsp.initialization_options:
            config["initialization"] = lsp.initialization_options

        lsp_config = {"lsp": {name: config}}
        config_path = Path("opencode.lsp.json")
        result.add_file(config_path, json.dumps(lsp_config, indent=2))

        result.add_mapping(
            "lsp",
            lsp.name,
            MappingStatus.TRANSFORM,
            target_path=config_path,
            notes="Converted to OpenCode LSP format",
        )


# Factory function
def get_emitter(
    target: TargetTool,
    scope: InstallScope = InstallScope.PROJECT,
    commands_as_skills: bool = False,
) -> CodexEmitter | CursorEmitter | OpenCodeEmitter:
    """Get an emitter for the specified target tool.

    Args:
        target: Target tool to emit for
        scope: Installation scope (user or project)
        commands_as_skills: For Codex, convert commands to skills instead of prompts.
            Default False emits commands as prompts for 1:1 behavior with Claude.
    """
    if target == TargetTool.CODEX:
        return CodexEmitter(scope, commands_as_skills=commands_as_skills)
    elif target == TargetTool.CURSOR:
        return CursorEmitter(scope)
    elif target == TargetTool.OPENCODE:
        return OpenCodeEmitter(scope)
    else:
        raise ValueError(f"No emitter for target: {target}")
