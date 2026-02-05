"""Cursor output validators for ai-config.

Validates that converted plugin output is valid for Cursor.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ai_config.validators.base import ValidationResult

# Cursor hook events (valid event types)
VALID_HOOK_EVENTS = frozenset(
    {
        "beforeShellExecution",
        "afterShellExecution",
        "beforeMCPExecution",
        "afterMCPExecution",
        "beforeReadFile",
        "afterFileEdit",
        "beforeSubmitPrompt",
        "stop",
    }
)

# Skill name validation (Cursor has some restrictions)
VALID_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024

# Reserved keywords that cannot be used in skill names
RESERVED_KEYWORDS = frozenset({"anthropic", "claude", "cursor"})


class CursorOutputValidator:
    """Validates Cursor output directory structure and content."""

    name = "cursor_output"
    description = "Validates Cursor converted output"

    def validate_skills(self, output_dir: Path) -> list[ValidationResult]:
        """Validate skills in .cursor/skills/ directory.

        Args:
            output_dir: Root output directory containing .cursor/

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        skills_dir = output_dir / ".cursor" / "skills"

        if not skills_dir.exists():
            results.append(
                ValidationResult(
                    check_name="cursor_skills_dir",
                    status="pass",
                    message="No Cursor skills directory (ok if no skills converted)",
                )
            )
            return results

        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]

        if not skill_dirs:
            results.append(
                ValidationResult(
                    check_name="cursor_skills_empty",
                    status="warn",
                    message="Cursor skills directory exists but is empty",
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
                    check_name=f"cursor_skill_{skill_name}_md",
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
                        check_name=f"cursor_skill_{skill_name}_frontmatter",
                        status="fail",
                        message=f"No YAML frontmatter in {skill_md}",
                        fix_hint="Add --- delimited YAML frontmatter with name and description",
                    )
                )
                return results

            # Validate name
            name = frontmatter.get("name", "")
            if not name:
                results.append(
                    ValidationResult(
                        check_name=f"cursor_skill_{skill_name}_name",
                        status="fail",
                        message=f"Missing 'name' field in {skill_md}",
                    )
                )
            else:
                # Check for reserved keywords
                name_lower = name.lower()
                for keyword in RESERVED_KEYWORDS:
                    if keyword in name_lower:
                        results.append(
                            ValidationResult(
                                check_name=f"cursor_skill_{skill_name}_reserved",
                                status="warn",
                                message=f"Skill name '{name}' contains reserved keyword '{keyword}'",
                                details="Cursor may reject skill names containing 'anthropic', 'claude', or 'cursor'",
                            )
                        )
                        break

                if not VALID_SKILL_NAME_PATTERN.match(name):
                    results.append(
                        ValidationResult(
                            check_name=f"cursor_skill_{skill_name}_name_format",
                            status="warn",
                            message=f"Skill name '{name}' should be lowercase kebab-case",
                            details="Valid pattern: ^[a-z0-9]+(-[a-z0-9]+)*$",
                        )
                    )
                elif len(name) > MAX_SKILL_NAME_LENGTH:
                    results.append(
                        ValidationResult(
                            check_name=f"cursor_skill_{skill_name}_name_length",
                            status="warn",
                            message=f"Skill name '{name}' exceeds {MAX_SKILL_NAME_LENGTH} chars",
                        )
                    )

            # Validate description
            description = frontmatter.get("description", "")
            if not description:
                results.append(
                    ValidationResult(
                        check_name=f"cursor_skill_{skill_name}_description",
                        status="fail",
                        message=f"Missing 'description' field in {skill_md}",
                    )
                )
            elif len(description) > MAX_DESCRIPTION_LENGTH:
                results.append(
                    ValidationResult(
                        check_name=f"cursor_skill_{skill_name}_description_length",
                        status="warn",
                        message=f"Description exceeds {MAX_DESCRIPTION_LENGTH} chars",
                    )
                )

            # All checks passed for this skill
            if not any(
                r.check_name.startswith(f"cursor_skill_{skill_name}")
                and r.status in ("fail", "warn")
                for r in results
            ):
                results.append(
                    ValidationResult(
                        check_name=f"cursor_skill_{skill_name}",
                        status="pass",
                        message=f"Skill '{skill_name}' is valid",
                    )
                )

        except Exception as e:
            results.append(
                ValidationResult(
                    check_name=f"cursor_skill_{skill_name}_parse",
                    status="fail",
                    message=f"Failed to parse {skill_md}",
                    details=str(e),
                )
            )

        return results

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
        """Validate commands in .cursor/commands/ directory.

        Args:
            output_dir: Root output directory containing .cursor/

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        commands_dir = output_dir / ".cursor" / "commands"

        if not commands_dir.exists():
            results.append(
                ValidationResult(
                    check_name="cursor_commands_dir",
                    status="pass",
                    message="No Cursor commands directory (ok if no commands converted)",
                )
            )
            return results

        command_files = list(commands_dir.glob("*.md"))

        if not command_files:
            results.append(
                ValidationResult(
                    check_name="cursor_commands_empty",
                    status="warn",
                    message="Cursor commands directory exists but is empty",
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
                        check_name=f"cursor_command_{cmd_name}_empty",
                        status="fail",
                        message=f"Command file {cmd_file.name} is empty",
                    )
                )
            else:
                results.append(
                    ValidationResult(
                        check_name=f"cursor_command_{cmd_name}",
                        status="pass",
                        message=f"Command '{cmd_name}' is valid",
                    )
                )
        except Exception as e:
            results.append(
                ValidationResult(
                    check_name=f"cursor_command_{cmd_name}_read",
                    status="fail",
                    message=f"Failed to read {cmd_file}",
                    details=str(e),
                )
            )

        return results

    def validate_hooks(self, output_dir: Path) -> list[ValidationResult]:
        """Validate hooks.json in .cursor/ directory.

        Args:
            output_dir: Root output directory containing .cursor/

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        hooks_file = output_dir / ".cursor" / "hooks.json"

        if not hooks_file.exists():
            results.append(
                ValidationResult(
                    check_name="cursor_hooks_file",
                    status="pass",
                    message="No Cursor hooks file (ok if no hooks converted)",
                )
            )
            return results

        try:
            content = hooks_file.read_text()
            hooks_data = json.loads(content)

            # Check version field
            if "version" not in hooks_data:
                results.append(
                    ValidationResult(
                        check_name="cursor_hooks_version",
                        status="fail",
                        message="Missing 'version' field in hooks.json",
                        fix_hint="Add 'version': 1 to hooks.json",
                    )
                )

            # Check hooks field
            hooks = hooks_data.get("hooks", {})
            if not isinstance(hooks, dict):
                results.append(
                    ValidationResult(
                        check_name="cursor_hooks_structure",
                        status="fail",
                        message="'hooks' field must be an object",
                    )
                )
            else:
                # Validate each event type
                for event_name, event_hooks in hooks.items():
                    if event_name not in VALID_HOOK_EVENTS:
                        results.append(
                            ValidationResult(
                                check_name=f"cursor_hooks_event_{event_name}",
                                status="warn",
                                message=f"Unknown hook event '{event_name}'",
                                details=f"Valid events: {', '.join(sorted(VALID_HOOK_EVENTS))}",
                            )
                        )

                    if not isinstance(event_hooks, list):
                        results.append(
                            ValidationResult(
                                check_name=f"cursor_hooks_event_{event_name}_type",
                                status="fail",
                                message=f"Hooks for event '{event_name}' must be an array",
                            )
                        )
                    else:
                        for i, hook in enumerate(event_hooks):
                            if not isinstance(hook, dict):
                                results.append(
                                    ValidationResult(
                                        check_name=f"cursor_hooks_event_{event_name}_{i}",
                                        status="fail",
                                        message=f"Hook {i} for event '{event_name}' must be an object",
                                    )
                                )
                            elif "command" not in hook:
                                results.append(
                                    ValidationResult(
                                        check_name=f"cursor_hooks_event_{event_name}_{i}_cmd",
                                        status="fail",
                                        message=f"Hook {i} for event '{event_name}' missing 'command' field",
                                    )
                                )

            # Overall success if no failures
            if not any(r.status == "fail" for r in results):
                results.append(
                    ValidationResult(
                        check_name="cursor_hooks_valid",
                        status="pass",
                        message="Hooks configuration is valid",
                    )
                )

        except json.JSONDecodeError as e:
            results.append(
                ValidationResult(
                    check_name="cursor_hooks_parse",
                    status="fail",
                    message="Invalid JSON in hooks.json",
                    details=str(e),
                    fix_hint="Fix JSON syntax errors in hooks.json",
                )
            )
        except Exception as e:
            results.append(
                ValidationResult(
                    check_name="cursor_hooks_error",
                    status="fail",
                    message="Failed to validate hooks.json",
                    details=str(e),
                )
            )

        return results

    def validate_mcp(self, output_dir: Path) -> list[ValidationResult]:
        """Validate MCP configuration in .cursor/mcp.json.

        Args:
            output_dir: Root output directory containing .cursor/

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        mcp_file = output_dir / ".cursor" / "mcp.json"

        if not mcp_file.exists():
            results.append(
                ValidationResult(
                    check_name="cursor_mcp_config",
                    status="pass",
                    message="No Cursor MCP config (ok if no MCP servers converted)",
                )
            )
            return results

        try:
            content = mcp_file.read_text()
            config = json.loads(content)

            # Check for mcpServers section (Cursor uses camelCase)
            mcp_servers = config.get("mcpServers", {})

            if not mcp_servers:
                results.append(
                    ValidationResult(
                        check_name="cursor_mcp_servers",
                        status="warn",
                        message="MCP config exists but has no servers defined",
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
                        check_name="cursor_mcp_valid",
                        status="pass",
                        message=f"MCP config valid ({len(mcp_servers)} server(s))",
                    )
                )

        except json.JSONDecodeError as e:
            results.append(
                ValidationResult(
                    check_name="cursor_mcp_parse",
                    status="fail",
                    message="Invalid JSON in MCP config",
                    details=str(e),
                    fix_hint="Fix JSON syntax errors in mcp.json",
                )
            )
        except Exception as e:
            results.append(
                ValidationResult(
                    check_name="cursor_mcp_error",
                    status="fail",
                    message="Failed to validate MCP config",
                    details=str(e),
                )
            )

        return results

    def _validate_mcp_server(self, name: str, config: dict) -> list[ValidationResult]:
        """Validate a single MCP server configuration."""
        results: list[ValidationResult] = []

        # Must have either command (stdio) or url (http)
        has_command = "command" in config
        has_url = "url" in config

        if not has_command and not has_url:
            results.append(
                ValidationResult(
                    check_name=f"cursor_mcp_{name}_type",
                    status="fail",
                    message=f"MCP server '{name}' needs 'command' or 'url'",
                )
            )
        elif has_command and has_url:
            results.append(
                ValidationResult(
                    check_name=f"cursor_mcp_{name}_type",
                    status="warn",
                    message=f"MCP server '{name}' has both command and url",
                )
            )

        # Validate args if present
        if "args" in config and not isinstance(config["args"], list):
            results.append(
                ValidationResult(
                    check_name=f"cursor_mcp_{name}_args",
                    status="fail",
                    message=f"MCP server '{name}' args must be an array",
                )
            )

        # Validate env if present
        if "env" in config and not isinstance(config["env"], dict):
            results.append(
                ValidationResult(
                    check_name=f"cursor_mcp_{name}_env",
                    status="fail",
                    message=f"MCP server '{name}' env must be an object",
                )
            )

        return results

    def validate_all(self, output_dir: Path) -> list[ValidationResult]:
        """Run all Cursor validations.

        Args:
            output_dir: Root output directory containing .cursor/

        Returns:
            List of all validation results.
        """
        results: list[ValidationResult] = []

        cursor_dir = output_dir / ".cursor"
        if not cursor_dir.exists():
            results.append(
                ValidationResult(
                    check_name="cursor_output_exists",
                    status="warn",
                    message="No .cursor directory found",
                    details=f"Expected .cursor/ in {output_dir}",
                )
            )
            return results

        results.extend(self.validate_skills(output_dir))
        results.extend(self.validate_commands(output_dir))
        results.extend(self.validate_hooks(output_dir))
        results.extend(self.validate_mcp(output_dir))

        return results
