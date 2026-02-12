"""OpenCode output validators for ai-config.

Validates that converted plugin output is valid for OpenCode.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ai_config.validators.base import ValidationResult

# OpenCode has stricter name validation than other tools
VALID_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


class OpenCodeOutputValidator:
    """Validates OpenCode output directory structure and content."""

    name = "opencode_output"
    description = "Validates OpenCode converted output"

    def validate_skills(self, output_dir: Path) -> list[ValidationResult]:
        """Validate skills in .opencode/skills/ directory.

        Args:
            output_dir: Root output directory containing .opencode/

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        skills_dir = output_dir / ".opencode" / "skills"

        if not skills_dir.exists():
            results.append(
                ValidationResult(
                    check_name="opencode_skills_dir",
                    status="pass",
                    message="No OpenCode skills directory (ok if no skills converted)",
                )
            )
            return results

        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]

        if not skill_dirs:
            results.append(
                ValidationResult(
                    check_name="opencode_skills_empty",
                    status="warn",
                    message="OpenCode skills directory exists but is empty",
                )
            )
            return results

        for skill_dir in skill_dirs:
            results.extend(self._validate_skill(skill_dir))

        return results

    def _validate_skill(self, skill_dir: Path) -> list[ValidationResult]:
        """Validate a single skill directory."""
        results: list[ValidationResult] = []
        skill_name = skill_dir.name

        # Check SKILL.md exists
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            results.append(
                ValidationResult(
                    check_name=f"opencode_skill_{skill_name}_md",
                    status="fail",
                    message=f"Missing SKILL.md in {skill_dir}",
                    fix_hint="Create a SKILL.md file with name and description frontmatter",
                )
            )
            return results

        # Parse and validate SKILL.md
        try:
            content = skill_md.read_text()
            frontmatter = self._parse_frontmatter(content)

            if not frontmatter:
                results.append(
                    ValidationResult(
                        check_name=f"opencode_skill_{skill_name}_frontmatter",
                        status="fail",
                        message=f"No YAML frontmatter in {skill_md}",
                        fix_hint="Add --- delimited YAML frontmatter with name and description",
                    )
                )
                return results

            # Validate name (OpenCode is strict about lowercase kebab-case)
            name = frontmatter.get("name", "")
            if not name:
                results.append(
                    ValidationResult(
                        check_name=f"opencode_skill_{skill_name}_name",
                        status="fail",
                        message=f"Missing 'name' field in {skill_md}",
                    )
                )
            elif not VALID_SKILL_NAME_PATTERN.match(name):
                # OpenCode enforces strict lowercase kebab-case
                results.append(
                    ValidationResult(
                        check_name=f"opencode_skill_{skill_name}_name_format",
                        status="fail",  # Fail for OpenCode, not just warn
                        message=f"Skill name '{name}' must be lowercase kebab-case",
                        details="OpenCode requires: ^[a-z0-9]+(-[a-z0-9]+)*$ (strict)",
                        fix_hint=f"Rename to: {self._to_kebab_case(name)}",
                    )
                )
            elif len(name) > MAX_SKILL_NAME_LENGTH:
                results.append(
                    ValidationResult(
                        check_name=f"opencode_skill_{skill_name}_name_length",
                        status="warn",
                        message=f"Skill name '{name}' exceeds {MAX_SKILL_NAME_LENGTH} chars",
                    )
                )
            elif name != skill_dir.name:
                results.append(
                    ValidationResult(
                        check_name=f"opencode_skill_{skill_name}_name_match",
                        status="warn",
                        message=f"Skill name '{name}' doesn't match directory '{skill_dir.name}'",
                    )
                )

            # Validate description
            description = frontmatter.get("description", "")
            if not description:
                results.append(
                    ValidationResult(
                        check_name=f"opencode_skill_{skill_name}_description",
                        status="fail",
                        message=f"Missing 'description' field in {skill_md}",
                    )
                )
            elif len(description) > MAX_DESCRIPTION_LENGTH:
                results.append(
                    ValidationResult(
                        check_name=f"opencode_skill_{skill_name}_description_length",
                        status="warn",
                        message=f"Description exceeds {MAX_DESCRIPTION_LENGTH} chars",
                    )
                )

            # All checks passed for this skill
            if not any(
                r.check_name.startswith(f"opencode_skill_{skill_name}")
                and r.status in ("fail", "warn")
                for r in results
            ):
                results.append(
                    ValidationResult(
                        check_name=f"opencode_skill_{skill_name}",
                        status="pass",
                        message=f"Skill '{skill_name}' is valid",
                    )
                )

        except Exception as e:
            results.append(
                ValidationResult(
                    check_name=f"opencode_skill_{skill_name}_parse",
                    status="fail",
                    message=f"Failed to parse {skill_md}",
                    details=str(e),
                )
            )

        return results

    def _to_kebab_case(self, name: str) -> str:
        """Convert a name to lowercase kebab-case."""
        # Replace underscores and spaces with hyphens
        name = re.sub(r"[_\s]+", "-", name)
        # Insert hyphen before uppercase letters
        name = re.sub(r"([a-z])([A-Z])", r"\1-\2", name)
        # Lowercase and collapse multiple hyphens
        name = re.sub(r"-+", "-", name.lower())
        # Remove non-alphanumeric except hyphens
        name = re.sub(r"[^a-z0-9-]", "", name)
        # Strip leading/trailing hyphens
        return name.strip("-")

    def _parse_frontmatter(self, content: str) -> dict | None:
        """Parse YAML frontmatter from SKILL.md content."""
        import yaml

        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            return yaml.safe_load(parts[1])
        except yaml.YAMLError:
            return None

    def validate_commands(self, output_dir: Path) -> list[ValidationResult]:
        """Validate commands in .opencode/commands/ directory.

        Args:
            output_dir: Root output directory containing .opencode/

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        commands_dir = output_dir / ".opencode" / "commands"

        if not commands_dir.exists():
            results.append(
                ValidationResult(
                    check_name="opencode_commands_dir",
                    status="pass",
                    message="No OpenCode commands directory (ok if no commands converted)",
                )
            )
            return results

        command_files = list(commands_dir.glob("*.md"))

        if not command_files:
            results.append(
                ValidationResult(
                    check_name="opencode_commands_empty",
                    status="warn",
                    message="OpenCode commands directory exists but is empty",
                )
            )
            return results

        for cmd_file in command_files:
            results.extend(self._validate_command(cmd_file))

        return results

    def _validate_command(self, cmd_file: Path) -> list[ValidationResult]:
        """Validate a single command file."""
        results: list[ValidationResult] = []
        cmd_name = cmd_file.stem

        try:
            content = cmd_file.read_text()
            if not content.strip():
                results.append(
                    ValidationResult(
                        check_name=f"opencode_command_{cmd_name}_empty",
                        status="fail",
                        message=f"Command file {cmd_file.name} is empty",
                    )
                )
            else:
                results.append(
                    ValidationResult(
                        check_name=f"opencode_command_{cmd_name}",
                        status="pass",
                        message=f"Command '{cmd_name}' is valid",
                    )
                )
        except Exception as e:
            results.append(
                ValidationResult(
                    check_name=f"opencode_command_{cmd_name}_read",
                    status="fail",
                    message=f"Failed to read {cmd_file}",
                    details=str(e),
                )
            )

        return results

    def validate_mcp(self, output_dir: Path) -> list[ValidationResult]:
        """Validate MCP configuration in opencode.json.

        Args:
            output_dir: Root output directory

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        mcp_file = output_dir / "opencode.json"

        if not mcp_file.exists():
            results.append(
                ValidationResult(
                    check_name="opencode_mcp_config",
                    status="pass",
                    message="No OpenCode config (ok if no MCP servers converted)",
                )
            )
            return results

        try:
            content = mcp_file.read_text()
            config = json.loads(content)

            # Check for mcp section (OpenCode uses lowercase)
            mcp_servers = config.get("mcp", {})

            if not mcp_servers:
                results.append(
                    ValidationResult(
                        check_name="opencode_mcp_servers",
                        status="warn",
                        message="OpenCode config exists but has no MCP servers defined",
                    )
                )
                return results

            # Validate each server
            for server_name, server_config in mcp_servers.items():
                server_results = self._validate_mcp_server(server_name, server_config)
                results.extend(server_results)

            # Overall success if no failures
            if not any(r.status == "fail" for r in results):
                results.append(
                    ValidationResult(
                        check_name="opencode_mcp_valid",
                        status="pass",
                        message=f"MCP config valid ({len(mcp_servers)} server(s))",
                    )
                )

        except json.JSONDecodeError as e:
            results.append(
                ValidationResult(
                    check_name="opencode_mcp_parse",
                    status="fail",
                    message="Invalid JSON in OpenCode config",
                    details=str(e),
                    fix_hint="Fix JSON syntax errors in opencode.json",
                )
            )
        except Exception as e:
            results.append(
                ValidationResult(
                    check_name="opencode_mcp_error",
                    status="fail",
                    message="Failed to validate OpenCode config",
                    details=str(e),
                )
            )

        return results

    def _validate_mcp_server(self, name: str, config: dict) -> list[ValidationResult]:
        """Validate a single MCP server configuration."""
        results: list[ValidationResult] = []

        # Must have command (OpenCode uses array format)
        if "command" not in config:
            results.append(
                ValidationResult(
                    check_name=f"opencode_mcp_{name}_command",
                    status="fail",
                    message=f"MCP server '{name}' needs 'command' field",
                )
            )
        else:
            # OpenCode expects command as array
            cmd = config["command"]
            if isinstance(cmd, str):
                results.append(
                    ValidationResult(
                        check_name=f"opencode_mcp_{name}_command_type",
                        status="warn",
                        message=f"MCP server '{name}' command should be an array",
                        details='OpenCode prefers command as array: ["cmd", "arg1", "arg2"]',
                    )
                )
            elif not isinstance(cmd, list):
                results.append(
                    ValidationResult(
                        check_name=f"opencode_mcp_{name}_command_type",
                        status="fail",
                        message=f"MCP server '{name}' command must be a string or array",
                    )
                )

        # Validate environment if present (OpenCode uses "environment" not "env")
        if "environment" in config and not isinstance(config["environment"], dict):
            results.append(
                ValidationResult(
                    check_name=f"opencode_mcp_{name}_env",
                    status="fail",
                    message=f"MCP server '{name}' environment must be an object",
                )
            )

        # Check for old "env" key (should be "environment")
        if "env" in config:
            results.append(
                ValidationResult(
                    check_name=f"opencode_mcp_{name}_env_key",
                    status="warn",
                    message=f"MCP server '{name}' uses 'env', should be 'environment'",
                    details="OpenCode expects 'environment' key for environment variables",
                )
            )

        return results

    def validate_lsp(self, output_dir: Path) -> list[ValidationResult]:
        """Validate LSP configuration in opencode.lsp.json.

        Args:
            output_dir: Root output directory

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        lsp_file = output_dir / "opencode.lsp.json"

        if not lsp_file.exists():
            results.append(
                ValidationResult(
                    check_name="opencode_lsp_config",
                    status="pass",
                    message="No OpenCode LSP config (ok if no LSP servers converted)",
                )
            )
            return results

        try:
            content = lsp_file.read_text()
            config = json.loads(content)

            # Check for lsp section
            lsp_servers = config.get("lsp", {})

            if not lsp_servers:
                results.append(
                    ValidationResult(
                        check_name="opencode_lsp_servers",
                        status="warn",
                        message="LSP config exists but has no servers defined",
                    )
                )
                return results

            # Validate each LSP server
            for server_name, server_config in lsp_servers.items():
                server_results = self._validate_lsp_server(server_name, server_config)
                results.extend(server_results)

            # Overall success if no failures
            if not any(r.status == "fail" for r in results):
                results.append(
                    ValidationResult(
                        check_name="opencode_lsp_valid",
                        status="pass",
                        message=f"LSP config valid ({len(lsp_servers)} server(s))",
                    )
                )

        except json.JSONDecodeError as e:
            results.append(
                ValidationResult(
                    check_name="opencode_lsp_parse",
                    status="fail",
                    message="Invalid JSON in LSP config",
                    details=str(e),
                    fix_hint="Fix JSON syntax errors in opencode.lsp.json",
                )
            )
        except Exception as e:
            results.append(
                ValidationResult(
                    check_name="opencode_lsp_error",
                    status="fail",
                    message="Failed to validate LSP config",
                    details=str(e),
                )
            )

        return results

    def _validate_lsp_server(self, name: str, config: dict) -> list[ValidationResult]:
        """Validate a single LSP server configuration."""
        results: list[ValidationResult] = []

        # Must have command
        if "command" not in config:
            results.append(
                ValidationResult(
                    check_name=f"opencode_lsp_{name}_command",
                    status="fail",
                    message=f"LSP server '{name}' needs 'command' field",
                )
            )

        # Check for languages
        if "languages" not in config:
            results.append(
                ValidationResult(
                    check_name=f"opencode_lsp_{name}_languages",
                    status="warn",
                    message=f"LSP server '{name}' has no 'languages' field",
                    details="Specify which languages this server handles",
                )
            )
        elif not isinstance(config["languages"], list):
            results.append(
                ValidationResult(
                    check_name=f"opencode_lsp_{name}_languages_type",
                    status="fail",
                    message=f"LSP server '{name}' languages must be an array",
                )
            )

        return results

    def validate_all(self, output_dir: Path) -> list[ValidationResult]:
        """Run all OpenCode validations.

        Args:
            output_dir: Root output directory containing .opencode/

        Returns:
            List of all validation results.
        """
        results: list[ValidationResult] = []

        opencode_dir = output_dir / ".opencode"
        if not opencode_dir.exists():
            results.append(
                ValidationResult(
                    check_name="opencode_output_exists",
                    status="warn",
                    message="No .opencode directory found",
                    details=f"Expected .opencode/ in {output_dir}",
                )
            )
            return results

        results.extend(self.validate_skills(output_dir))
        results.extend(self.validate_commands(output_dir))
        results.extend(self.validate_mcp(output_dir))
        results.extend(self.validate_lsp(output_dir))

        return results
