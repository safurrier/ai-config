"""Pi output validators for ai-config.

Validates that converted plugin output is valid for Pi (Agent Skills standard).
"""

from __future__ import annotations

import re
from pathlib import Path

from ai_config.validators.base import ValidationResult

# Agent Skills standard constraints
VALID_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


class PiOutputValidator:
    """Validates Pi output directory structure and content."""

    name = "pi_output"
    description = "Validates Pi converted output"

    def validate_skills(self, output_dir: Path) -> list[ValidationResult]:
        """Validate skills in .pi/skills/ or .pi/agent/skills/ directory."""
        results: list[ValidationResult] = []
        # Check both project (.pi/skills/) and user (.pi/agent/skills/) locations
        skills_dir = output_dir / ".pi" / "skills"
        agent_skills_dir = output_dir / ".pi" / "agent" / "skills"
        if agent_skills_dir.exists():
            skills_dir = agent_skills_dir

        if not skills_dir.exists():
            results.append(
                ValidationResult(
                    check_name="pi_skills_dir",
                    status="pass",
                    message="No Pi skills directory (ok if no skills converted)",
                )
            )
            return results

        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]

        if not skill_dirs:
            results.append(
                ValidationResult(
                    check_name="pi_skills_empty",
                    status="warn",
                    message="Pi skills directory exists but is empty",
                )
            )
            return results

        for skill_dir in skill_dirs:
            results.extend(self._validate_skill(skill_dir))

        return results

    def _validate_skill(self, skill_dir: Path) -> list[ValidationResult]:
        """Validate a single skill directory."""
        results: list[ValidationResult] = []
        dir_name = skill_dir.name

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            results.append(
                ValidationResult(
                    check_name=f"pi_skill_{dir_name}_md",
                    status="fail",
                    message=f"Missing SKILL.md in {skill_dir}",
                    fix_hint="Create a SKILL.md file with name and description frontmatter",
                )
            )
            return results

        try:
            content = skill_md.read_text()
            frontmatter = self._parse_frontmatter(content)

            if not frontmatter:
                results.append(
                    ValidationResult(
                        check_name=f"pi_skill_{dir_name}_frontmatter",
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
                        check_name=f"pi_skill_{dir_name}_name",
                        status="fail",
                        message=f"Missing 'name' field in {skill_md}",
                    )
                )
            elif not VALID_SKILL_NAME_PATTERN.match(name):
                results.append(
                    ValidationResult(
                        check_name=f"pi_skill_{dir_name}_name_format",
                        status="warn",
                        message=f"Skill name '{name}' should be lowercase kebab-case",
                        details="Valid pattern: ^[a-z0-9]+(-[a-z0-9]+)*$",
                    )
                )
            elif len(name) > MAX_SKILL_NAME_LENGTH:
                results.append(
                    ValidationResult(
                        check_name=f"pi_skill_{dir_name}_name_length",
                        status="warn",
                        message=f"Skill name '{name}' exceeds {MAX_SKILL_NAME_LENGTH} chars",
                    )
                )

            # Validate description (required — pi skips skills without descriptions)
            description = frontmatter.get("description", "")
            if not description:
                results.append(
                    ValidationResult(
                        check_name=f"pi_skill_{dir_name}_description",
                        status="fail",
                        message=f"Missing 'description' in {skill_md} (Pi won't load this skill)",
                        fix_hint="Add a description field — Pi requires it to load the skill",
                    )
                )
            elif len(description) > MAX_DESCRIPTION_LENGTH:
                results.append(
                    ValidationResult(
                        check_name=f"pi_skill_{dir_name}_description_length",
                        status="warn",
                        message=f"Description exceeds {MAX_DESCRIPTION_LENGTH} chars",
                    )
                )

            # All checks passed for this skill
            if not any(
                r.check_name.startswith(f"pi_skill_{dir_name}") and r.status in ("fail", "warn")
                for r in results
            ):
                results.append(
                    ValidationResult(
                        check_name=f"pi_skill_{dir_name}",
                        status="pass",
                        message=f"Skill '{dir_name}' is valid",
                    )
                )

        except Exception as e:
            results.append(
                ValidationResult(
                    check_name=f"pi_skill_{dir_name}_parse",
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

    def validate_prompts(self, output_dir: Path) -> list[ValidationResult]:
        """Validate prompt templates in .pi/prompts/ or .pi/agent/prompts/ directory."""
        results: list[ValidationResult] = []
        prompts_dir = output_dir / ".pi" / "prompts"
        agent_prompts_dir = output_dir / ".pi" / "agent" / "prompts"
        if agent_prompts_dir.exists():
            prompts_dir = agent_prompts_dir

        if not prompts_dir.exists():
            return results  # No prompts is fine

        prompt_files = list(prompts_dir.glob("*.md"))
        if prompt_files:
            results.append(
                ValidationResult(
                    check_name="pi_prompts_valid",
                    status="pass",
                    message=f"Found {len(prompt_files)} prompt template(s)",
                )
            )

        return results

    def validate_all(self, output_dir: Path) -> list[ValidationResult]:
        """Run all Pi validations."""
        results: list[ValidationResult] = []

        pi_dir = output_dir / ".pi"
        if not pi_dir.exists():
            results.append(
                ValidationResult(
                    check_name="pi_output_exists",
                    status="warn",
                    message="No .pi directory found",
                    details=f"Expected .pi/ in {output_dir}",
                )
            )
            return results

        results.extend(self.validate_skills(output_dir))
        results.extend(self.validate_prompts(output_dir))

        return results
