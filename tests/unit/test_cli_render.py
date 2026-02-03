"""Unit tests for ai_config.cli_render module."""

from ai_config.cli_render import (
    EntityResult,
    count_by_status,
    extract_claude_version,
    extract_entity_from_result,
    group_results_by_entity,
)
from ai_config.validators.base import ValidationReport, ValidationResult


class TestExtractEntityFromResult:
    """Tests for extract_entity_from_result function."""

    def test_claude_cli_available_pass(self) -> None:
        """Extract target entity from successful Claude CLI check."""
        result = ValidationResult(
            check_name="claude_cli_available",
            status="pass",
            message="Claude CLI available (claude 2.1.29)",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "target"
        assert entity_name == "claude 2.1.29"

    def test_claude_cli_not_found(self) -> None:
        """Extract target entity from failed Claude CLI check."""
        result = ValidationResult(
            check_name="claude_cli_available",
            status="fail",
            message="Claude CLI not found",
        )
        entity = extract_entity_from_result(result)
        # No version in message, should still extract something
        assert entity is None or entity[0] == "target"

    def test_plugin_installed_pass(self) -> None:
        """Extract plugin entity from installed check."""
        result = ValidationResult(
            check_name="plugin_installed",
            status="pass",
            message="Plugin 'alex-ai@dots-plugins' is installed",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "plugin"
        assert entity_name == "alex-ai@dots-plugins"

    def test_plugin_not_installed(self) -> None:
        """Extract plugin entity from not installed check."""
        result = ValidationResult(
            check_name="plugin_installed",
            status="fail",
            message="Plugin 'my-plugin@marketplace' is not installed",
            fix_hint="Run: ai-config sync",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "plugin"
        assert entity_name == "my-plugin@marketplace"

    def test_plugin_state_matches(self) -> None:
        """Extract plugin entity from state check."""
        result = ValidationResult(
            check_name="plugin_enabled_state",
            status="pass",
            message="Plugin 'test-plugin' state matches config",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "plugin"
        assert entity_name == "test-plugin"

    def test_marketplace_path_exists(self) -> None:
        """Extract marketplace entity from path check."""
        result = ValidationResult(
            check_name="marketplace_path_exists",
            status="pass",
            message="Marketplace 'dots-plugins' path exists: /path/to/plugins",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "marketplace"
        assert entity_name == "dots-plugins"

    def test_marketplace_path_missing(self) -> None:
        """Extract marketplace entity from missing path check."""
        result = ValidationResult(
            check_name="marketplace_path_exists",
            status="fail",
            message="Marketplace 'test-mp' path does not exist: /missing/path",
            fix_hint="Create the directory: mkdir -p /missing/path",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "marketplace"
        assert entity_name == "test-mp"

    def test_marketplace_manifest_valid(self) -> None:
        """Extract marketplace entity from manifest check."""
        result = ValidationResult(
            check_name="marketplace_manifest_valid",
            status="pass",
            message="Marketplace 'my-marketplace' manifest is valid",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "marketplace"
        assert entity_name == "my-marketplace"

    def test_skill_name_valid(self) -> None:
        """Extract skill entity from name validation."""
        result = ValidationResult(
            check_name="name_valid",
            status="pass",
            message="Skill name 'python-core' is valid",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "skill"
        assert entity_name == "python-core"

    def test_skill_md_not_found(self) -> None:
        """Extract skill entity from SKILL.md not found."""
        result = ValidationResult(
            check_name="skill_md_exists",
            status="fail",
            message="SKILL.md not found in /path/to/skills/my-skill",
            fix_hint="Create /path/to/skills/my-skill/SKILL.md",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "skill"
        assert entity_name == "my-skill"

    def test_hooks_valid(self) -> None:
        """Extract hook entity from hooks validation."""
        result = ValidationResult(
            check_name="hooks_valid",
            status="pass",
            message="Plugin 'alex-ai@dots-plugins' hooks are valid",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "hook"
        assert entity_name == "alex-ai@dots-plugins"

    def test_mcp_valid(self) -> None:
        """Extract MCP entity from validation."""
        result = ValidationResult(
            check_name="mcp_valid",
            status="pass",
            message="Plugin 'claude-code-tutorial' MCP config is valid",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "mcp"
        assert entity_name == "claude-code-tutorial"

    def test_mcp_server_warning(self) -> None:
        """Extract MCP entity from server warning."""
        result = ValidationResult(
            check_name="mcp_command_exists",
            status="warn",
            message="MCP server 'context7' command not found: npx",
            details="Plugin: claude-code-tutorial",
        )
        entity = extract_entity_from_result(result)
        assert entity is not None
        entity_type, entity_name = entity
        assert entity_type == "mcp"
        assert entity_name == "context7"


class TestGroupResultsByEntity:
    """Tests for group_results_by_entity function."""

    def test_empty_results(self) -> None:
        """Empty results should return empty dict."""
        grouped = group_results_by_entity([])
        assert grouped == {}

    def test_single_plugin_result(self) -> None:
        """Single plugin result should be grouped correctly."""
        results = [
            ValidationResult(
                check_name="plugin_installed",
                status="pass",
                message="Plugin 'test-plugin' is installed",
            )
        ]
        grouped = group_results_by_entity(results)
        assert "plugin" in grouped
        assert "test-plugin" in grouped["plugin"]
        entity = grouped["plugin"]["test-plugin"]
        assert len(entity.passed) == 1
        assert len(entity.failures) == 0
        assert len(entity.warnings) == 0

    def test_multiple_results_same_entity(self) -> None:
        """Multiple results for same entity should be grouped together."""
        results = [
            ValidationResult(
                check_name="plugin_installed",
                status="pass",
                message="Plugin 'my-plugin' is installed",
            ),
            ValidationResult(
                check_name="plugin_enabled_state",
                status="pass",
                message="Plugin 'my-plugin' state matches config",
            ),
            ValidationResult(
                check_name="plugin_manifest_valid",
                status="warn",
                message="Plugin 'my-plugin' manifest has warnings",
            ),
        ]
        grouped = group_results_by_entity(results)
        assert "plugin" in grouped
        entity = grouped["plugin"]["my-plugin"]
        assert len(entity.passed) == 2
        assert len(entity.warnings) == 1
        assert len(entity.failures) == 0

    def test_mixed_entity_types(self) -> None:
        """Results from different entity types should be separated."""
        results = [
            ValidationResult(
                check_name="plugin_installed",
                status="pass",
                message="Plugin 'plugin-a' is installed",
            ),
            ValidationResult(
                check_name="marketplace_path_exists",
                status="pass",
                message="Marketplace 'mp-a' path exists: /path",
            ),
            ValidationResult(
                check_name="name_valid",
                status="pass",
                message="Skill name 'skill-a' is valid",
            ),
        ]
        grouped = group_results_by_entity(results)
        assert "plugin" in grouped
        assert "marketplace" in grouped
        assert "skill" in grouped
        assert "plugin-a" in grouped["plugin"]
        assert "mp-a" in grouped["marketplace"]
        assert "skill-a" in grouped["skill"]


class TestEntityResult:
    """Tests for EntityResult dataclass."""

    def test_has_issues_with_failures(self) -> None:
        """has_issues should be True when there are failures."""
        entity = EntityResult(entity_type="plugin", entity_name="test")
        entity.failures.append(
            ValidationResult(
                check_name="test",
                status="fail",
                message="Test failure",
            )
        )
        assert entity.has_issues is True

    def test_has_issues_with_warnings(self) -> None:
        """has_issues should be True when there are warnings."""
        entity = EntityResult(entity_type="plugin", entity_name="test")
        entity.warnings.append(
            ValidationResult(
                check_name="test",
                status="warn",
                message="Test warning",
            )
        )
        assert entity.has_issues is True

    def test_has_issues_only_passed(self) -> None:
        """has_issues should be False when only passed results."""
        entity = EntityResult(entity_type="plugin", entity_name="test")
        entity.passed.append(
            ValidationResult(
                check_name="test",
                status="pass",
                message="Test passed",
            )
        )
        assert entity.has_issues is False

    def test_status_symbol_failure(self) -> None:
        """status_symbol should be red X for failures."""
        entity = EntityResult(entity_type="plugin", entity_name="test")
        entity.failures.append(
            ValidationResult(
                check_name="test",
                status="fail",
                message="Test failure",
            )
        )
        assert "red" in entity.status_symbol
        assert "✗" in entity.status_symbol

    def test_status_symbol_warning(self) -> None:
        """status_symbol should be yellow warning for warnings."""
        entity = EntityResult(entity_type="plugin", entity_name="test")
        entity.warnings.append(
            ValidationResult(
                check_name="test",
                status="warn",
                message="Test warning",
            )
        )
        assert "yellow" in entity.status_symbol
        assert "⚠" in entity.status_symbol

    def test_status_symbol_pass(self) -> None:
        """status_symbol should be green check for all passed."""
        entity = EntityResult(entity_type="plugin", entity_name="test")
        entity.passed.append(
            ValidationResult(
                check_name="test",
                status="pass",
                message="Test passed",
            )
        )
        assert "green" in entity.status_symbol
        assert "✓" in entity.status_symbol


class TestExtractClaudeVersion:
    """Tests for extract_claude_version function."""

    def test_extract_version_from_reports(self) -> None:
        """Should extract version from target report."""
        reports = {
            "target": ValidationReport(
                target="claude:target",
                results=[
                    ValidationResult(
                        check_name="claude_cli_available",
                        status="pass",
                        message="Claude CLI available (claude 2.1.29)",
                    )
                ],
            )
        }
        version = extract_claude_version(reports)
        assert version == "claude 2.1.29"

    def test_extract_version_no_target(self) -> None:
        """Should return None when no target report."""
        reports = {
            "plugin": ValidationReport(
                target="claude:plugin",
                results=[],
            )
        }
        version = extract_claude_version(reports)
        assert version is None

    def test_extract_version_failed_check(self) -> None:
        """Should return None when CLI check failed."""
        reports = {
            "target": ValidationReport(
                target="claude:target",
                results=[
                    ValidationResult(
                        check_name="claude_cli_available",
                        status="fail",
                        message="Claude CLI not found",
                    )
                ],
            )
        }
        version = extract_claude_version(reports)
        assert version is None


class TestCountByStatus:
    """Tests for count_by_status function."""

    def test_empty_results(self) -> None:
        """Empty results should return all zeros."""
        pass_count, warn_count, fail_count = count_by_status([])
        assert pass_count == 0
        assert warn_count == 0
        assert fail_count == 0

    def test_mixed_statuses(self) -> None:
        """Should count each status correctly."""
        results = [
            ValidationResult(check_name="a", status="pass", message="a"),
            ValidationResult(check_name="b", status="pass", message="b"),
            ValidationResult(check_name="c", status="warn", message="c"),
            ValidationResult(check_name="d", status="fail", message="d"),
            ValidationResult(check_name="e", status="fail", message="e"),
            ValidationResult(check_name="f", status="fail", message="f"),
        ]
        pass_count, warn_count, fail_count = count_by_status(results)
        assert pass_count == 2
        assert warn_count == 1
        assert fail_count == 3
