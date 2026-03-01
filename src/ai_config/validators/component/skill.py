"""Skill validator for ai-config.

Validates skills per the agentskills.io specification:
https://agentskills.io/specification

Adapted from the reference implementation:
https://github.com/agentskills/agentskills/blob/main/skills-ref/src/skills_ref/validator.py
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml

from ai_config.validators.base import ValidationResult
from ai_config.validators.context import ValidationContext

# Maximum lengths per spec
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500

# Allowed frontmatter fields per spec
ALLOWED_FIELDS = frozenset(
    ["name", "description", "license", "allowed-tools", "metadata", "compatibility"]
)

# Regex for valid skill names: lowercase alphanumeric + hyphens
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _normalize_unicode(text: str) -> str:
    """Normalize Unicode text to NFC form."""
    return unicodedata.normalize("NFC", text)


def validate_name(name: str, directory_name: str | None = None) -> list[str]:
    """Validate skill name per agentskills.io specification.

    Args:
        name: The skill name to validate.
        directory_name: Optional directory name to check for match.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    if not name:
        errors.append("Skill name is required and cannot be empty")
        return errors

    # Normalize Unicode
    name = _normalize_unicode(name)

    # Check length
    if len(name) > MAX_NAME_LENGTH:
        errors.append(f"Skill name exceeds {MAX_NAME_LENGTH} characters (got {len(name)})")

    # Check for lowercase only
    if name != name.lower():
        errors.append("Skill name must be lowercase")

    # Check for valid characters (alphanumeric and hyphens only)
    if not NAME_PATTERN.match(name):
        if name.startswith("-"):
            errors.append("Skill name cannot start with a hyphen")
        elif name.endswith("-"):
            errors.append("Skill name cannot end with a hyphen")
        elif "--" in name:
            errors.append("Skill name cannot contain consecutive hyphens")
        else:
            errors.append("Skill name can only contain lowercase letters, numbers, and hyphens")

    # Check directory name match if provided
    if directory_name is not None and name != directory_name:
        errors.append(f"Skill name '{name}' does not match directory name '{directory_name}'")

    return errors


def validate_description(description: str) -> list[str]:
    """Validate skill description per agentskills.io specification.

    Args:
        description: The description to validate.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    if not description or not description.strip():
        errors.append("Skill description is required and cannot be empty")
        return errors

    # Normalize Unicode
    description = _normalize_unicode(description)

    # Check length
    if len(description) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            f"Skill description exceeds {MAX_DESCRIPTION_LENGTH} characters "
            f"(got {len(description)})"
        )

    return errors


def validate_compatibility(compatibility: str) -> list[str]:
    """Validate skill compatibility field per spec.

    Args:
        compatibility: The compatibility string to validate.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []

    if not isinstance(compatibility, str):
        errors.append("Skill compatibility must be a string")
        return errors

    if len(compatibility) > MAX_COMPATIBILITY_LENGTH:
        errors.append(
            f"Skill compatibility exceeds {MAX_COMPATIBILITY_LENGTH} characters "
            f"(got {len(compatibility)})"
        )

    return errors


def validate_metadata_fields(metadata: dict) -> list[str]:
    """Validate that metadata only contains allowed fields.

    Args:
        metadata: The frontmatter metadata dict.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []
    extra_fields = set(metadata.keys()) - ALLOWED_FIELDS
    if extra_fields:
        errors.append(f"Unknown frontmatter fields: {', '.join(sorted(extra_fields))}")
    return errors


def _parse_frontmatter(content: str) -> tuple[dict | None, str | None]:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: The markdown file content.

    Returns:
        Tuple of (frontmatter_dict, error_message).
    """
    content = content.strip()
    if not content.startswith("---"):
        return None, "SKILL.md must start with YAML frontmatter (---)"

    # Find the closing ---
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return None, "SKILL.md frontmatter is not properly closed (missing ---)"

    yaml_content = content[3:end_idx].strip()
    if not yaml_content:
        return None, "SKILL.md frontmatter is empty"

    try:
        metadata = yaml.safe_load(yaml_content)
        if not isinstance(metadata, dict):
            return None, "SKILL.md frontmatter must be a YAML mapping"
        return metadata, None
    except yaml.YAMLError as e:
        return None, f"Failed to parse SKILL.md frontmatter: {e}"


def _find_resource_references(content: str) -> list[str]:
    """Find all resource references in markdown content.

    Looks for markdown links like [text](resources/file.md)

    Args:
        content: The markdown content.

    Returns:
        List of resource paths referenced.
    """
    # Match markdown links to resources/ directory
    pattern = r"\[.*?\]\((resources/[^)]+)\)"
    matches = re.findall(pattern, content)
    return matches


