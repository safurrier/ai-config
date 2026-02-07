"""E2E tests for fresh ai-config installation and sync.

These tests validate that ai-config can sync plugins, skills, hooks,
and MCP configurations to Claude Code's plugin directory from a fresh state.

Note: These tests use all_tools_container which includes Claude Code and
all other supported AI tools. This is a superset of claude-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.e2e.conftest import exec_in_container

if TYPE_CHECKING:
    from docker.models.containers import Container


# Test config that uses a local marketplace with a test plugin
TEST_CONFIG = """
version: 1
targets:
  - type: claude
    config:
      marketplaces:
        test-marketplace:
          source: local
          path: tests/fixtures/test-marketplace
      plugins:
        - id: test-plugin@test-marketplace
          scope: user
          enabled: true
"""


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.slow
class TestFreshInstall:
    """Test ai-config sync from a fresh installation."""

    def test_ai_config_installs(self, all_tools_container: Container) -> None:
        """Verify ai-config CLI is available and working."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config --help",
        )
        assert exit_code == 0, f"ai-config --help failed: {output}"
        assert "ai-config" in output.lower()

    def test_claude_cli_installed(self, all_tools_container: Container) -> None:
        """Verify Claude CLI is installed and available."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "claude --version",
        )
        assert exit_code == 0, f"Claude CLI not available: {output}"

    def test_sync_adds_marketplace(self, all_tools_container: Container) -> None:
        """Verify sync adds the local marketplace and installs the plugin."""
        # Write config
        exit_code, output = exec_in_container(
            all_tools_container,
            f"mkdir -p ~/.ai-config && cat > ~/.ai-config/config.yaml << 'EOF'\n{TEST_CONFIG}\nEOF",
        )
        assert exit_code == 0, f"Failed to create config: {output}"

        # Run sync
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config sync",
        )
        assert exit_code == 0, f"ai-config sync failed (exit {exit_code}): {output}"
        assert "Failed" not in output, f"Sync reported failure: {output}"
        assert "Error" not in output, f"Sync reported error: {output}"

        # Verify marketplace is registered
        exit_code, output = exec_in_container(
            all_tools_container,
            "claude plugin marketplace list --json",
        )
        assert exit_code == 0, f"claude plugin marketplace list failed: {output}"
        assert "test-marketplace" in output, (
            f"test-marketplace not in marketplace list: {output}"
        )

        # Verify plugin is installed
        exit_code, output = exec_in_container(
            all_tools_container,
            "claude plugin list --json",
        )
        assert exit_code == 0, f"claude plugin list failed: {output}"
        assert "test-plugin" in output, f"test-plugin not in plugin list: {output}"

        # Check status for good measure
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config status",
        )
        assert exit_code == 0, f"ai-config status failed: {output}"

    def test_sync_dry_run_shows_actions(self, all_tools_container: Container) -> None:
        """Verify dry-run shows what would be done."""
        # Write config
        exit_code, output = exec_in_container(
            all_tools_container,
            f"mkdir -p ~/.ai-config && cat > ~/.ai-config/config.yaml << 'EOF'\n{TEST_CONFIG}\nEOF",
        )
        assert exit_code == 0, f"Failed to create config: {output}"

        # Run sync with dry-run
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config sync --dry-run",
        )
        assert "Dry run" in output, f"Dry run message not in output: {output}"


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.slow
class TestConfigValidation:
    """Test config validation in Docker environment."""

    def test_invalid_config_errors(self, all_tools_container: Container) -> None:
        """Verify invalid config produces clear errors."""
        # Write invalid config (missing version)
        invalid_config = """
plugins:
  - path: some/path
"""
        exit_code, output = exec_in_container(
            all_tools_container,
            f"mkdir -p ~/.ai-config && cat > ~/.ai-config/config.yaml << 'EOF'\n{invalid_config}\nEOF",
        )

        # Try to sync
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config sync",
        )
        assert exit_code != 0, "Should fail with invalid config"
        assert "version" in output.lower(), f"Error should mention version: {output}"

    def test_empty_config_errors(self, all_tools_container: Container) -> None:
        """Verify empty config produces clear errors."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "mkdir -p ~/.ai-config && echo '' > ~/.ai-config/config.yaml",
        )

        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config sync",
        )
        assert exit_code != 0, "Should fail with empty config"


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.slow
class TestStatusCommand:
    """Test status command in Docker environment."""

    def test_status_no_plugins(self, all_tools_container: Container) -> None:
        """Verify status shows no plugins when none installed."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config status",
        )
        assert exit_code == 0, f"Status command failed: {output}"
        # Should indicate no plugins
        assert "No plugins" in output or "no plugins" in output.lower()

    def test_status_command_works(self, all_tools_container: Container) -> None:
        """Verify status command runs without errors."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config status",
        )
        assert exit_code == 0, f"Status command failed: {output}"
        # Should show some structure
        assert "Installed" in output or "Plugin" in output or "Marketplace" in output
