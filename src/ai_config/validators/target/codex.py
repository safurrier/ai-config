"""Codex output validators for ai-config.

Validates that converted plugin output is valid for OpenAI Codex.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

from ai_config.validators.base import ValidationResult

# Valid Codex hook events (Codex doesn't support hooks, but included for completeness)
VALID_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


class CodexOutputValidator:
    """Validates Codex output directory structure and content."""

    name = "codex_output"
    description = "Validates Codex converted output"

    def validate_skills(self, output_dir: Path) -> list[ValidationResult]:
        """Validate skills in .codex/skills/ directory.

        Args:
            output_dir: Root output directory containing .codex/

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        skills_dir = output_dir / ".codex" / "skills"

        if not skills_dir.exists():
            results.append(
                ValidationResult(
                    check_name="codex_skills_dir",
                    status="pass",
                    message="No Codex skills directory (ok if no skills converted)",
                )
            )
            return results

        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]

        if not skill_dirs:
            results.append(
                ValidationResult(
                    check_name="codex_skills_empty",
                    status="warn",
                    message="Codex skills directory exists but is empty",
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
                    check_name=f"codex_skill_{skill_name}_md",
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
                        check_name=f"codex_skill_{skill_name}_frontmatter",
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
                        check_name=f"codex_skill_{skill_name}_name",
                        status="fail",
                        message=f"Missing 'name' field in {skill_md}",
                    )
                )
            elif not VALID_SKILL_NAME_PATTERN.match(name):
                results.append(
                    ValidationResult(
                        check_name=f"codex_skill_{skill_name}_name_format",
                        status="warn",
                        message=f"Skill name '{name}' should be lowercase kebab-case",
                        details="Valid pattern: ^[a-z0-9]+(-[a-z0-9]+)*$",
                    )
                )
            elif len(name) > MAX_SKILL_NAME_LENGTH:
                results.append(
                    ValidationResult(
                        check_name=f"codex_skill_{skill_name}_name_length",
                        status="warn",
                        message=f"Skill name '{name}' exceeds {MAX_SKILL_NAME_LENGTH} chars",
                    )
                )
            elif name != skill_dir.name:
                results.append(
                    ValidationResult(
                        check_name=f"codex_skill_{skill_name}_name_match",
                        status="warn",
                        message=f"Skill name '{name}' doesn't match directory '{skill_dir.name}'",
                    )
                )

            # Validate description
            description = frontmatter.get("description", "")
            if not description:
                results.append(
                    ValidationResult(
                        check_name=f"codex_skill_{skill_name}_description",
                        status="fail",
                        message=f"Missing 'description' field in {skill_md}",
                    )
                )
            elif len(description) > MAX_DESCRIPTION_LENGTH:
                results.append(
                    ValidationResult(
                        check_name=f"codex_skill_{skill_name}_description_length",
                        status="warn",
                        message=f"Description exceeds {MAX_DESCRIPTION_LENGTH} chars",
                    )
                )

            # All checks passed for this skill
            if not any(
                r.check_name.startswith(f"codex_skill_{skill_name}")
                and r.status in ("fail", "warn")
                for r in results
            ):
                results.append(
                    ValidationResult(
                        check_name=f"codex_skill_{skill_name}",
                        status="pass",
                        message=f"Skill '{skill_name}' is valid",
                    )
                )

        except Exception as e:
            results.append(
                ValidationResult(
                    check_name=f"codex_skill_{skill_name}_parse",
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

    def validate_mcp(self, output_dir: Path) -> list[ValidationResult]:
        """Validate MCP configuration in .codex/mcp-config.toml.

        Args:
            output_dir: Root output directory containing .codex/

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        mcp_file = output_dir / ".codex" / "mcp-config.toml"

        if not mcp_file.exists():
            results.append(
                ValidationResult(
                    check_name="codex_mcp_config",
                    status="pass",
                    message="No Codex MCP config (ok if no MCP servers converted)",
                )
            )
            return results

        try:
            content = mcp_file.read_text()
            config = tomllib.loads(content)

            # Check for mcp_servers section
            mcp_servers = config.get("mcp_servers", {})

            if not mcp_servers:
                results.append(
                    ValidationResult(
                        check_name="codex_mcp_servers",
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
                        check_name="codex_mcp_valid",
                        status="pass",
                        message=f"MCP config valid ({len(mcp_servers)} server(s))",
                    )
                )

        except tomllib.TOMLDecodeError as e:
            results.append(
                ValidationResult(
                    check_name="codex_mcp_parse",
                    status="fail",
                    message="Invalid TOML in MCP config",
                    details=str(e),
                    fix_hint="Fix TOML syntax errors in mcp-config.toml",
                )
            )
        except Exception as e:
            results.append(
                ValidationResult(
                    check_name="codex_mcp_error",
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
                    check_name=f"codex_mcp_{name}_type",
                    status="fail",
                    message=f"MCP server '{name}' needs 'command' or 'url'",
                )
            )
        elif has_command and has_url:
            results.append(
                ValidationResult(
                    check_name=f"codex_mcp_{name}_type",
                    status="warn",
                    message=f"MCP server '{name}' has both command and url",
                )
            )

        # Validate args if present
        if "args" in config and not isinstance(config["args"], list):
            results.append(
                ValidationResult(
                    check_name=f"codex_mcp_{name}_args",
                    status="fail",
                    message=f"MCP server '{name}' args must be an array",
                )
            )

        # Validate env if present
        if "env" in config and not isinstance(config["env"], dict):
            results.append(
                ValidationResult(
                    check_name=f"codex_mcp_{name}_env",
                    status="fail",
                    message=f"MCP server '{name}' env must be an object",
                )
            )

        return results

    def validate_prompts(self, output_dir: Path) -> list[ValidationResult]:
        """Validate prompts in .codex/prompts/ (deprecated but may exist).

        Args:
            output_dir: Root output directory containing .codex/

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        prompts_dir = output_dir / ".codex" / "prompts"

        if not prompts_dir.exists():
            return results  # No prompts is fine

        prompt_files = list(prompts_dir.glob("*.md"))
        if prompt_files:
            results.append(
                ValidationResult(
                    check_name="codex_prompts_deprecated",
                    status="warn",
                    message=f"Found {len(prompt_files)} prompts (prompts are deprecated in Codex)",
                    details="Consider converting to skills instead",
                )
            )

        return results

    def validate_all(self, output_dir: Path) -> list[ValidationResult]:
        """Run all Codex validations.

        Args:
            output_dir: Root output directory containing .codex/

        Returns:
            List of all validation results.
        """
        results: list[ValidationResult] = []

        codex_dir = output_dir / ".codex"
        if not codex_dir.exists():
            results.append(
                ValidationResult(
                    check_name="codex_output_exists",
                    status="warn",
                    message="No .codex directory found",
                    details=f"Expected .codex/ in {output_dir}",
                )
            )
            return results

        results.extend(self.validate_skills(output_dir))
        results.extend(self.validate_mcp(output_dir))
        results.extend(self.validate_prompts(output_dir))

        return results