def validate_skill_directory(skill_dir: Path) -> list[ValidationResult]:
    """Validate a skill directory.

    Args:
        skill_dir: Path to the skill directory.

    Returns:
        List of ValidationResult objects.
    """
    results: list[ValidationResult] = []
    dir_name = skill_dir.name

    # Check directory exists
    if not skill_dir.is_dir():
        results.append(
            ValidationResult(
                check_name="skill_directory_exists",
                status="fail",
                message=f"Skill directory does not exist: {skill_dir}",
            )
        )
        return results

    # Check SKILL.md exists
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        results.append(
            ValidationResult(
                check_name="skill_md_exists",
                status="fail",
                message=f"SKILL.md not found in {skill_dir}",
                fix_hint=f"Create {skill_md}",
            )
        )
        return results

    # Read and parse frontmatter
    try:
        content = skill_md.read_text()
    except OSError as e:
        results.append(
            ValidationResult(
                check_name="skill_md_readable",
                status="fail",
                message=f"Failed to read SKILL.md: {e}",
            )
        )
        return results

    metadata, parse_error = _parse_frontmatter(content)
    if parse_error:
        results.append(
            ValidationResult(
                check_name="frontmatter_valid",
                status="fail",
                message=parse_error,
            )
        )
        return results

    assert metadata is not None  # mypy

    # Validate required fields
    name = metadata.get("name")
    if not name:
        results.append(
            ValidationResult(
                check_name="name_required",
                status="fail",
                message="Skill name is required in frontmatter",
                fix_hint="Add 'name: your-skill-name' to the YAML frontmatter",
            )
        )
    else:
        name_errors = validate_name(name, dir_name)
        if name_errors:
            for error in name_errors:
                results.append(
                    ValidationResult(
                        check_name="name_valid",
                        status="fail",
                        message=f"Invalid skill name: {error}",
                    )
                )
        else:
            results.append(
                ValidationResult(
                    check_name="name_valid",
                    status="pass",
                    message=f"Skill name '{name}' is valid",
                )
            )

    description = metadata.get("description")
    if not description:
        results.append(
            ValidationResult(
                check_name="description_required",
                status="fail",
                message="Skill description is required in frontmatter",
                fix_hint="Add 'description: Your skill description' to the YAML frontmatter",
            )
        )
    else:
        desc_errors = validate_description(description)
        if desc_errors:
            for error in desc_errors:
                results.append(
                    ValidationResult(
                        check_name="description_valid",
                        status="fail",
                        message=f"Invalid skill description: {error}",
                    )
                )
        else:
            results.append(
                ValidationResult(
                    check_name="description_valid",
                    status="pass",
                    message="Skill description is valid",
                )
            )

    # Validate optional compatibility field if present
    compatibility = metadata.get("compatibility")
    if compatibility is not None:
        compat_errors = validate_compatibility(compatibility)
        for error in compat_errors:
            results.append(
                ValidationResult(
                    check_name="compatibility_valid",
                    status="fail",
                    message=f"Invalid compatibility field: {error}",
                )
            )

    # Check for unknown fields
    field_errors = validate_metadata_fields(metadata)
    for error in field_errors:
        results.append(
            ValidationResult(
                check_name="fields_valid",
                status="warn",
                message=error,
            )
        )

    # Validate resource references
    resource_refs = _find_resource_references(content)
    for ref in resource_refs:
        ref_path = skill_dir / ref
        if not ref_path.exists():
            results.append(
                ValidationResult(
                    check_name="resource_exists",
                    status="warn",
                    message=f"Referenced resource does not exist: {ref}",
                    details=f"Expected file at: {ref_path}",
                    fix_hint=f"Create {ref_path} or remove the reference",
                )
            )

    return results


class SkillValidator:
    """Validator for Claude Code plugin skills."""

    name = "skill_validator"
    description = "Validates skill directories per agentskills.io specification"

    async def validate(
        self,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        """Validate all skills in the configured plugins.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """

        results: list[ValidationResult] = []

        # Find skill directories from the config
        for target in context.config.targets:
            if target.type != "claude":
                continue

            for _mp_name, mp_config in target.config.marketplaces.items():
                if mp_config.source.value == "local":
                    mp_path = Path(mp_config.path)
                    if not mp_path.exists():
                        continue

                    # Look for plugins in the marketplace
                    for plugin_dir in mp_path.iterdir():
                        if not plugin_dir.is_dir():
                            continue
                        if plugin_dir.name.startswith("."):
                            continue

                        # Look for skills directory
                        skills_dir = plugin_dir / "skills"
                        if skills_dir.is_dir():
                            for skill_dir in skills_dir.iterdir():
                                if skill_dir.is_dir():
                                    skill_results = validate_skill_directory(skill_dir)
                                    results.extend(skill_results)

        return results
