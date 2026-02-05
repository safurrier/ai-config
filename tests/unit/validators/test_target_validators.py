"""Tests for target-specific validators (Codex, Cursor, OpenCode).

These validators check that converted plugin output is valid for each target tool.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestCodexValidator:
    """Tests for Codex output validation."""

    def test_validate_skills_directory_exists(self, tmp_path: Path) -> None:
        """Test that skills directory validation passes when present."""
        from ai_config.validators.target.codex import CodexOutputValidator

        # Create valid Codex structure
        skills_dir = tmp_path / ".codex" / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill\n---\n# My Skill"
        )

        validator = CodexOutputValidator()
        results = validator.validate_skills(tmp_path)

        assert len(results) >= 1
        skill_result = next((r for r in results if "skill" in r.check_name.lower()), None)
        assert skill_result is not None
        assert skill_result.status == "pass"

    def test_validate_skills_missing_skill_md(self, tmp_path: Path) -> None:
        """Test that missing SKILL.md fails validation."""
        from ai_config.validators.target.codex import CodexOutputValidator

        # Create directory without SKILL.md
        skills_dir = tmp_path / ".codex" / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)

        validator = CodexOutputValidator()
        results = validator.validate_skills(tmp_path)

        # Should warn or fail about missing SKILL.md
        assert any(r.status in ("warn", "fail") for r in results)

    def test_validate_skills_invalid_name(self, tmp_path: Path) -> None:
        """Test that invalid skill names are caught."""
        from ai_config.validators.target.codex import CodexOutputValidator

        # Create skill with uppercase name (invalid)
        skills_dir = tmp_path / ".codex" / "skills" / "MySkill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: MySkill\ndescription: Invalid name\n---\n# Bad"
        )

        validator = CodexOutputValidator()
        results = validator.validate_skills(tmp_path)

        # Should warn about name
        assert any(r.status == "warn" for r in results)

    def test_validate_mcp_config_toml(self, tmp_path: Path) -> None:
        """Test that valid MCP TOML config passes."""
        from ai_config.validators.target.codex import CodexOutputValidator

        # Create .codex directory
        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir(parents=True)

        # Create valid config.toml
        config_content = """
