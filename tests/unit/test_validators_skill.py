"""Tests for ai_config.validators.component.skill module."""

from pathlib import Path
from textwrap import dedent

import pytest

from ai_config.validators.component.skill import (
    validate_description,
    validate_name,
    validate_skill_directory,
)


class TestValidateName:
    """Tests for skill name validation per agentskills.io spec."""

    @pytest.mark.parametrize(
        "name,valid",
        [
            # Valid names
            ("pdf-processing", True),
            ("data-analysis", True),
            ("code-review", True),
            ("python-core", True),
            ("a", True),  # Single char valid
            ("a" * 64, True),  # Exactly 64 chars valid
            ("test123", True),  # Alphanumeric valid
            ("my-skill-v2", True),  # Version suffix valid
            # Invalid names - uppercase
            ("PDF-Processing", False),
            ("DataAnalysis", False),
            ("UPPERCASE", False),
            # Invalid names - hyphen rules
            ("-pdf", False),  # Cannot start with hyphen
            ("pdf-", False),  # Cannot end with hyphen
            ("pdf--processing", False),  # Consecutive hyphens not allowed
            ("-", False),  # Just hyphen
            ("--", False),  # Just hyphens
            # Invalid names - length
            ("a" * 65, False),  # Over 64 chars
            ("", False),  # Empty name
            # Invalid names - special characters
            ("pdf_processing", False),  # Underscores not allowed
            ("pdf.processing", False),  # Dots not allowed
            ("pdf processing", False),  # Spaces not allowed
            ("pdf@processing", False),  # @ not allowed
        ],
    )
    def test_name_validation(self, name: str, valid: bool) -> None:
        """Parametrized test for skill name validation."""
        errors = validate_name(name)
        if valid:
            assert errors == [], f"Expected '{name}' to be valid, got errors: {errors}"
        else:
            assert errors != [], f"Expected '{name}' to be invalid, but got no errors"

    def test_name_must_match_directory(self, tmp_path: Path) -> None:
        """Skill name in frontmatter must match directory name."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            dedent("""
            ---
            name: different-name
            description: A test skill.
            ---
            # Content
            """)
        )
        results = validate_skill_directory(skill_dir)
        assert any(
            "match" in r.message.lower() and "directory" in r.message.lower() for r in results
        )


class TestValidateDescription:
    """Tests for skill description validation."""

    def test_valid_description(self) -> None:
        """Valid description should return no errors."""
        errors = validate_description("A valid skill description.")
        assert errors == []

    def test_empty_description(self) -> None:
        """Empty description should return an error."""
        errors = validate_description("")
        assert len(errors) == 1
        assert "empty" in errors[0].lower() or "required" in errors[0].lower()

    def test_whitespace_only_description(self) -> None:
        """Whitespace-only description should return an error."""
        errors = validate_description("   \n\t  ")
        assert len(errors) == 1

    def test_description_at_max_length(self) -> None:
        """Description at exactly 1024 chars should be valid."""
        desc = "a" * 1024
        errors = validate_description(desc)
        assert errors == []

    def test_description_over_max_length(self) -> None:
        """Description over 1024 chars should return an error."""
        desc = "a" * 1025
        errors = validate_description(desc)
        assert len(errors) == 1
        assert "1024" in errors[0]


class TestSkillValidator:
    """Tests for the SkillValidator class."""

    @pytest.fixture
    def valid_skill_dir(self, tmp_path: Path) -> Path:
        """Create a valid skill directory for testing."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            dedent("""
            ---
            name: test-skill
            description: A test skill for validation testing.
            ---

            ## Instructions
            Test instructions here.
            """)
        )
        return skill_dir

    @pytest.fixture
    def skill_missing_name(self, tmp_path: Path) -> Path:
        """Skill with missing name in frontmatter."""
        skill_dir = tmp_path / "no-name-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            dedent("""
            ---
            description: A skill without a name.
            ---
            # Content
            """)
        )
        return skill_dir

    @pytest.fixture
    def skill_missing_description(self, tmp_path: Path) -> Path:
        """Skill with missing description in frontmatter."""
        skill_dir = tmp_path / "no-desc-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            dedent("""
            ---
            name: no-desc-skill
            ---
            # Content
            """)
        )
        return skill_dir

    @pytest.fixture
    def skill_invalid_name(self, tmp_path: Path) -> Path:
        """Skill with invalid name (uppercase)."""
        skill_dir = tmp_path / "InvalidName"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            dedent("""
            ---
            name: InvalidName
            description: A skill with an invalid name.
            ---
            # Content
            """)
        )
        return skill_dir

    @pytest.fixture
    def skill_no_frontmatter(self, tmp_path: Path) -> Path:
        """Skill without YAML frontmatter."""
        skill_dir = tmp_path / "no-frontmatter"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just a heading\nNo frontmatter here.")
        return skill_dir

    @pytest.fixture
    def skill_missing_skill_md(self, tmp_path: Path) -> Path:
        """Skill directory without SKILL.md file."""
        skill_dir = tmp_path / "missing-skill-md"
        skill_dir.mkdir()
        (skill_dir / "README.md").write_text("# Readme\nNot a skill file.")
        return skill_dir

    def test_valid_skill_passes(self, valid_skill_dir: Path) -> None:
        """Valid skill directory should pass all checks."""
        results = validate_skill_directory(valid_skill_dir)
        failures = [r for r in results if r.status == "fail"]
        assert failures == [], f"Expected no failures, got: {failures}"

    def test_missing_skill_md_fails(self, skill_missing_skill_md: Path) -> None:
        """Missing SKILL.md should fail validation."""
        results = validate_skill_directory(skill_missing_skill_md)
        assert any(r.status == "fail" and "SKILL.md" in r.message for r in results)

    def test_missing_name_fails(self, skill_missing_name: Path) -> None:
        """Missing name in frontmatter should fail."""
        results = validate_skill_directory(skill_missing_name)
        assert any(r.status == "fail" and "name" in r.message.lower() for r in results)

    def test_missing_description_fails(self, skill_missing_description: Path) -> None:
        """Missing description in frontmatter should fail."""
        results = validate_skill_directory(skill_missing_description)
        assert any(r.status == "fail" and "description" in r.message.lower() for r in results)

    def test_invalid_name_fails(self, skill_invalid_name: Path) -> None:
        """Invalid name (uppercase) should fail."""
        results = validate_skill_directory(skill_invalid_name)
        assert any(r.status == "fail" and "name" in r.message.lower() for r in results)

    def test_no_frontmatter_fails(self, skill_no_frontmatter: Path) -> None:
        """Skill without frontmatter should fail."""
        results = validate_skill_directory(skill_no_frontmatter)
        assert any(r.status == "fail" for r in results)


class TestSkillValidatorWithResources:
    """Tests for skill resource validation."""

    @pytest.fixture
    def skill_with_resources(self, tmp_path: Path) -> Path:
        """Create a skill with resources directory."""
        skill_dir = tmp_path / "skill-with-resources"
        skill_dir.mkdir()
        resources_dir = skill_dir / "resources"
        resources_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            dedent("""
            ---
            name: skill-with-resources
            description: A skill with resources.
            ---
            # Instructions
            See [resources/reference.md](resources/reference.md)
            """)
        )
        (resources_dir / "reference.md").write_text("# Reference\nSome content.")
        return skill_dir

    @pytest.fixture
    def skill_with_missing_resource(self, tmp_path: Path) -> Path:
        """Create a skill that references a missing resource."""
        skill_dir = tmp_path / "skill-missing-resource"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            dedent("""
            ---
            name: skill-missing-resource
            description: A skill referencing a missing resource.
            ---
            # Instructions
            See [resources/missing.md](resources/missing.md)
            """)
        )
        return skill_dir

    def test_valid_resources_pass(self, skill_with_resources: Path) -> None:
        """Skill with valid resource references should pass."""
        results = validate_skill_directory(skill_with_resources)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    def test_missing_resource_warns(self, skill_with_missing_resource: Path) -> None:
        """Skill referencing missing resource should warn."""
        results = validate_skill_directory(skill_with_missing_resource)
        # Missing resources should be a warning, not a failure
        warnings = [r for r in results if r.status == "warn"]
        assert any(
            "resource" in r.message.lower() or "missing" in r.message.lower() for r in warnings
        )
