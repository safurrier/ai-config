"""MCP (Model Context Protocol) validators for ai-config.

Validates .mcp.json configuration per the official Claude Code schema:
https://code.claude.com/docs/en/plugins-reference#mcp-servers
"""

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

    async def validate(self, context: "ValidationContext") -> list[ValidationResult]:
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

    def _validate_mcp_servers(self, plugin_id: str, mcp_config: dict) -> list[ValidationResult]:
        """Validate MCP server entries.

        Official schema:
        {
          "mcpServers": {
            "server-name": {
              "command": "path/to/server",  // required
              "args": ["--flag", "value"],  // optional
              "env": { "VAR": "value" },    // optional
              "cwd": "working/dir"          // optional
            }
          }
        }

        Args:
            plugin_id: The plugin identifier.
            mcp_config: The parsed .mcp.json content.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        # Check mcpServers if present
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

            # Check command exists (required field)
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
                continue

            # Validate command is a string
            if not isinstance(command, str):
                results.append(
                    ValidationResult(
                        check_name="mcp_command_type",
                        status="fail",
                        message=f"MCP server '{server_name}' command must be a string",
                        details=f"Plugin: {plugin_id}, got type: {type(command).__name__}",
                    )
                )
                continue

            # Check if command is on PATH (only warn, don't fail - it might use variables)
            if not command.startswith("${") and not shutil.which(command):
                # Only warn if it's not a variable reference
                results.append(
                    ValidationResult(
                        check_name="mcp_command_exists",
                        status="warn",
                        message=f"MCP server '{server_name}' command not found: {command}",
                        details=f"Plugin: {plugin_id}",
                        fix_hint=f"Install {command} or add it to PATH",
                    )
                )

            # Check args is a list if present
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

            # Check env is a dict if present
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

            # Check cwd is a string if present
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
