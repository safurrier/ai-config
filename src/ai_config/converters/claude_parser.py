"""Parser for Claude Code plugins.

Reads a Claude plugin directory and produces a PluginIR.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from ai_config.converters.ir import (
    Agent,
    BinaryFile,
    Command,
    Diagnostic,
    Hook,
    HookEvent,
    HookHandler,
    HookHandlerType,
    LspServer,
    McpServer,
    McpTransport,
    PluginIdentity,
    PluginIR,
    Severity,
    Skill,
    TextFile,
)


class ClaudePluginParser:
    """Parses Claude Code plugins into IR format."""

    def __init__(self, plugin_path: Path) -> None:
        self.plugin_path = plugin_path.resolve()
        self.diagnostics: list[Diagnostic] = []

    def parse(self) -> PluginIR:
        """Parse the plugin and return IR."""
        # Find and parse plugin.json
        manifest_path = self._find_manifest()
        if not manifest_path:
            return self._error_ir("Could not find plugin.json manifest")

        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as e:
            return self._error_ir(f"Invalid JSON in plugin.json: {e}")

        # Extract identity
        identity = self._parse_identity(manifest)
        if not identity:
            return self._error_ir("Missing required 'name' field in plugin.json")

        # Build IR
        ir = PluginIR(
            identity=identity,
            source_path=self.plugin_path,
            diagnostics=self.diagnostics,
        )

        # Parse each component type
        self._parse_skills(ir, manifest)
        self._parse_commands(ir, manifest)
        self._parse_agents(ir, manifest)
        self._parse_hooks(ir, manifest)
        self._parse_mcp_servers(ir, manifest)
        self._parse_lsp_servers(ir, manifest)

        return ir

    def _find_manifest(self) -> Path | None:
        """Find plugin.json in standard locations."""
        # Standard: .claude-plugin/plugin.json
        standard = self.plugin_path / ".claude-plugin" / "plugin.json"
        if standard.exists():
            return standard

        # Alternative: plugin.json at root
        root = self.plugin_path / "plugin.json"
        if root.exists():
            self._add_diagnostic(
                Severity.WARN,
                "plugin.json found at root instead of .claude-plugin/",
                source_path=root,
            )
            return root

        return None

    def _parse_identity(self, manifest: dict[str, Any]) -> PluginIdentity | None:
        """Extract plugin identity from manifest."""
        name = manifest.get("name")
        if not name:
            return None

        # Normalize name to plugin_id
        plugin_id = name.lower().replace("_", "-").replace(" ", "-")

        return PluginIdentity(
            plugin_id=plugin_id,
            name=name,
            version=manifest.get("version"),
            description=manifest.get("description"),
        )

    def _resolve_paths(self, manifest: dict[str, Any], key: str) -> list[Path]:
        """Resolve component paths from manifest."""
        value = manifest.get(key)
        if not value:
            # Check default directory
            default_dir = self.plugin_path / key
            if default_dir.is_dir():
                return [default_dir]
            return []

        if isinstance(value, str):
            paths = [value]
        elif isinstance(value, list):
            paths = value
        else:
            return []

        resolved = []
        for p in paths:
            # Handle relative paths (./path)
            if p.startswith("./"):
                p = p[2:]
            full_path = self.plugin_path / p
            if full_path.exists():
                resolved.append(full_path)
            else:
                self._add_diagnostic(
                    Severity.WARN,
                    f"Path does not exist: {p}",
                    component_ref=f"{key}:{p}",
                )
        return resolved

    def _parse_skills(self, ir: PluginIR, manifest: dict[str, Any]) -> None:
        """Parse skill directories."""
        skill_paths = self._resolve_paths(manifest, "skills")

        for skill_path in skill_paths:
            if skill_path.is_dir():
                # If it's a directory, look for subdirectories with SKILL.md
                for subdir in skill_path.iterdir():
                    if subdir.is_dir():
                        skill_md = subdir / "SKILL.md"
                        if skill_md.exists():
                            skill = self._parse_skill(subdir, skill_md)
                            if skill:
                                ir.components.append(skill)
                # Also check if this directory itself has SKILL.md
                skill_md = skill_path / "SKILL.md"
                if skill_md.exists():
                    skill = self._parse_skill(skill_path, skill_md)
                    if skill:
                        ir.components.append(skill)

    def _parse_skill(self, skill_dir: Path, skill_md: Path) -> Skill | None:
        """Parse a single SKILL.md file."""
        content = skill_md.read_text()
        frontmatter, body = self._split_frontmatter(content)

        if not frontmatter:
            self._add_diagnostic(
                Severity.ERROR,
                "SKILL.md missing YAML frontmatter",
                source_path=skill_md,
            )
            return None

        try:
            meta = yaml.safe_load(frontmatter)
        except yaml.YAMLError as e:
            self._add_diagnostic(
                Severity.ERROR,
                f"Invalid YAML frontmatter: {e}",
                source_path=skill_md,
            )
            return None

        name = meta.get("name", skill_dir.name)
        description = meta.get("description")

        # Validate name for strictest target (OpenCode)
        try:
            # This will raise if invalid
            name_lower = name.lower().replace("_", "-")
            if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name_lower):
                self._add_diagnostic(
                    Severity.WARN,
                    f"Skill name '{name}' may not be portable (non-kebab-case)",
                    component_ref=f"skill:{name}",
                    source_path=skill_md,
                )
                # Normalize it
                name = name_lower
        except Exception:
            pass

        # Collect all files in the skill directory
        files: list[TextFile | BinaryFile] = []
        for file_path in skill_dir.rglob("*"):
            if file_path.is_file():
                relpath = str(file_path.relative_to(skill_dir))
                try:
                    content = file_path.read_text()
                    files.append(
                        TextFile(
                            relpath=relpath,
                            content=content,
                            executable=file_path.stat().st_mode & 0o111 != 0,
                        )
                    )
                except UnicodeDecodeError:
                    # Binary file - skip for now or handle separately
                    self._add_diagnostic(
                        Severity.INFO,
                        f"Skipping binary file: {relpath}",
                        component_ref=f"skill:{name}",
                    )

        return Skill(
            name=name,
            description=description,
            files=files,
            allowed_tools=self._parse_allowed_tools(meta.get("allowed-tools")),
            model=meta.get("model"),
            context=meta.get("context"),
            agent=meta.get("agent"),
            user_invocable=meta.get("user-invocable", True),
            disable_model_invocation=meta.get("disable-model-invocation", False),
        )

    def _parse_allowed_tools(self, value: Any) -> list[str] | None:
        """Parse allowed-tools field."""
        if not value:
            return None
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            # Space or comma separated
            return [t.strip() for t in re.split(r"[,\s]+", value) if t.strip()]
        return None

    def _parse_commands(self, ir: PluginIR, manifest: dict[str, Any]) -> None:
        """Parse command files."""
        cmd_paths = self._resolve_paths(manifest, "commands")

        for cmd_path in cmd_paths:
            if cmd_path.is_file() and cmd_path.suffix == ".md":
                cmd = self._parse_command(cmd_path)
                if cmd:
                    ir.components.append(cmd)
            elif cmd_path.is_dir():
                for md_file in cmd_path.glob("*.md"):
                    cmd = self._parse_command(md_file)
                    if cmd:
                        ir.components.append(cmd)

    def _parse_command(self, cmd_path: Path) -> Command | None:
        """Parse a single command markdown file."""
        content = cmd_path.read_text()
        frontmatter, body = self._split_frontmatter(content)

        meta = {}
        if frontmatter:
            try:
                meta = yaml.safe_load(frontmatter) or {}
            except yaml.YAMLError:
                pass

        name = cmd_path.stem  # filename without .md
        description = meta.get("description")

        # Detect template variables
        has_arguments = "$ARGUMENTS" in body or "${ARGUMENTS}" in body
        has_positional = bool(re.search(r"\$[1-9]|\$\{[1-9]\}", body))

        return Command(
            name=name,
            description=description,
            markdown=body.strip() if body else content.strip(),
            argument_hint=meta.get("argument-hint"),
            has_arguments_var=has_arguments,
            has_positional_vars=has_positional,
        )

    def _parse_agents(self, ir: PluginIR, manifest: dict[str, Any]) -> None:
        """Parse agent definition files."""
        agent_paths = self._resolve_paths(manifest, "agents")

        for agent_path in agent_paths:
            if agent_path.is_file() and agent_path.suffix == ".md":
                agent = self._parse_agent(agent_path)
                if agent:
                    ir.components.append(agent)
            elif agent_path.is_dir():
                for md_file in agent_path.glob("*.md"):
                    agent = self._parse_agent(md_file)
                    if agent:
                        ir.components.append(agent)

    def _parse_agent(self, agent_path: Path) -> Agent | None:
        """Parse a single agent markdown file."""
        content = agent_path.read_text()
        frontmatter, body = self._split_frontmatter(content)

        meta = {}
        if frontmatter:
            try:
                meta = yaml.safe_load(frontmatter) or {}
            except yaml.YAMLError:
                pass

        name = agent_path.stem
        return Agent(
            name=name,
            description=meta.get("description"),
            markdown=body.strip() if body else content.strip(),
            capabilities=meta.get("capabilities", []),
        )

    def _parse_hooks(self, ir: PluginIR, manifest: dict[str, Any]) -> None:
        """Parse hooks configuration."""
        hooks_value = manifest.get("hooks")
        if not hooks_value:
            # Check default location
            default_hooks = self.plugin_path / "hooks" / "hooks.json"
            if default_hooks.exists():
                hooks_value = str(default_hooks.relative_to(self.plugin_path))
            else:
                return

        # Load hooks config
        if isinstance(hooks_value, str):
            # Handle ./ prefix carefully
            clean_path = hooks_value
            if clean_path.startswith("./"):
                clean_path = clean_path[2:]
            hooks_path = self.plugin_path / clean_path
            if not hooks_path.exists():
                return
            try:
                hooks_config = json.loads(hooks_path.read_text())
            except json.JSONDecodeError as e:
                self._add_diagnostic(
                    Severity.ERROR,
                    f"Invalid JSON in hooks config: {e}",
                    source_path=hooks_path,
                )
                return
        elif isinstance(hooks_value, dict):
            hooks_config = hooks_value
        else:
            return

        # Parse hooks
        hooks_data = hooks_config.get("hooks", hooks_config)
        hook = Hook(events=[])

        for event_name, event_handlers in hooks_data.items():
            if not isinstance(event_handlers, list):
                continue

            for handler_group in event_handlers:
                matcher = handler_group.get("matcher")
                handlers_list = handler_group.get("hooks", [])

                parsed_handlers = []
                for h in handlers_list:
                    handler_type = h.get("type", "command")
                    parsed_handlers.append(
                        HookHandler(
                            type=HookHandlerType(handler_type),
                            command=h.get("command"),
                            prompt=h.get("prompt"),
                            timeout_sec=h.get("timeout"),
                            is_async=h.get("async", False),
                        )
                    )

                hook.events.append(
                    HookEvent(
                        name=event_name,
                        matcher=matcher,
                        handlers=parsed_handlers,
                    )
                )

        if hook.events:
            ir.components.append(hook)

    def _parse_mcp_servers(self, ir: PluginIR, manifest: dict[str, Any]) -> None:
        """Parse MCP server configuration."""
        mcp_value = manifest.get("mcpServers")
        if not mcp_value:
            # Check default location
            default_mcp = self.plugin_path / ".mcp.json"
            if default_mcp.exists():
                mcp_value = ".mcp.json"
            else:
                return

        # Load MCP config
        if isinstance(mcp_value, str):
            # Handle ./ prefix carefully - don't strip the leading dot from filenames
            clean_path = mcp_value
            if clean_path.startswith("./"):
                clean_path = clean_path[2:]
            mcp_path = self.plugin_path / clean_path
            if not mcp_path.exists():
                return
            try:
                mcp_config = json.loads(mcp_path.read_text())
            except json.JSONDecodeError as e:
                self._add_diagnostic(
                    Severity.ERROR,
                    f"Invalid JSON in MCP config: {e}",
                    source_path=mcp_path,
                )
                return
        elif isinstance(mcp_value, dict):
            mcp_config = mcp_value
        else:
            return

        # Parse servers
        servers = mcp_config.get("mcpServers", mcp_config)
        for name, config in servers.items():
            if not isinstance(config, dict):
                continue

            # Determine transport
            if config.get("url"):
                transport = McpTransport.HTTP
            else:
                transport = McpTransport.STDIO

            ir.components.append(
                McpServer(
                    name=name,
                    transport=transport,
                    command=config.get("command"),
                    args=config.get("args", []),
                    url=config.get("url"),
                    env=config.get("env", {}),
                    cwd=config.get("cwd"),
                )
            )

    def _parse_lsp_servers(self, ir: PluginIR, manifest: dict[str, Any]) -> None:
        """Parse LSP server configuration."""
        lsp_value = manifest.get("lspServers")
        if not lsp_value:
            # Check default location
            default_lsp = self.plugin_path / ".lsp.json"
            if default_lsp.exists():
                lsp_value = ".lsp.json"
            else:
                return

        # Load LSP config
        if isinstance(lsp_value, str):
            # Handle ./ prefix carefully - don't strip the leading dot from filenames
            clean_path = lsp_value
            if clean_path.startswith("./"):
                clean_path = clean_path[2:]
            lsp_path = self.plugin_path / clean_path
            if not lsp_path.exists():
                return
            try:
                lsp_config = json.loads(lsp_path.read_text())
            except json.JSONDecodeError as e:
                self._add_diagnostic(
                    Severity.ERROR,
                    f"Invalid JSON in LSP config: {e}",
                    source_path=lsp_path,
                )
                return
        elif isinstance(lsp_value, dict):
            lsp_config = lsp_value
        else:
            return

        # Parse servers
        for name, config in lsp_config.items():
            if not isinstance(config, dict):
                continue

            # Extract extensions from extensionToLanguage
            extensions = []
            ext_map = config.get("extensionToLanguage", {})
            if ext_map:
                extensions = list(ext_map.keys())

            ir.components.append(
                LspServer(
                    name=name,
                    command=config.get("command"),
                    args=config.get("args", []),
                    extensions=extensions,
                    env=config.get("env", {}),
                    initialization_options=config.get("initializationOptions", {}),
                )
            )

    def _split_frontmatter(self, content: str) -> tuple[str | None, str]:
        """Split markdown content into frontmatter and body."""
        if not content.startswith("---"):
            return None, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None, content

        return parts[1].strip(), parts[2].strip()

    def _add_diagnostic(
        self,
        severity: Severity,
        message: str,
        component_ref: str | None = None,
        source_path: Path | None = None,
    ) -> None:
        """Add a diagnostic message."""
        self.diagnostics.append(
            Diagnostic(
                severity=severity,
                message=message,
                component_ref=component_ref,
                source_path=source_path,
            )
        )

    def _error_ir(self, message: str) -> PluginIR:
        """Create an error IR with no components."""
        return PluginIR(
            identity=PluginIdentity(plugin_id="error", name="error"),
            diagnostics=[Diagnostic(severity=Severity.ERROR, message=message)],
        )


def parse_claude_plugin(plugin_path: Path | str) -> PluginIR:
    """Parse a Claude Code plugin directory into IR.

    Args:
        plugin_path: Path to the plugin directory

    Returns:
        PluginIR with parsed components and diagnostics
    """
    parser = ClaudePluginParser(Path(plugin_path))
    return parser.parse()
