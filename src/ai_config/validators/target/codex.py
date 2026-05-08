"""Codex output validators for ai-config.

Validates that converted plugin output is valid for OpenAI Codex.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

from ai_config.validators.base import ValidationResult

VALID_CODEX_HOOK_EVENTS = {
    "SessionStart",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "UserPromptSubmit",
    "Stop",
}
VALID_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


class CodexOutputValidator:
    """Validates Codex output directory structure and content."""

    name = "codex_output"
    description = "Validates Codex converted output"

    def validate_skills(self, output_dir: Path) -> list[ValidationResult]:
        """Validate Codex Agent Skills in .agents/skills/."""
        results: list[ValidationResult] = []
        skills_dir = output_dir / ".agents" / "skills"
        legacy_skills_dir = output_dir / ".codex" / "skills"

        if legacy_skills_dir.exists():
            results.append(
                ValidationResult(
                    check_name="codex_legacy_skills_dir",
                    status="warn",
                    message="Found legacy .codex/skills directory",
                    details="Current Codex discovers Agent Skills from .agents/skills and $HOME/.agents/skills",
                    fix_hint="Move skills to .agents/skills",
                )
            )

        if not skills_dir.exists():
            results.append(
                ValidationResult(
                    check_name="codex_skills_dir",
                    status="pass",
                    message="No Codex Agent Skills directory (ok if no skills converted)",
                )
            )
            return results

        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]

        if not skill_dirs:
            results.append(
                ValidationResult(
                    check_name="codex_skills_empty",
                    status="warn",
                    message="Codex Agent Skills directory exists but is empty",
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

    def _load_config(self, output_dir: Path) -> tuple[dict, list[ValidationResult]]:
        """Load .codex/config.toml and return config plus validation results."""
        results: list[ValidationResult] = []
        config_file = output_dir / ".codex" / "config.toml"
        legacy_mcp_file = output_dir / ".codex" / "mcp-config.toml"

        if legacy_mcp_file.exists():
            results.append(
                ValidationResult(
                    check_name="codex_legacy_mcp_config",
                    status="warn",
                    message="Found legacy .codex/mcp-config.toml",
                    details="Current Codex reads MCP servers from .codex/config.toml",
                    fix_hint="Move MCP servers under [mcp_servers.*] in .codex/config.toml",
                )
            )

        if not config_file.exists():
            return {}, results

        try:
            return tomllib.loads(config_file.read_text()), results
        except tomllib.TOMLDecodeError as e:
            results.append(
                ValidationResult(
                    check_name="codex_config_parse",
                    status="fail",
                    message="Invalid TOML in Codex config",
                    details=str(e),
                    fix_hint="Fix TOML syntax errors in .codex/config.toml",
                )
            )
        except Exception as e:
            results.append(
                ValidationResult(
                    check_name="codex_config_error",
                    status="fail",
                    message="Failed to validate Codex config",
                    details=str(e),
                )
            )

        return {}, results

    def validate_mcp(self, output_dir: Path) -> list[ValidationResult]:
        """Validate MCP configuration in .codex/config.toml."""
        results: list[ValidationResult] = []
        config, config_results = self._load_config(output_dir)
        results.extend(config_results)

        if any(r.status == "fail" for r in results):
            return results

        if not config:
            results.append(
                ValidationResult(
                    check_name="codex_mcp_config",
                    status="pass",
                    message="No Codex config.toml (ok if no MCP servers converted)",
                )
            )
            return results

        try:
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

        except Exception as e:
            results.append(
                ValidationResult(
                    check_name="codex_mcp_error",
                    status="fail",
                    message="Failed to validate MCP servers",
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

    def validate_hooks(self, output_dir: Path) -> list[ValidationResult]:
        """Validate Codex hooks.json and feature flag in config.toml."""
        results: list[ValidationResult] = []
        hooks_file = output_dir / ".codex" / "hooks.json"

        if not hooks_file.exists():
            return results

        config, config_results = self._load_config(output_dir)
        results.extend(config_results)

        features = config.get("features", {}) if isinstance(config, dict) else {}
        if features.get("codex_hooks") is not True:
            results.append(
                ValidationResult(
                    check_name="codex_hooks_feature_flag",
                    status="warn",
                    message="Codex hooks file exists but features.codex_hooks is not enabled",
                    fix_hint="Add [features] codex_hooks = true to .codex/config.toml",
                )
            )

        try:
            hooks_data = json.loads(hooks_file.read_text())
        except json.JSONDecodeError as e:
            results.append(
                ValidationResult(
                    check_name="codex_hooks_parse",
                    status="fail",
                    message="Invalid JSON in .codex/hooks.json",
                    details=str(e),
                    fix_hint="Fix JSON syntax errors in .codex/hooks.json",
                )
            )
            return results

        hooks = hooks_data.get("hooks")
        if not isinstance(hooks, dict):
            results.append(
                ValidationResult(
                    check_name="codex_hooks_structure",
                    status="fail",
                    message=".codex/hooks.json must contain a hooks object",
                )
            )
            return results

        for event_name, groups in hooks.items():
            if event_name not in VALID_CODEX_HOOK_EVENTS:
                results.append(
                    ValidationResult(
                        check_name=f"codex_hooks_event_{event_name}",
                        status="fail",
                        message=f"Unsupported Codex hook event '{event_name}'",
                    )
                )
                continue
            if not isinstance(groups, list):
                results.append(
                    ValidationResult(
                        check_name=f"codex_hooks_event_{event_name}_type",
                        status="fail",
                        message=f"Codex hook event '{event_name}' must be an array",
                    )
                )
                continue
            for i, group in enumerate(groups):
                if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                    results.append(
                        ValidationResult(
                            check_name=f"codex_hooks_event_{event_name}_{i}",
                            status="fail",
                            message=f"Codex hook group {event_name}[{i}] must contain hooks array",
                        )
                    )
                    continue
                for j, hook in enumerate(group["hooks"]):
                    if not isinstance(hook, dict):
                        results.append(
                            ValidationResult(
                                check_name=f"codex_hooks_event_{event_name}_{i}_{j}",
                                status="fail",
                                message=f"Codex hook {event_name}[{i}].hooks[{j}] must be an object",
                            )
                        )
                    elif hook.get("type") != "command" or not isinstance(hook.get("command"), str):
                        results.append(
                            ValidationResult(
                                check_name=f"codex_hooks_event_{event_name}_{i}_{j}_command",
                                status="fail",
                                message=f"Codex hook {event_name}[{i}].hooks[{j}] must be a command hook",
                            )
                        )

        if not any(r.status == "fail" for r in results):
            results.append(
                ValidationResult(
                    check_name="codex_hooks_valid",
                    status="pass",
                    message=f"Codex hooks valid ({len(hooks)} event(s))",
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
        agents_dir = output_dir / ".agents"
        if not codex_dir.exists() and not agents_dir.exists():
            results.append(
                ValidationResult(
                    check_name="codex_output_exists",
                    status="warn",
                    message="No Codex output found",
                    details=f"Expected .agents/ and/or .codex/ in {output_dir}",
                )
            )
            return results

        results.extend(self.validate_skills(output_dir))
        results.extend(self.validate_mcp(output_dir))
        results.extend(self.validate_hooks(output_dir))
        results.extend(self.validate_prompts(output_dir))

        return results
