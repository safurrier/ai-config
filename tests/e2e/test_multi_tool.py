"""E2E tests for multiple AI coding tools.

These tests validate that ai-config works with all supported AI coding tools:
- Claude Code (@anthropic-ai/claude-code)
- OpenAI Codex (@openai/codex)
- OpenCode (opencode.ai)
- Cursor CLI (cursor.com)

Note: Some tools may not be publicly available yet. Tests will report
installation status and skip gracefully if tools aren't installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from tests.e2e.conftest import check_tool_installed, exec_in_container

if TYPE_CHECKING:
    from docker.models.containers import Container


@dataclass
class ToolConfig:
    """Configuration for an AI coding tool."""

    name: str
    version_cmd: str
    config_dir: str  # Where the tool stores plugins/config
    description: str


# Tool configurations
TOOLS = {
    "claude": ToolConfig(
        name="Claude Code",
        version_cmd="claude --version",
        config_dir="~/.claude",
        description="Anthropic's Claude Code CLI",
    ),
    "codex": ToolConfig(
        name="OpenAI Codex",
        version_cmd="codex --version",
        config_dir="~/.codex",
        description="OpenAI's Codex CLI",
    ),
    "opencode": ToolConfig(
        name="OpenCode",
        version_cmd="opencode --version",
        config_dir="~/.opencode",
        description="OpenCode AI coding assistant",
    ),
    "cursor": ToolConfig(
        name="Cursor",
        version_cmd="cursor-agent --version || cursor --version",
        config_dir="~/.cursor",
        description="Cursor AI-powered editor CLI",
    ),
}


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.slow
class TestAllToolsInstallation:
    """Test that all AI coding tools are installed correctly.

    These tests use the all-tools Docker image which attempts to install
    all supported AI coding tools. Some may fail if installers aren't
    publicly available.
    """

    def test_tool_installation_report(self, all_tools_container: Container) -> None:
        """Generate a report of which tools are installed."""
        print("\n" + "=" * 60)  # noqa: T201
        print("AI Coding Tools Installation Report")  # noqa: T201
        print("=" * 60)  # noqa: T201

        results = {}
        for tool_id, tool_config in TOOLS.items():
            installed, version_or_error = check_tool_installed(
                all_tools_container,
                tool_config.name,
                tool_config.version_cmd,
            )
            results[tool_id] = (installed, version_or_error)

            status = "✓ INSTALLED" if installed else "✗ NOT INSTALLED"
            print(f"\n{tool_config.name} ({tool_id}):")  # noqa: T201
            print(f"  Status: {status}")  # noqa: T201
            print(f"  {version_or_error}")  # noqa: T201
            print(f"  Config dir: {tool_config.config_dir}")  # noqa: T201

        print("\n" + "=" * 60)  # noqa: T201

        # At minimum, Claude should be installed
        assert results["claude"][0], "Claude Code must be installed"

    def test_claude_installed(self, all_tools_container: Container) -> None:
        """Verify Claude Code is installed in the all-tools image."""
        installed, output = check_tool_installed(
            all_tools_container,
            "Claude Code",
            "claude --version",
        )
        assert installed, f"Claude Code not installed: {output}"
        print(f"Claude Code version: {output}")  # noqa: T201

    def test_codex_installation_status(self, all_tools_container: Container) -> None:
        """Check Codex installation status (may not be available yet)."""
        installed, output = check_tool_installed(
            all_tools_container,
            "OpenAI Codex",
            "codex --version",
        )
        if installed:
            print(f"OpenAI Codex version: {output}")  # noqa: T201
        else:
            pytest.skip("OpenAI Codex not installed (may not be publicly available)")

    def test_opencode_installation_status(self, all_tools_container: Container) -> None:
        """Check OpenCode installation status (may not be available yet)."""
        installed, output = check_tool_installed(
            all_tools_container,
            "OpenCode",
            "opencode --version",
        )
        if installed:
            print(f"OpenCode version: {output}")  # noqa: T201
        else:
            pytest.skip("OpenCode not installed (may not be publicly available)")

    def test_cursor_installation_status(self, all_tools_container: Container) -> None:
        """Check Cursor installation status (may not be available yet)."""
        # Cursor CLI installs as 'cursor-agent'
        installed, output = check_tool_installed(
            all_tools_container,
            "Cursor",
            "cursor-agent --version",
        )
        if installed:
            print(f"Cursor version: {output}")  # noqa: T201
        else:
            pytest.skip("Cursor CLI not installed (may not be publicly available)")


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.slow
class TestCodexPlaceholder:
    """Placeholder tests for OpenAI Codex integration.

    These tests will be expanded when ai-config adds Codex support.
    For now, they verify basic installation and document expected behavior.
    """

    def test_codex_config_dir_structure(self, all_tools_container: Container) -> None:
        """Document expected Codex config directory structure."""
        # Check if codex is installed first
        installed, _ = check_tool_installed(
            all_tools_container,
            "OpenAI Codex",
            "codex --version",
        )
        if not installed:
            pytest.skip("Codex not installed")

        # Document expected structure (to be implemented)
        expected_structure = """
        Expected Codex config structure (~/.codex/):
        - plugins/           # Plugin installation directory
        - config.json        # Main configuration
        - marketplace/       # Marketplace cache (if applicable)
        """
        print(expected_structure)  # noqa: T201

        # Check if config dir exists
        exit_code, output = exec_in_container(
            all_tools_container,
            "ls -la ~/.codex 2>&1 || echo 'Directory does not exist'",
        )
        print(f"Codex config directory status:\n{output}")  # noqa: T201


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.slow
class TestOpenCodePlaceholder:
    """Placeholder tests for OpenCode integration.

    These tests will be expanded when ai-config adds OpenCode support.
    For now, they verify basic installation and document expected behavior.
    """

    def test_opencode_config_dir_structure(self, all_tools_container: Container) -> None:
        """Document expected OpenCode config directory structure."""
        installed, _ = check_tool_installed(
            all_tools_container,
            "OpenCode",
            "opencode --version",
        )
        if not installed:
            pytest.skip("OpenCode not installed")

        expected_structure = """
        Expected OpenCode config structure (~/.opencode/):
        - plugins/           # Plugin installation directory
        - settings.yaml      # Main configuration
        """
        print(expected_structure)  # noqa: T201

        exit_code, output = exec_in_container(
            all_tools_container,
            "ls -la ~/.opencode 2>&1 || echo 'Directory does not exist'",
        )
        print(f"OpenCode config directory status:\n{output}")  # noqa: T201


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.slow
class TestCursorPlaceholder:
    """Placeholder tests for Cursor CLI integration.

    These tests will be expanded when ai-config adds Cursor support.
    For now, they verify basic installation and document expected behavior.
    """

    def test_cursor_config_dir_structure(self, all_tools_container: Container) -> None:
        """Document expected Cursor config directory structure."""
        # Cursor CLI installs as 'cursor-agent'
        installed, _ = check_tool_installed(
            all_tools_container,
            "Cursor",
            "cursor-agent --version",
        )
        if not installed:
            pytest.skip("Cursor CLI not installed")

        expected_structure = """
        Expected Cursor config structure (~/.cursor/):
        - extensions/        # Extension/plugin directory
        - settings.json      # Main configuration
        """
        print(expected_structure)  # noqa: T201

        exit_code, output = exec_in_container(
            all_tools_container,
            "ls -la ~/.cursor 2>&1 || echo 'Directory does not exist'",
        )
        print(f"Cursor config directory status:\n{output}")  # noqa: T201


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.slow
class TestAiConfigWithAllTools:
    """Test ai-config behavior in multi-tool environment."""

    def test_ai_config_works_with_all_tools_image(self, all_tools_container: Container) -> None:
        """Verify ai-config CLI works in the all-tools image."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config --help",
        )
        assert exit_code == 0, f"ai-config failed: {output}"
        assert "ai-config" in output.lower()

    def test_ai_config_status_in_multi_tool_env(self, all_tools_container: Container) -> None:
        """Verify ai-config status works in multi-tool environment."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config status",
        )
        assert exit_code == 0, f"ai-config status failed: {output}"
        print(f"ai-config status output:\n{output}")  # noqa: T201

    def test_future_multi_target_config(self, all_tools_container: Container) -> None:
        """Document expected multi-target config format for future implementation."""
        # This test documents the expected config format when multiple targets are supported
        future_config = """
# Future multi-target config format (not yet implemented):
version: 1
targets:
  - type: claude
    config:
      marketplaces:
        my-marketplace:
          source: github
          repo: owner/repo
      plugins:
        - id: my-plugin@my-marketplace
          scope: user

  - type: codex
    config:
      # Codex-specific configuration (TBD)
      plugins: []

  - type: opencode
    config:
      # OpenCode-specific configuration (TBD)
      plugins: []

  - type: cursor
    config:
      # Cursor-specific configuration (TBD)
      extensions: []
"""
        print(future_config)  # noqa: T201

        # For now, only claude target is supported
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config --help",
        )
        # Verify we get help output (current implementation)
        assert exit_code == 0
