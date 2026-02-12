"""Tests for doctor command --target option.

These tests verify that the doctor command can validate converted plugin output
for each target tool (Codex, Cursor, OpenCode).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_config.cli import main


@pytest.fixture
def runner() -> CliRunner:
    """Click test runner."""
    return CliRunner()


@pytest.fixture
def codex_output_dir(tmp_path: Path) -> Path:
    """Create a valid Codex output directory."""
    codex_dir = tmp_path / ".codex"
    skills_dir = codex_dir / "skills" / "my-skill"
    skills_dir.mkdir(parents=True)

    skill_md = skills_dir / "SKILL.md"
    skill_md.write_text("""---
name: my-skill
description: A test skill for Codex
---

# My Skill

Instructions here.
""")

    return tmp_path


@pytest.fixture
def cursor_output_dir(tmp_path: Path) -> Path:
    """Create a valid Cursor output directory."""
    cursor_dir = tmp_path / ".cursor"
    skills_dir = cursor_dir / "skills" / "my-skill"
    skills_dir.mkdir(parents=True)

    skill_md = skills_dir / "SKILL.md"
    skill_md.write_text("""---
name: my-skill
description: A test skill for Cursor
---

# My Skill

Instructions here.
""")

    # Also create hooks.json
    hooks_file = cursor_dir / "hooks.json"
    hooks_file.write_text('{"version": 1, "hooks": {}}')

    return tmp_path


@pytest.fixture
def opencode_output_dir(tmp_path: Path) -> Path:
    """Create a valid OpenCode output directory."""
    opencode_dir = tmp_path / ".opencode"
    skills_dir = opencode_dir / "skills" / "my-skill"
    skills_dir.mkdir(parents=True)

    skill_md = skills_dir / "SKILL.md"
    skill_md.write_text("""---
name: my-skill
description: A test skill for OpenCode
---

# My Skill

Instructions here.
""")

    return tmp_path


class TestDoctorTargetHelp:
    """Test doctor command help shows target option."""

    def test_doctor_help_shows_target_option(self, runner: CliRunner) -> None:
        """Verify --target option is shown in doctor help."""
        result = runner.invoke(main, ["doctor", "--help"])
        assert result.exit_code == 0
        assert "--target" in result.output


class TestDoctorCodexTarget:
    """Test doctor command with Codex target."""

    def test_doctor_validates_codex_output(
        self, runner: CliRunner, codex_output_dir: Path
    ) -> None:
        """Doctor validates Codex output directory successfully."""
        result = runner.invoke(
            main, ["doctor", "--target", "codex", str(codex_output_dir)]
        )
        # Should pass because the output is valid
        assert result.exit_code == 0
        assert "codex" in result.output.lower()

    def test_doctor_codex_missing_skill_md(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Doctor fails when skill directory missing SKILL.md."""
        codex_dir = tmp_path / ".codex" / "skills" / "broken-skill"
        codex_dir.mkdir(parents=True)
        # No SKILL.md file - should fail

        result = runner.invoke(
            main, ["doctor", "--target", "codex", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "SKILL.md" in result.output or "fail" in result.output.lower()

    def test_doctor_codex_no_output_dir(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Doctor warns when no .codex directory exists."""
        result = runner.invoke(
            main, ["doctor", "--target", "codex", str(tmp_path)]
        )
        # Should warn but not fail
        assert "warn" in result.output.lower() or ".codex" in result.output


class TestDoctorCursorTarget:
    """Test doctor command with Cursor target."""

    def test_doctor_validates_cursor_output(
        self, runner: CliRunner, cursor_output_dir: Path
    ) -> None:
        """Doctor validates Cursor output directory successfully."""
        result = runner.invoke(
            main, ["doctor", "--target", "cursor", str(cursor_output_dir)]
        )
        assert result.exit_code == 0
        assert "cursor" in result.output.lower()

    def test_doctor_cursor_invalid_hooks(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Doctor fails on invalid hooks.json."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True)

        hooks_file = cursor_dir / "hooks.json"
        hooks_file.write_text('{"hooks": {}}')  # Missing version field

        result = runner.invoke(
            main, ["doctor", "--target", "cursor", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "version" in result.output.lower() or "fail" in result.output.lower()


class TestDoctorOpenCodeTarget:
    """Test doctor command with OpenCode target."""

    def test_doctor_validates_opencode_output(
        self, runner: CliRunner, opencode_output_dir: Path
    ) -> None:
        """Doctor validates OpenCode output directory successfully."""
        result = runner.invoke(
            main, ["doctor", "--target", "opencode", str(opencode_output_dir)]
        )
        assert result.exit_code == 0
        assert "opencode" in result.output.lower()

    def test_doctor_opencode_strict_name_validation(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Doctor fails on skill name with uppercase (OpenCode is strict)."""
        opencode_dir = tmp_path / ".opencode" / "skills" / "my-skill"
        opencode_dir.mkdir(parents=True)

        skill_md = opencode_dir / "SKILL.md"
        skill_md.write_text("""---
name: MySkill
description: A test skill with invalid name (uppercase)
---

# My Skill
""")

        result = runner.invoke(
            main, ["doctor", "--target", "opencode", str(tmp_path)]
        )
        # OpenCode requires lowercase kebab-case, should fail
        assert result.exit_code == 1
        assert "lowercase" in result.output.lower() or "fail" in result.output.lower()


class TestDoctorAllTargets:
    """Test doctor command with all targets."""

    def test_doctor_all_targets(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Doctor validates all targets when --target all is specified."""
        # Create minimal valid output for all targets
        for tool_dir in [".codex", ".cursor", ".opencode"]:
            skills_dir = tmp_path / tool_dir / "skills" / "my-skill"
            skills_dir.mkdir(parents=True)
            skill_md = skills_dir / "SKILL.md"
            skill_md.write_text("""---
name: my-skill
description: A test skill
---

# My Skill
""")

        # Add hooks.json for Cursor
        cursor_hooks = tmp_path / ".cursor" / "hooks.json"
        cursor_hooks.write_text('{"version": 1, "hooks": {}}')

        result = runner.invoke(
            main, ["doctor", "--target", "all", str(tmp_path)]
        )
        assert result.exit_code == 0
        # Should mention all three targets
        output_lower = result.output.lower()
        assert "codex" in output_lower
        assert "cursor" in output_lower
        assert "opencode" in output_lower


class TestDoctorTargetJsonOutput:
    """Test doctor target with JSON output."""

    def test_doctor_target_json_output(
        self, runner: CliRunner, codex_output_dir: Path
    ) -> None:
        """Doctor can output JSON for target validation."""
        result = runner.invoke(
            main, ["doctor", "--target", "codex", str(codex_output_dir), "--json"]
        )
        assert result.exit_code == 0
        # Should be valid JSON
        import json
        output = json.loads(result.output)
        assert "reports" in output or "results" in output


class TestDoctorTargetVerbose:
    """Test doctor target with verbose output."""

    def test_doctor_target_verbose(
        self, runner: CliRunner, codex_output_dir: Path
    ) -> None:
        """Doctor shows all checks including passed in verbose mode."""
        result = runner.invoke(
            main, ["doctor", "--target", "codex", str(codex_output_dir), "--verbose"]
        )
        assert result.exit_code == 0
        # Should show passed checks
        assert "pass" in result.output.lower()
