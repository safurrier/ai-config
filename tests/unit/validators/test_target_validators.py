"""Tests for target-specific validators (Codex, Cursor, OpenCode).

These validators check that converted plugin output is valid for each target tool.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestCodexValidator:
    """Tests for Codex package and ownership validation."""

    def _emit(self, tmp_path: Path) -> Path:
        from ai_config.converters import TargetTool, convert_plugin

        plugin = Path(__file__).parent.parent.parent / "fixtures/sample-plugins/complete-plugin"
        convert_plugin(plugin, [TargetTool.CODEX], output_dir=tmp_path)
        return tmp_path

    def test_generated_package_passes(self, tmp_path: Path) -> None:
        from ai_config.validators.target.codex import CodexOutputValidator

        results = CodexOutputValidator().validate_all(self._emit(tmp_path))
        assert not [result for result in results if result.status == "fail"]
        assert any("package" in result.check_name and result.status == "pass" for result in results)
        assert any(
            "marketplace" in result.check_name and result.status == "pass" for result in results
        )

    def test_manifest_name_mismatch_fails(self, tmp_path: Path) -> None:
        from ai_config.validators.target.codex import CodexOutputValidator

        self._emit(tmp_path)
        manifest = next(
            tmp_path.glob(".ai-config/codex/marketplaces/*/plugins/*/.codex-plugin/plugin.json")
        )
        payload = json.loads(manifest.read_text())
        payload["name"] = "wrong"
        manifest.write_text(json.dumps(payload))
        results = CodexOutputValidator().validate_all(tmp_path)
        assert any(result.status == "fail" and "name" in result.check_name for result in results)

    @pytest.mark.parametrize("version", ["1.0", "01.0.0", "latest"])
    def test_manifest_invalid_semver_fails(self, tmp_path: Path, version: str) -> None:
        from ai_config.validators.target.codex import CodexOutputValidator

        self._emit(tmp_path)
        manifest = next(
            tmp_path.glob(".ai-config/codex/marketplaces/*/plugins/*/.codex-plugin/plugin.json")
        )
        payload = json.loads(manifest.read_text())
        payload["version"] = version
        manifest.write_text(json.dumps(payload))

        results = CodexOutputValidator().validate_all(tmp_path)

        assert any(
            result.status == "fail" and result.check_name.endswith("_version") for result in results
        )

    def test_marketplace_normalized_identity_mutation_fails(self, tmp_path: Path) -> None:
        from ai_config.validators.target.codex import CodexOutputValidator

        self._emit(tmp_path)
        marketplace = next(
            tmp_path.glob(".ai-config/codex/marketplaces/*/.agents/plugins/marketplace.json")
        )
        payload = json.loads(marketplace.read_text())
        payload["plugins"][0]["source"]["path"] = "./plugins/other"
        marketplace.write_text(json.dumps(payload))

        results = CodexOutputValidator().validate_all(tmp_path)

        assert any(
            result.status == "fail" and result.check_name.endswith("_identity")
            for result in results
        )

    def test_marketplace_reference_escape_fails(self, tmp_path: Path) -> None:
        from ai_config.validators.target.codex import CodexOutputValidator

        self._emit(tmp_path)
        marketplace = next(
            tmp_path.glob(".ai-config/codex/marketplaces/*/.agents/plugins/marketplace.json")
        )
        payload = json.loads(marketplace.read_text())
        payload["plugins"][0]["source"]["path"] = "../../../../outside"
        marketplace.write_text(json.dumps(payload))
        results = CodexOutputValidator().validate_all(tmp_path)
        assert any(result.status == "fail" and "escape" in result.check_name for result in results)

    def test_package_manifest_reference_escape_fails(self, tmp_path: Path) -> None:
        from ai_config.validators.target.codex import CodexOutputValidator

        self._emit(tmp_path)
        manifest = next(
            tmp_path.glob(".ai-config/codex/marketplaces/*/plugins/*/.codex-plugin/plugin.json")
        )
        outside = tmp_path / "outside-hooks.json"
        outside.write_text('{"hooks": {}}')
        payload = json.loads(manifest.read_text())
        payload["hooks"] = "../../../../../../outside-hooks.json"
        manifest.write_text(json.dumps(payload))

        results = CodexOutputValidator().validate_all(tmp_path)

        assert any(
            result.status == "fail" and "package_hooks_reference" in result.check_name
            for result in results
        )

    def test_invalid_package_hooks_fail(self, tmp_path: Path) -> None:
        from ai_config.validators.target.codex import CodexOutputValidator

        self._emit(tmp_path)
        hooks = next(tmp_path.glob(".ai-config/codex/marketplaces/*/plugins/*/hooks/hooks.json"))
        hooks.write_text('{"hooks":{"Unknown":[]}}')
        results = CodexOutputValidator().validate_all(tmp_path)
        assert any(result.status == "fail" and "hook" in result.check_name for result in results)

    def test_legacy_loose_output_warns_without_removal(self, tmp_path: Path) -> None:
        from ai_config.validators.target.codex import CodexOutputValidator

        legacy = tmp_path / ".codex/skills/user-skill/SKILL.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("user content")
        results = CodexOutputValidator().validate_all(self._emit(tmp_path))
        assert legacy.is_file()
        assert any(result.status == "warn" and "legacy" in result.check_name for result in results)

    def test_no_package_output_warns(self, tmp_path: Path) -> None:
        from ai_config.validators.target.codex import CodexOutputValidator

        results = CodexOutputValidator().validate_all(tmp_path)
        assert any(
            result.status == "warn" and "No generated" in result.message for result in results
        )


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

        mcp = {"mcpServers": {"test-server": {"command": "npx", "args": ["-y", "test-mcp"]}}}
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


class TestPiValidator:
    """Tests for Pi output validation."""

    def test_validate_skills_directory_exists(self, tmp_path: Path) -> None:
        """Valid skill passes validation."""
        from ai_config.validators.target.pi import PiOutputValidator

        skill_dir = tmp_path / ".pi" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill\n---\n\n# My Skill\n"
        )

        validator = PiOutputValidator()
        results = validator.validate_skills(tmp_path)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 0

    def test_validate_skills_missing_description(self, tmp_path: Path) -> None:
        """Skill without description fails (Pi won't load it)."""
        from ai_config.validators.target.pi import PiOutputValidator

        skill_dir = tmp_path / ".pi" / "skills" / "no-desc"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: no-desc\n---\n\nBody\n")

        validator = PiOutputValidator()
        results = validator.validate_skills(tmp_path)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "description" in failures[0].message.lower()

    def test_validate_skills_missing_skill_md(self, tmp_path: Path) -> None:
        """Skill dir without SKILL.md fails."""
        from ai_config.validators.target.pi import PiOutputValidator

        skill_dir = tmp_path / ".pi" / "skills" / "empty"
        skill_dir.mkdir(parents=True)

        validator = PiOutputValidator()
        results = validator.validate_skills(tmp_path)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "SKILL.md" in failures[0].message

    def test_validate_prompts(self, tmp_path: Path) -> None:
        """Valid prompt templates pass validation."""
        from ai_config.validators.target.pi import PiOutputValidator

        prompts_dir = tmp_path / ".pi" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "review.md").write_text("---\ndescription: Review code\n---\nReview this.")

        validator = PiOutputValidator()
        results = validator.validate_prompts(tmp_path)
        passes = [r for r in results if r.status == "pass"]
        assert len(passes) == 1

    def test_validate_all_no_pi_dir(self, tmp_path: Path) -> None:
        """No .pi directory produces a warning."""
        from ai_config.validators.target.pi import PiOutputValidator

        validator = PiOutputValidator()
        results = validator.validate_all(tmp_path)
        warnings = [r for r in results if r.status == "warn"]
        assert len(warnings) == 1
        assert ".pi" in warnings[0].message


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

    def test_get_validator_pi(self) -> None:
        """Test getting Pi validator."""
        from ai_config.validators.target import get_output_validator

        validator = get_output_validator("pi")
        assert validator is not None
        assert "pi" in validator.__class__.__name__.lower()

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

    def test_convert_and_validate_pi(self, tmp_path: Path) -> None:
        """Test that converted Pi output validates."""
        from ai_config.converters import TargetTool, convert_plugin
        from ai_config.validators.target.pi import PiOutputValidator

        fixtures = Path(__file__).parent.parent.parent / "fixtures" / "sample-plugins"
        plugin_path = fixtures / "complete-plugin"

        if not plugin_path.exists():
            pytest.skip("Test fixture not available")

        convert_plugin(
            plugin_path=plugin_path,
            targets=[TargetTool.PI],
            output_dir=tmp_path,
            dry_run=False,
        )

        validator = PiOutputValidator()
        results = validator.validate_all(tmp_path)

        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 0, f"Validation failures: {failures}"