[mcp_servers.test-server]
command = "npx"
args = ["-y", "test-server"]
"""
        (codex_dir / "mcp-config.toml").write_text(config_content)

        validator = CodexOutputValidator()
        results = validator.validate_mcp(tmp_path)

        mcp_result = next((r for r in results if "mcp" in r.check_name.lower()), None)
        assert mcp_result is not None
        assert mcp_result.status == "pass"

    def test_validate_mcp_invalid_toml(self, tmp_path: Path) -> None:
        """Test that invalid TOML fails validation."""
        from ai_config.validators.target.codex import CodexOutputValidator

        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir(parents=True)

        # Invalid TOML
        (codex_dir / "mcp-config.toml").write_text("this is not valid toml {{{")

        validator = CodexOutputValidator()
        results = validator.validate_mcp(tmp_path)

        assert any(r.status == "fail" for r in results)

    def test_validate_no_output(self, tmp_path: Path) -> None:
        """Test validation when no Codex output exists."""
        from ai_config.validators.target.codex import CodexOutputValidator

        validator = CodexOutputValidator()
        results = validator.validate_all(tmp_path)

        # Should indicate no output found
        assert any("not found" in r.message.lower() or "no " in r.message.lower() for r in results)


class TestCursorValidator:
    """Tests for Cursor output validation."""

    def test_validate_skills_directory(self, tmp_path: Path) -> None:
        """Test that skills directory validation passes."""
        from ai_config.validators.target.cursor import CursorOutputValidator

        skills_dir = tmp_path / ".cursor" / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill\n---\n# Skill"
        )

        validator = CursorOutputValidator()
        results = validator.validate_skills(tmp_path)

        assert any(r.status == "pass" for r in results)

    def test_validate_commands_directory(self, tmp_path: Path) -> None:
        """Test that commands directory validation passes."""
        from ai_config.validators.target.cursor import CursorOutputValidator

        commands_dir = tmp_path / ".cursor" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "my-command.md").write_text("# My Command\n\nDo something")

        validator = CursorOutputValidator()
        results = validator.validate_commands(tmp_path)

        assert any(r.status == "pass" for r in results)

    def test_validate_hooks_json_valid(self, tmp_path: Path) -> None:
        """Test that valid hooks.json passes validation."""
        from ai_config.validators.target.cursor import CursorOutputValidator

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True)

        hooks = {
            "version": 1,
            "hooks": {
                "beforeShellExecution": [
                    {"command": "/usr/bin/echo", "args": ["test"], "timeoutMs": 3000}
                ]
            },
        }
        (cursor_dir / "hooks.json").write_text(json.dumps(hooks))

        validator = CursorOutputValidator()
        results = validator.validate_hooks(tmp_path)

        hooks_result = next((r for r in results if "hooks" in r.check_name.lower()), None)
        assert hooks_result is not None
        assert hooks_result.status == "pass"

    def test_validate_hooks_json_missing_version(self, tmp_path: Path) -> None:
        """Test that hooks.json without version fails."""
        from ai_config.validators.target.cursor import CursorOutputValidator

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True)

        # Missing version field
        hooks = {"hooks": {"beforeShellExecution": []}}
        (cursor_dir / "hooks.json").write_text(json.dumps(hooks))

        validator = CursorOutputValidator()
        results = validator.validate_hooks(tmp_path)

        assert any(r.status in ("warn", "fail") for r in results)

    def test_validate_hooks_invalid_event(self, tmp_path: Path) -> None:
        """Test that invalid hook event names are warned."""
        from ai_config.validators.target.cursor import CursorOutputValidator

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True)

        hooks = {"version": 1, "hooks": {"invalidEvent": []}}
        (cursor_dir / "hooks.json").write_text(json.dumps(hooks))

        validator = CursorOutputValidator()
        results = validator.validate_hooks(tmp_path)

        assert any(r.status == "warn" for r in results)

    def test_validate_mcp_json_valid(self, tmp_path: Path) -> None:
        """Test that valid mcp.json passes."""
        from ai_config.validators.target.cursor import CursorOutputValidator

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True)

        mcp = {
            "mcpServers": {
                "test-server": {"command": "npx", "args": ["-y", "test-mcp"]}
            }
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(mcp))

        validator = CursorOutputValidator()
        results = validator.validate_mcp(tmp_path)

        assert any(r.status == "pass" for r in results)

    def test_validate_mcp_json_invalid_structure(self, tmp_path: Path) -> None:
        """Test that invalid mcp.json structure fails."""
        from ai_config.validators.target.cursor import CursorOutputValidator

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True)

        # Missing mcpServers key
        mcp = {"servers": {}}
        (cursor_dir / "mcp.json").write_text(json.dumps(mcp))

        validator = CursorOutputValidator()
        results = validator.validate_mcp(tmp_path)

        assert any(r.status in ("warn", "fail") for r in results)


class TestOpenCodeValidator:
    """Tests for OpenCode output validation."""

    def test_validate_skills_directory(self, tmp_path: Path) -> None:
        """Test that skills directory validation passes."""
        from ai_config.validators.target.opencode import OpenCodeOutputValidator

        skills_dir = tmp_path / ".opencode" / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill\n---\n# Skill"
        )

        validator = OpenCodeOutputValidator()
        results = validator.validate_skills(tmp_path)

        assert any(r.status == "pass" for r in results)

    def test_validate_skills_strict_name_validation(self, tmp_path: Path) -> None:
        """Test that OpenCode's strict name rules are enforced."""
        from ai_config.validators.target.opencode import OpenCodeOutputValidator

        # OpenCode requires: ^[a-z0-9]+(-[a-z0-9]+)*$
        skills_dir = tmp_path / ".opencode" / "skills" / "My-Skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text(
            "---\nname: My-Skill\ndescription: Invalid\n---\n# Bad"
        )

        validator = OpenCodeOutputValidator()
        results = validator.validate_skills(tmp_path)

        # Should fail due to uppercase
        assert any(r.status in ("warn", "fail") for r in results)

    def test_validate_opencode_json_valid(self, tmp_path: Path) -> None:
        """Test that valid opencode.json passes."""
        from ai_config.validators.target.opencode import OpenCodeOutputValidator

        config = {
            "mcp": {
                "test-server": {
                    "type": "local",
                    "command": ["npx", "-y", "test-mcp"],
                    "enabled": True,
                }
            }
        }
        (tmp_path / "opencode.json").write_text(json.dumps(config))

        validator = OpenCodeOutputValidator()
        results = validator.validate_mcp(tmp_path)

        assert any(r.status == "pass" for r in results)

    def test_validate_opencode_json_command_as_string(self, tmp_path: Path) -> None:
        """Test that command as string (not array) warns."""
        from ai_config.validators.target.opencode import OpenCodeOutputValidator

        # OpenCode requires command as array
        config = {
            "mcp": {
                "test-server": {
                    "type": "local",
                    "command": "npx -y test-mcp",  # Should be array
                    "enabled": True,
                }
            }
        }
        (tmp_path / "opencode.json").write_text(json.dumps(config))

        validator = OpenCodeOutputValidator()
        results = validator.validate_mcp(tmp_path)

        assert any(r.status == "warn" for r in results)

    def test_validate_lsp_config(self, tmp_path: Path) -> None:
        """Test that LSP config validation works."""
        from ai_config.validators.target.opencode import OpenCodeOutputValidator

        config = {
            "lsp": {
                "python": {
                    "command": ["pylsp"],
                    "extensions": [".py"],
                }
            }
        }
        (tmp_path / "opencode.lsp.json").write_text(json.dumps(config))

        validator = OpenCodeOutputValidator()
        results = validator.validate_lsp(tmp_path)

        assert any(r.status == "pass" for r in results)


