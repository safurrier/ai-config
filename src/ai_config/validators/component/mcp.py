"""MCP (Model Context Protocol) validators for ai-config.

Validates .mcp.json configuration per the official Claude Code schema:
https://code.claude.com/docs/en/plugins-reference#mcp-servers
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from ai_config.validators.base import ValidationResult

if TYPE_CHECKING:
    from ai_config.validators.context import ValidationContext


class MCPValidator:
    """Validates .mcp.json configuration for plugins."""

    name = "mcp_validator"
    description = "Validates MCP server configuration files"

    async def validate(self, context: ValidationContext) -> list[ValidationResult]:
        """Validate MCP config for all configured plugins.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        # Create lookup map for installed plugins
        installed_map = {p.id: p for p in context.installed_plugins}

        for target in context.config.targets:
            if target.type != "claude":
                continue

            for plugin in target.config.plugins:
                installed = installed_map.get(plugin.id)
                if not installed:
                    continue

                install_path = Path(installed.install_path)
                if not install_path.exists():
                    continue

                # Check for .mcp.json
                mcp_json = install_path / ".mcp.json"
                if not mcp_json.exists():
                    # No MCP config is fine - not all plugins need MCP
                    continue

                # Validate .mcp.json
                try:
                    with open(mcp_json) as f:
                        mcp_config = json.load(f)
                except json.JSONDecodeError as e:
                    results.append(
                        ValidationResult(
                            check_name="mcp_json_valid",
                            status="fail",
                            message=f"Plugin '{plugin.id}' has invalid JSON in .mcp.json",
                            details=str(e),
                        )
                    )
                    continue
                except OSError as e:
                    results.append(
                        ValidationResult(
                            check_name="mcp_json_readable",
                            status="fail",
                            message=f"Failed to read .mcp.json for '{plugin.id}'",
                            details=str(e),
                        )
                    )
                    continue

                if not isinstance(mcp_config, dict):
                    results.append(
                        ValidationResult(
                            check_name="mcp_json_valid",
                            status="fail",
                            message=f"Plugin '{plugin.id}' .mcp.json is not a JSON object",
                        )
                    )
                    continue

                # Validate MCP server entries
                mcp_results = self._validate_mcp_servers(plugin.id, mcp_config)
                results.extend(mcp_results)

                if not any(r.status == "fail" for r in mcp_results):
                    results.append(
                        ValidationResult(
                            check_name="mcp_valid",
                            status="pass",
                            message=f"Plugin '{plugin.id}' MCP config is valid",
                        )
                    )

        return results

    def _detect_transport(self, server_config: dict) -> str | None:
        """Detect the transport type for an MCP server configuration.

        Args:
            server_config: The server configuration dict.

        Returns:
            "stdio", "http", "sse", or None if transport cannot be determined.
        """
        explicit_type = server_config.get("type")
        if explicit_type is not None:
            if explicit_type == "stdio":
                return "stdio"
            if explicit_type in ("streamable-http", "http"):
                return "http"
            if explicit_type == "sse":
                return "sse"
            return None

        if "command" in server_config:
            return "stdio"
        if "url" in server_config:
            return "http"
        return None

    def _validate_stdio_server(
        self, plugin_id: str, server_name: str, server_config: dict
    ) -> list[ValidationResult]:
        """Validate a stdio-transport MCP server.

        Args:
            plugin_id: The plugin identifier.
            server_name: The server name.
            server_config: The server configuration dict.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        command = server_config.get("command")
        if command is None:
            results.append(
                ValidationResult(
                    check_name="mcp_command_required",
                    status="fail",
                    message=f"MCP server '{server_name}' is missing required 'command' field",
                    details=f"Plugin: {plugin_id}",
                    fix_hint="Add 'command' field with the path to the MCP server executable",
                )
            )
            return results

        if not isinstance(command, str):
            results.append(
                ValidationResult(
                    check_name="mcp_command_type",
                    status="fail",
                    message=f"MCP server '{server_name}' command must be a string",
                    details=f"Plugin: {plugin_id}, got type: {type(command).__name__}",
                )
            )
            return results

        if not command.startswith("${") and not shutil.which(command):
            results.append(
                ValidationResult(
                    check_name="mcp_command_exists",
                    status="warn",
                    message=f"MCP server '{server_name}' command not found: {command}",
                    details=f"Plugin: {plugin_id}",
                    fix_hint=f"Install {command} or add it to PATH",
                )
            )

        args = server_config.get("args")
        if args is not None and not isinstance(args, list):
            results.append(
                ValidationResult(
                    check_name="mcp_args_format",
                    status="fail",
                    message=f"MCP server '{server_name}' args must be an array (list)",
                    details=f"Plugin: {plugin_id}",
                )
            )

        env = server_config.get("env")
        if env is not None and not isinstance(env, dict):
            results.append(
                ValidationResult(
                    check_name="mcp_env_format",
                    status="fail",
                    message=f"MCP server '{server_name}' env must be an object",
                    details=f"Plugin: {plugin_id}",
                )
            )

        cwd = server_config.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            results.append(
                ValidationResult(
                    check_name="mcp_cwd_format",
                    status="fail",
                    message=f"MCP server '{server_name}' cwd must be a string",
                    details=f"Plugin: {plugin_id}",
                )
            )

        return results

    def _validate_url_server(
        self, plugin_id: str, server_name: str, server_config: dict, transport: str
    ) -> list[ValidationResult]:
        """Validate a URL-based (HTTP/SSE) MCP server.

        Args:
            plugin_id: The plugin identifier.
            server_name: The server name.
            server_config: The server configuration dict.
            transport: The transport type ("http" or "sse").

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        url = server_config.get("url")
        if url is None:
            results.append(
                ValidationResult(
                    check_name="mcp_url_required",
                    status="fail",
                    message=f"MCP server '{server_name}' is missing required 'url' field",
                    details=f"Plugin: {plugin_id}",
                    fix_hint="Add 'url' field with the server endpoint URL",
                )
            )
            return results

        if not isinstance(url, str):
            results.append(
                ValidationResult(
                    check_name="mcp_url_type",
                    status="fail",
                    message=f"MCP server '{server_name}' url must be a string",
                    details=f"Plugin: {plugin_id}, got type: {type(url).__name__}",
                )
            )
            return results

        if not url.startswith(("http://", "https://")):
            results.append(
                ValidationResult(
                    check_name="mcp_url_format",
                    status="warn",
                    message=f"MCP server '{server_name}' url should start with http:// or https://",
                    details=f"Plugin: {plugin_id}, got: {url}",
                    fix_hint="Use an http:// or https:// URL",
                )
            )

        headers = server_config.get("headers")
        if headers is not None and not isinstance(headers, dict):
            results.append(
                ValidationResult(
                    check_name="mcp_headers_format",
                    status="fail",
                    message=f"MCP server '{server_name}' headers must be an object (dict)",
                    details=f"Plugin: {plugin_id}",
                )
            )

        if transport == "sse":
            results.append(
                ValidationResult(
                    check_name="mcp_sse_deprecated",
                    status="warn",
                    message=(
                        f"MCP server '{server_name}' uses SSE transport which is deprecated; "
                        "consider migrating to streamable-http"
                    ),
                    details=f"Plugin: {plugin_id}",
                )
            )

        return results

    def _validate_mcp_servers(self, plugin_id: str, mcp_config: dict) -> list[ValidationResult]:
        """Validate MCP server entries.

        Supports multiple transport types:
        - stdio: command-based servers (command, args, env, cwd)
        - http/streamable-http: URL-based servers (url, headers)
        - sse: Server-Sent Events servers (url, headers) — deprecated

        Args:
            plugin_id: The plugin identifier.
            mcp_config: The parsed .mcp.json content.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        mcp_servers = mcp_config.get("mcpServers", {})
        if not isinstance(mcp_servers, dict):
            results.append(
                ValidationResult(
                    check_name="mcp_servers_format",
                    status="fail",
                    message=f"Plugin '{plugin_id}' .mcp.json 'mcpServers' must be an object",
                )
            )
            return results

        for server_name, server_config in mcp_servers.items():
            if not isinstance(server_config, dict):
                results.append(
                    ValidationResult(
                        check_name="mcp_server_format",
                        status="fail",
                        message=f"MCP server '{server_name}' config must be an object",
                        details=f"Plugin: {plugin_id}",
                    )
                )
                continue

            transport = self._detect_transport(server_config)

            if transport == "stdio":
                results.extend(self._validate_stdio_server(plugin_id, server_name, server_config))
            elif transport in ("http", "sse"):
                results.extend(
                    self._validate_url_server(plugin_id, server_name, server_config, transport)
                )
            else:
                results.append(
                    ValidationResult(
                        check_name="mcp_transport_unknown",
                        status="fail",
                        message=(
                            f"MCP server '{server_name}' could not determine transport type; "
                            "provide 'command' for stdio or 'url' for HTTP"
                        ),
                        details=f"Plugin: {plugin_id}",
                        fix_hint=(
                            "Add 'command' field for stdio servers or 'url' field for HTTP servers"
                        ),
                    )
                )

        return results
