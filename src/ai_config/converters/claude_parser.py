"""Parser for Claude Code plugins.

Reads a Claude plugin directory and produces a PluginIR.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
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
    IncludeKind,
    LspServer,
    McpServer,
    McpTransport,
    PluginIdentity,
    PluginIR,
    Severity,
    Skill,
    SkillInclude,
    TextFile,
)
from ai_config.converters.skill_projection import project_skill
from ai_config.source_safety import ContainedSource, SourceMissingError, SourceSafetyError


def normalize_portable_name(value: str, fallback_prefix: str, max_len: int | None = None) -> str:
    """Normalize one source identity to the converter's portable kebab-case key."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")

    if max_len is not None and len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")

    if not slug:
        digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:6]
        slug = f"{fallback_prefix}-{digest}"

    return slug


class ClaudePluginParser:
    """Parses Claude Code plugins into IR format."""

    def __init__(self, plugin_path: Path) -> None:
        self.plugin_path = plugin_path.expanduser().absolute()
        self.diagnostics: list[Diagnostic] = []
        self.source: ContainedSource | None = None

    def parse(self) -> PluginIR:
        """Parse the plugin and return IR."""
        try:
            self.source = ContainedSource(self.plugin_path)
        except SourceSafetyError as error:
            return self._error_ir(f"Could not find plugin.json manifest: {error}")
        self.plugin_path = self.source.root

        manifest_path = self._find_manifest()
        if not manifest_path:
            return self._error_ir("Could not find plugin.json manifest")

        try:
            manifest_bytes = self.source.read_file(manifest_path, context="manifest").content
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            return self._error_ir(f"Invalid JSON in plugin.json: {e}")
        except SourceSafetyError as error:
            return self._error_ir(str(error))
        if not isinstance(manifest, dict):
            return self._error_ir("plugin.json manifest must contain a JSON object")

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
        self._diagnose_known_unparsed_fields(ir, manifest)
        # Pydantic copies the diagnostic list passed at construction; publish
        # component-scoped diagnostics accumulated during the complete parse.
        ir.diagnostics = list(self.diagnostics) + [
            item for item in ir.diagnostics if item not in self.diagnostics
        ]
        return ir

    def _diagnose_known_unparsed_fields(self, ir: PluginIR, manifest: dict[str, Any]) -> None:
        """Surface modern Claude plugin fields that are not yet represented in IR."""
        known_unparsed_fields = {
            "outputStyles": "Claude output styles are recognized but not converted yet",
            "monitors": "Claude monitors are recognized but not converted yet",
            "themes": "Claude themes are recognized but not converted yet",
            "channels": "Claude channels are recognized but not converted yet",
        }
        for field, message in known_unparsed_fields.items():
            if field in manifest:
                ir.diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARN,
                        message=message,
                        component_ref=f"manifest:{field}",
                    )
                )

    def _find_manifest(self) -> PurePosixPath | None:
        """Find plugin.json in standard locations without following links."""
        assert self.source is not None
        standard = PurePosixPath(".claude-plugin/plugin.json")
        try:
            if self.source.kind(standard, context="manifest") == "file":
                return standard
        except SourceMissingError:
            pass
        except SourceSafetyError as error:
            self._add_diagnostic(Severity.ERROR, str(error), component_ref="manifest:plugin.json")
            return None

        root = PurePosixPath("plugin.json")
        try:
            if self.source.kind(root, context="manifest") == "file":
                self._add_diagnostic(
                    Severity.WARN,
                    "plugin.json found at root instead of .claude-plugin/",
                    source_path=self.plugin_path / "plugin.json",
                )
                return root
        except SourceMissingError:
            pass
        except SourceSafetyError as error:
            self._add_diagnostic(Severity.ERROR, str(error), component_ref="manifest:plugin.json")
        return None

    def _parse_identity(self, manifest: dict[str, Any]) -> PluginIdentity | None:
        """Extract plugin identity from manifest."""
        name = manifest.get("name")
        if not name:
            return None

        # Normalize name to plugin_id
        plugin_id = self._slugify(name, "plugin")
        if plugin_id != name:
            self._add_diagnostic(
                Severity.WARN,
                f"Normalized plugin id '{name}' → '{plugin_id}' for portability",
                component_ref="plugin:identity",
            )

        try:
            return PluginIdentity(
                plugin_id=plugin_id,
                name=name,
                version=manifest.get("version"),
                description=manifest.get("description"),
            )
        except Exception as e:
            self._add_diagnostic(
                Severity.ERROR,
                f"Invalid plugin identity: {e}",
                component_ref="plugin:identity",
            )
            return None

    def _resolve_paths(self, manifest: dict[str, Any], key: str) -> list[PurePosixPath]:
        """Resolve component paths through the contained-source authority."""
        assert self.source is not None
        value = manifest.get(key)
        if value is None or value == "" or value == []:
            default = PurePosixPath(key)
            try:
                return [default] if self.source.kind(default, context=key) == "directory" else []
            except SourceMissingError:
                return []
            except SourceSafetyError as error:
                self._add_diagnostic(Severity.ERROR, str(error), component_ref=f"{key}:{key}")
                return []

        raw_paths = (
            [value] if isinstance(value, str) else value if isinstance(value, list) else None
        )
        if raw_paths is None:
            self._add_diagnostic(
                Severity.ERROR,
                f"Manifest field '{key}' must be a string or list of strings",
                component_ref=f"manifest:{key}",
            )
            return []

        resolved: list[PurePosixPath] = []
        for raw in raw_paths:
            try:
                relative = self.source.relative(raw, context=key)
                self.source.kind(relative, context=key)
            except SourceMissingError:
                self._add_diagnostic(
                    Severity.WARN,
                    f"Path does not exist: {raw}",
                    component_ref=f"{key}:{raw}",
                )
            except SourceSafetyError as error:
                self._add_diagnostic(
                    Severity.ERROR,
                    str(error),
                    component_ref=f"{key}:{raw!r}",
                )
            else:
                resolved.append(relative)
        return resolved

    def _parse_skills(self, ir: PluginIR, manifest: dict[str, Any]) -> None:
        """Parse every safely contained SKILL.md below configured skill roots."""
        assert self.source is not None
        for skill_path in self._resolve_paths(manifest, "skills"):
            try:
                kind = self.source.kind(skill_path, context="skills")
                if kind == "file":
                    candidates = [skill_path] if skill_path.name == "SKILL.md" else []
                    scan_errors: list[str] = []
                else:
                    scanned, scan_errors = self.source.scan_files(skill_path, context="skills")
                    candidates = [item for item in scanned if item.name == "SKILL.md"]
                for error in scan_errors:
                    self._add_diagnostic(
                        Severity.ERROR, error, component_ref=f"skills:{skill_path}"
                    )
            except SourceSafetyError as error:
                self._add_diagnostic(
                    Severity.ERROR, str(error), component_ref=f"skills:{skill_path}"
                )
                continue
            for skill_md in candidates:
                skill = self._parse_skill(skill_md.parent, skill_md)
                if skill:
                    ir.components.append(skill)

    def _parse_skill(self, skill_dir: PurePosixPath, skill_md: PurePosixPath) -> Skill | None:
        """Parse one skill and capture all bytes it can emit."""
        assert self.source is not None
        try:
            content = self.source.read_file(
                skill_md, context=f"skill:{skill_dir.name}"
            ).content.decode("utf-8")
        except (SourceSafetyError, UnicodeDecodeError) as error:
            self._add_diagnostic(
                Severity.ERROR,
                f"Unsafe or non-text SKILL.md: {error}",
                component_ref=f"skill:{skill_dir.name}",
                source_path=self.plugin_path / skill_md,
            )
            return None
        frontmatter, _body = self._split_frontmatter(content)

        if not frontmatter:
            self._add_diagnostic(
                Severity.ERROR,
                "SKILL.md missing YAML frontmatter",
                source_path=self.plugin_path / skill_md,
            )
            return None

        try:
            meta = yaml.safe_load(frontmatter)
        except yaml.YAMLError as e:
            self._add_diagnostic(
                Severity.ERROR,
                f"Invalid YAML frontmatter: {e}",
                source_path=self.plugin_path / skill_md,
            )
            return None
        if not isinstance(meta, dict):
            self._add_diagnostic(
                Severity.ERROR,
                "SKILL.md frontmatter must be a mapping",
                source_path=self.plugin_path / skill_md,
            )
            return None

        raw_name = meta.get("name", skill_dir.name)
        if not isinstance(raw_name, str):
            self._add_diagnostic(
                Severity.ERROR,
                "Skill name must be a string",
                component_ref=f"skill:{skill_dir.name}",
                source_path=self.plugin_path / skill_md,
            )
            return None
        description = meta.get("description")
        name = self._slugify(raw_name, "skill", max_len=64)
        if name != raw_name:
            self._add_diagnostic(
                Severity.WARN,
                f"Normalized skill name '{raw_name}' → '{name}' for portability",
                component_ref=f"skill:{raw_name}",
                source_path=self.plugin_path / skill_md,
            )

        files: list[TextFile | BinaryFile] = []
        try:
            skill_files = list(self.source.walk_files(skill_dir, context=f"skill:{name}"))
            for source_path in skill_files:
                source_file = self.source.read_file(source_path, context=f"skill:{name}")
                relpath = source_path.relative_to(skill_dir).as_posix()
                try:
                    text = source_file.content.decode("utf-8")
                except UnicodeDecodeError:
                    files.append(
                        BinaryFile(
                            relpath=relpath,
                            content_b64=base64.b64encode(source_file.content).decode("ascii"),
                            executable=source_file.executable,
                        )
                    )
                else:
                    files.append(
                        TextFile(
                            relpath=relpath,
                            content=text,
                            executable=source_file.executable,
                        )
                    )
            includes = self._parse_skill_includes(meta, name)
        except SourceSafetyError as error:
            self._add_diagnostic(
                Severity.ERROR,
                str(error),
                component_ref=f"skill:{name}",
                source_path=self.plugin_path / skill_md,
            )
            return None
        if includes is None:
            return None

        try:
            skill = Skill(
                name=name,
                description=description,
                files=files,
                includes=includes,
                allowed_tools=self._parse_allowed_tools(meta.get("allowed-tools")),
                model=meta.get("model"),
                context=meta.get("context"),
                agent=meta.get("agent"),
                user_invocable=meta.get("user-invocable", True),
                disable_model_invocation=meta.get("disable-model-invocation", False),
            )
        except Exception as e:
            self._add_diagnostic(
                Severity.ERROR,
                f"Invalid skill definition: {e}",
                component_ref=f"skill:{raw_name}",
                source_path=self.plugin_path / skill_md,
            )
            return None

        # Run the target-neutral projection as a parser-time invariant check.
        projection = project_skill(skill, content)
        if projection.errors:
            for error in projection.errors:
                self._add_diagnostic(
                    Severity.ERROR,
                    error,
                    component_ref=f"skill:{name}",
                    source_path=self.plugin_path / skill_md,
                )
            return None
        return skill

    def _parse_skill_includes(
        self, meta: dict[str, Any], skill_name: str
    ) -> tuple[SkillInclude, ...] | None:
        """Parse exact plugin-relative regular files from skill build metadata."""
        assert self.source is not None
        raw = meta.get("x-ai-config-includes")
        if raw is None:
            return ()
        if not isinstance(raw, list):
            self._add_diagnostic(
                Severity.ERROR,
                "x-ai-config-includes must be a list of exact path strings",
                component_ref=f"skill:{skill_name}",
            )
            return None
        includes: list[SkillInclude] = []
        seen: set[str] = set()
        for value in raw:
            try:
                if isinstance(value, str) and value.startswith("./"):
                    raise SourceSafetyError(
                        f"skill:{skill_name} include path contains a dot component: {value!r}"
                    )
                relative = self.source.relative(value, context=f"skill:{skill_name} include")
                logical = relative.as_posix()
                if logical in seen:
                    raise SourceSafetyError(f"duplicate include declaration: {logical}")
                seen.add(logical)
                source_file = self.source.read_file(
                    relative,
                    context=f"skill:{skill_name} include",
                    reject_hardlinks=True,
                )
            except SourceSafetyError as error:
                self._add_diagnostic(
                    Severity.ERROR,
                    str(error),
                    component_ref=f"skill:{skill_name}",
                )
                return None
            try:
                source_file.content.decode("utf-8")
            except UnicodeDecodeError:
                kind = IncludeKind.BINARY
            else:
                kind = IncludeKind.TEXT
            includes.append(
                SkillInclude(
                    source_relative_path=logical,
                    projected_path=f"_shared/{logical}",
                    content=source_file.content,
                    kind=kind,
                    executable=source_file.executable,
                )
            )
        return tuple(includes)

    def _slugify(self, value: str, fallback_prefix: str, max_len: int | None = None) -> str:
        """Normalize names to lowercase kebab-case with safe fallback."""
        return normalize_portable_name(value, fallback_prefix, max_len)

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
        """Parse safely contained command files."""
        assert self.source is not None
        for cmd_path in self._resolve_paths(manifest, "commands"):
            try:
                kind = self.source.kind(cmd_path, context="commands")
                if kind == "file":
                    files = [cmd_path]
                    scan_errors: list[str] = []
                else:
                    scanned, scan_errors = self.source.scan_files(cmd_path, context="commands")
                    files = [item for item in scanned if item.parent == cmd_path]
                for error in scan_errors:
                    self._add_diagnostic(
                        Severity.ERROR, error, component_ref=f"commands:{cmd_path}"
                    )
                for md_file in files:
                    if md_file.suffix == ".md":
                        cmd = self._parse_command(md_file)
                        if cmd:
                            ir.components.append(cmd)
            except SourceSafetyError as error:
                self._add_diagnostic(
                    Severity.ERROR, str(error), component_ref=f"commands:{cmd_path}"
                )

    def _parse_command(self, cmd_path: PurePosixPath) -> Command | None:
        """Parse a single command markdown file."""
        assert self.source is not None
        try:
            content = self.source.read_file(
                cmd_path, context=f"command:{cmd_path.stem}"
            ).content.decode("utf-8")
        except (SourceSafetyError, UnicodeDecodeError) as error:
            self._add_diagnostic(
                Severity.ERROR, str(error), component_ref=f"command:{cmd_path.stem}"
            )
            return None
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
        """Parse safely contained agent definition files."""
        assert self.source is not None
        for agent_path in self._resolve_paths(manifest, "agents"):
            try:
                kind = self.source.kind(agent_path, context="agents")
                if kind == "file":
                    files = [agent_path]
                    scan_errors: list[str] = []
                else:
                    scanned, scan_errors = self.source.scan_files(agent_path, context="agents")
                    files = [item for item in scanned if item.parent == agent_path]
                for error in scan_errors:
                    self._add_diagnostic(
                        Severity.ERROR, error, component_ref=f"agents:{agent_path}"
                    )
                for md_file in files:
                    if md_file.suffix == ".md":
                        agent = self._parse_agent(md_file)
                        if agent:
                            ir.components.append(agent)
            except SourceSafetyError as error:
                self._add_diagnostic(
                    Severity.ERROR, str(error), component_ref=f"agents:{agent_path}"
                )

    def _parse_agent(self, agent_path: PurePosixPath) -> Agent | None:
        """Parse a single agent markdown file."""
        assert self.source is not None
        try:
            content = self.source.read_file(
                agent_path, context=f"agent:{agent_path.stem}"
            ).content.decode("utf-8")
        except (SourceSafetyError, UnicodeDecodeError) as error:
            self._add_diagnostic(
                Severity.ERROR, str(error), component_ref=f"agent:{agent_path.stem}"
            )
            return None
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

    def _load_json_component(
        self,
        value: Any,
        *,
        default_path: str,
        context: str,
    ) -> dict[str, Any] | None:
        """Load an inline object or one safe plugin-relative JSON file."""
        assert self.source is not None
        if value is None or value == "":
            try:
                relative = self.source.relative(default_path, context=context)
                source_file = self.source.read_file(relative, context=context)
            except SourceMissingError:
                return None
            except SourceSafetyError as error:
                self._add_diagnostic(
                    Severity.ERROR, str(error), component_ref=f"{context}:{default_path}"
                )
                return None
        elif isinstance(value, str):
            try:
                relative = self.source.relative(value, context=context)
                source_file = self.source.read_file(relative, context=context)
            except SourceSafetyError as error:
                self._add_diagnostic(
                    Severity.ERROR, str(error), component_ref=f"{context}:{value!r}"
                )
                return None
        elif isinstance(value, dict):
            return value
        else:
            self._add_diagnostic(
                Severity.ERROR,
                f"Manifest field '{context}' must be a path string or object",
                component_ref=f"manifest:{context}",
            )
            return None
        try:
            parsed = json.loads(source_file.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            self._add_diagnostic(
                Severity.ERROR,
                f"Invalid JSON in {context} config: {error}",
                component_ref=f"{context}:{relative}",
            )
            return None
        if not isinstance(parsed, dict):
            self._add_diagnostic(
                Severity.ERROR,
                f"{context} config must contain a JSON object",
                component_ref=f"{context}:{relative}",
            )
            return None
        return parsed

    def _parse_hooks(self, ir: PluginIR, manifest: dict[str, Any]) -> None:
        """Parse hooks configuration."""
        hooks_config = self._load_json_component(
            manifest.get("hooks"), default_path="hooks/hooks.json", context="hooks"
        )
        if hooks_config is None:
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
        mcp_config = self._load_json_component(
            manifest.get("mcpServers"), default_path=".mcp.json", context="mcpServers"
        )
        if mcp_config is None:
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
        lsp_config = self._load_json_component(
            manifest.get("lspServers"), default_path=".lsp.json", context="lspServers"
        )
        if lsp_config is None:
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
        diagnostics = list(self.diagnostics)
        diagnostics.append(Diagnostic(severity=Severity.ERROR, message=message))
        return PluginIR(
            identity=PluginIdentity(plugin_id="error", name="error"),
            diagnostics=diagnostics,
            source_path=self.plugin_path,
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