class TestValidatorFactory:
    """Tests for the validator factory function."""

    def test_get_validator_codex(self) -> None:
        """Test getting Codex validator."""
        from ai_config.validators.target import get_output_validator

        validator = get_output_validator("codex")
        assert validator is not None
        assert "codex" in validator.__class__.__name__.lower()

    def test_get_validator_cursor(self) -> None:
        """Test getting Cursor validator."""
        from ai_config.validators.target import get_output_validator

        validator = get_output_validator("cursor")
        assert validator is not None
        assert "cursor" in validator.__class__.__name__.lower()

    def test_get_validator_opencode(self) -> None:
        """Test getting OpenCode validator."""
        from ai_config.validators.target import get_output_validator

        validator = get_output_validator("opencode")
        assert validator is not None
        assert "opencode" in validator.__class__.__name__.lower()

    def test_get_validator_unknown_raises(self) -> None:
        """Test that unknown target raises ValueError."""
        from ai_config.validators.target import get_output_validator

        with pytest.raises(ValueError, match="Unknown target"):
            get_output_validator("unknown-tool")


class TestIntegrationWithConversion:
    """Integration tests: convert then validate."""

    def test_convert_and_validate_codex(self, tmp_path: Path) -> None:
        """Test that converted Codex output validates."""
        from ai_config.converters import TargetTool, convert_plugin
        from ai_config.validators.target.codex import CodexOutputValidator

        fixtures = Path(__file__).parent.parent.parent / "fixtures" / "sample-plugins"
        plugin_path = fixtures / "complete-plugin"

        if not plugin_path.exists():
            pytest.skip("Test fixture not available")

        # Convert
        convert_plugin(
            plugin_path=plugin_path,
            targets=[TargetTool.CODEX],
            output_dir=tmp_path,
            dry_run=False,
        )

        # Validate
        validator = CodexOutputValidator()
        results = validator.validate_all(tmp_path)

        # Should have mostly passes
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 0, f"Validation failures: {failures}"

    def test_convert_and_validate_cursor(self, tmp_path: Path) -> None:
        """Test that converted Cursor output validates."""
        from ai_config.converters import TargetTool, convert_plugin
        from ai_config.validators.target.cursor import CursorOutputValidator

        fixtures = Path(__file__).parent.parent.parent / "fixtures" / "sample-plugins"
        plugin_path = fixtures / "complete-plugin"

        if not plugin_path.exists():
            pytest.skip("Test fixture not available")

        # Convert
        convert_plugin(
            plugin_path=plugin_path,
            targets=[TargetTool.CURSOR],
            output_dir=tmp_path,
            dry_run=False,
        )

        # Validate
        validator = CursorOutputValidator()
        results = validator.validate_all(tmp_path)

        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 0, f"Validation failures: {failures}"

    def test_convert_and_validate_opencode(self, tmp_path: Path) -> None:
        """Test that converted OpenCode output validates."""
        from ai_config.converters import TargetTool, convert_plugin
        from ai_config.validators.target.opencode import OpenCodeOutputValidator

        fixtures = Path(__file__).parent.parent.parent / "fixtures" / "sample-plugins"
        plugin_path = fixtures / "complete-plugin"

        if not plugin_path.exists():
            pytest.skip("Test fixture not available")

        # Convert
        convert_plugin(
            plugin_path=plugin_path,
            targets=[TargetTool.OPENCODE],
            output_dir=tmp_path,
            dry_run=False,
        )

        # Validate
        validator = OpenCodeOutputValidator()
        results = validator.validate_all(tmp_path)

        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 0, f"Validation failures: {failures}"
