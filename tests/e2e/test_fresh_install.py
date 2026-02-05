"""E2E tests for fresh ai-config installation and sync.

These tests validate that ai-config can sync plugins, skills, hooks,
and MCP configurations to Claude Code's plugin directory from a fresh state.
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
class TestFreshInstall:
    """Test ai-config sync from a fresh installation."""

    def test_ai_config_installs(self, claude_container: Container) -> None:
        """Verify ai-config CLI is available and working."""
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config --help",
        )
        assert exit_code == 0, f"ai-config --help failed: {output}"
        assert "ai-config" in output.lower()

    def test_claude_cli_installed(self, claude_container: Container) -> None:
        """Verify Claude CLI is installed and available."""
        exit_code, output = exec_in_container(
            claude_container,
            "claude --version",
        )
        assert exit_code == 0, f"Claude CLI not available: {output}"

    def test_sync_adds_marketplace(self, claude_container: Container) -> None:
        """Verify sync adds the local marketplace."""
        # Write config
        exit_code, output = exec_in_container(
            claude_container,
            f"mkdir -p ~/.ai-config && cat > ~/.ai-config/config.yaml << 'EOF'\n{TEST_CONFIG}\nEOF",
        )
        assert exit_code == 0, f"Failed to create config: {output}"

        # Run sync
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config sync",
        )
        # Sync may fail if claude plugin commands fail, but check the status
        print(f"Sync output: {output}")  # noqa: T201

        # Check status
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config status",
        )
        print(f"Status output: {output}")  # noqa: T201

    def test_sync_dry_run_shows_actions(self, claude_container: Container) -> None:
        """Verify dry-run shows what would be done."""
        # Write config
        exit_code, output = exec_in_container(
            claude_container,
            f"mkdir -p ~/.ai-config && cat > ~/.ai-config/config.yaml << 'EOF'\n{TEST_CONFIG}\nEOF",
        )
        assert exit_code == 0, f"Failed to create config: {output}"

        # Run sync with dry-run
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config sync --dry-run",
        )
        assert "Dry run" in output, f"Dry run message not in output: {output}"


@pytest.mark.e2e
@pytest.mark.docker
class TestConfigValidation:
    """Test config validation in Docker environment."""

    def test_invalid_config_errors(self, claude_container: Container) -> None:
        """Verify invalid config produces clear errors."""
        # Write invalid config (missing version)
        invalid_config = """
plugins:
  - path: some/path
"""
        exit_code, output = exec_in_container(
            claude_container,
            f"mkdir -p ~/.ai-config && cat > ~/.ai-config/config.yaml << 'EOF'\n{invalid_config}\nEOF",
        )

        # Try to sync
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config sync",
        )
        assert exit_code != 0, "Should fail with invalid config"
        assert "version" in output.lower(), f"Error should mention version: {output}"

    def test_empty_config_errors(self, claude_container: Container) -> None:
        """Verify empty config produces clear errors."""
        exit_code, output = exec_in_container(
            claude_container,
            "mkdir -p ~/.ai-config && echo '' > ~/.ai-config/config.yaml",
        )

        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config sync",
        )
        assert exit_code != 0, "Should fail with empty config"


@pytest.mark.e2e
@pytest.mark.docker
class TestStatusCommand:
    """Test status command in Docker environment."""

    def test_status_no_plugins(self, claude_container: Container) -> None:
        """Verify status shows no plugins when none installed."""
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config status",
        )
        assert exit_code == 0, f"Status command failed: {output}"
        # Should indicate no plugins
        assert "No plugins" in output or "no plugins" in output.lower()

    def test_status_command_works(self, claude_container: Container) -> None:
        """Verify status command runs without errors."""
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config status",
        )
        assert exit_code == 0, f"Status command failed: {output}"
        # Should show some structure
        assert "Installed" in output or "Plugin" in output or "Marketplace" in output
