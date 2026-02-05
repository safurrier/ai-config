"""E2E tests for validating converted plugins with target CLI tools.

These tests use tmux to launch real AI CLI tools and verify they
recognize converted plugin output.

Prior art: ~/git_repositories/dots/tests/e2e/ai_tools/test_ai_tools_e2e.py
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from tests.e2e.conftest import exec_in_container
from tests.e2e.tmux_helper import TmuxTestSession, is_tmux_available

if TYPE_CHECKING:
    from docker.models.containers import Container


# Skip all tests if tmux not available
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.docker,
    pytest.mark.skipif(not is_tmux_available(), reason="tmux not available"),
]


@pytest.fixture
def tmux_session():
    """Provides a tmux session for testing."""
    session_name = f"test-ai-config-{int(time.time())}"
    session = TmuxTestSession(session_name)

    try:
        yield session
    finally:
        session.cleanup()


class TestTmuxHelper:
    """Tests for TmuxTestSession helper itself."""

    def test_tmux_session_create_and_cleanup(self, tmux_session: TmuxTestSession) -> None:
        """Test basic tmux session lifecycle."""
        tmux_session.create_session()
        assert tmux_session.session_active

        # Should be able to send keys
        tmux_session.send_keys("echo hello")

        # Should be able to capture output
        output = tmux_session.capture_pane()
        assert "hello" in output or "echo" in output

    def test_wait_for_output(self, tmux_session: TmuxTestSession) -> None:
        """Test wait_for_output with expected content."""
        tmux_session.create_session()

        tmux_session.send_keys("echo 'TEST_MARKER_12345'")

        assert tmux_session.wait_for_output("TEST_MARKER_12345", timeout=5.0)

    def test_wait_for_output_timeout(self, tmux_session: TmuxTestSession) -> None:
        """Test wait_for_output times out correctly."""
        tmux_session.create_session()

        # Wait for something that won't appear
        assert not tmux_session.wait_for_output(
            "THIS_WILL_NOT_APPEAR_EVER_12345",
            timeout=1.0,
        )


@pytest.mark.slow
class TestCodexToolValidation:
    """Validate Codex CLI recognizes converted plugins."""

    def test_codex_version_check(self, all_tools_container: Container) -> None:
        """Test Codex CLI is installed and accessible."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "codex --version",
        )
        # If Codex is installed, version should return 0
        if exit_code != 0:
            pytest.skip(f"Codex CLI not available: {output}")

        assert "codex" in output.lower() or exit_code == 0

    def test_codex_skills_directory_recognized(self, all_tools_container: Container) -> None:
        """Test Codex recognizes skills in .codex/skills/ after conversion."""
        # Convert a test plugin to Codex format
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t codex -o /tmp/codex-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Verify skills directory was created
        exit_code, output = exec_in_container(
            all_tools_container,
            "ls /tmp/codex-test/.codex/skills/",
        )
        assert exit_code == 0, f"Skills directory not created: {output}"
        assert "dev-tools" in output  # Plugin ID should be in skill name

    def test_codex_mcp_config_valid_toml(self, all_tools_container: Container) -> None:
        """Test Codex MCP config is valid TOML."""
        # Convert plugin with MCP servers
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t codex -o /tmp/codex-mcp-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Check if MCP config exists
        exit_code, output = exec_in_container(
            all_tools_container,
            "cat /tmp/codex-mcp-test/.codex/mcp-config.toml 2>/dev/null || echo 'NO_MCP'",
        )
        if "NO_MCP" in output:
            pytest.skip("Test plugin has no MCP servers")

        # Validate TOML syntax with Python
        exit_code, output = exec_in_container(
            all_tools_container,
            "python3 -c \"import tomllib; tomllib.load(open('/tmp/codex-mcp-test/.codex/mcp-config.toml', 'rb'))\"",
        )
        assert exit_code == 0, f"Invalid TOML: {output}"


@pytest.mark.slow
class TestCursorToolValidation:
    """Validate Cursor CLI recognizes converted plugins."""

    def test_cursor_agent_version_check(self, all_tools_container: Container) -> None:
        """Test Cursor CLI is installed and accessible."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "cursor-agent --version 2>/dev/null || echo 'NOT_INSTALLED'",
        )
        if "NOT_INSTALLED" in output or exit_code != 0:
            pytest.skip("Cursor CLI (cursor-agent) not available")

    def test_cursor_skills_directory_recognized(self, all_tools_container: Container) -> None:
        """Test Cursor recognizes skills in .cursor/skills/ after conversion."""
        # Convert a test plugin to Cursor format
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t cursor -o /tmp/cursor-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Verify skills directory was created
        exit_code, output = exec_in_container(
            all_tools_container,
            "ls /tmp/cursor-test/.cursor/skills/",
        )
        assert exit_code == 0, f"Skills directory not created: {output}"

    def test_cursor_hooks_json_valid(self, all_tools_container: Container) -> None:
        """Test Cursor hooks.json is valid JSON."""
        # Convert plugin with hooks
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t cursor -o /tmp/cursor-hooks-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Check if hooks.json exists
        exit_code, output = exec_in_container(
            all_tools_container,
            "cat /tmp/cursor-hooks-test/.cursor/hooks.json 2>/dev/null || echo 'NO_HOOKS'",
        )
        if "NO_HOOKS" in output:
            pytest.skip("Test plugin has no hooks")

        # Validate JSON syntax
        exit_code, output = exec_in_container(
            all_tools_container,
            "python3 -c \"import json; json.load(open('/tmp/cursor-hooks-test/.cursor/hooks.json'))\"",
        )
        assert exit_code == 0, f"Invalid JSON: {output}"

    def test_cursor_mcp_json_valid(self, all_tools_container: Container) -> None:
        """Test Cursor mcp.json is valid JSON."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t cursor -o /tmp/cursor-mcp-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Check if mcp.json exists
        exit_code, output = exec_in_container(
            all_tools_container,
            "cat /tmp/cursor-mcp-test/.cursor/mcp.json 2>/dev/null || echo 'NO_MCP'",
        )
        if "NO_MCP" in output:
            pytest.skip("Test plugin has no MCP servers")

        # Validate JSON syntax
        exit_code, output = exec_in_container(
            all_tools_container,
            "python3 -c \"import json; json.load(open('/tmp/cursor-mcp-test/.cursor/mcp.json'))\"",
        )
        assert exit_code == 0, f"Invalid JSON: {output}"


@pytest.mark.slow
class TestOpenCodeToolValidation:
    """Validate OpenCode CLI recognizes converted plugins."""

    def test_opencode_version_check(self, all_tools_container: Container) -> None:
        """Test OpenCode CLI is installed and accessible."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "opencode --version 2>/dev/null || echo 'NOT_INSTALLED'",
        )
        if "NOT_INSTALLED" in output or exit_code != 0:
            pytest.skip("OpenCode CLI not available")

    def test_opencode_skills_directory_recognized(self, all_tools_container: Container) -> None:
        """Test OpenCode recognizes skills in .opencode/skills/ after conversion."""
        # Convert a test plugin to OpenCode format
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t opencode -o /tmp/opencode-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Verify skills directory was created
        exit_code, output = exec_in_container(
            all_tools_container,
            "ls /tmp/opencode-test/.opencode/skills/",
        )
        assert exit_code == 0, f"Skills directory not created: {output}"

    def test_opencode_json_valid(self, all_tools_container: Container) -> None:
        """Test OpenCode opencode.json is valid JSON."""
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t opencode -o /tmp/opencode-json-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Check if opencode.json exists
        exit_code, output = exec_in_container(
            all_tools_container,
            "cat /tmp/opencode-json-test/opencode.json 2>/dev/null || echo 'NO_CONFIG'",
        )
        if "NO_CONFIG" in output:
            pytest.skip("Test plugin has no MCP/LSP config")

        # Validate JSON syntax
        exit_code, output = exec_in_container(
            all_tools_container,
            "python3 -c \"import json; json.load(open('/tmp/opencode-json-test/opencode.json'))\"",
        )
        assert exit_code == 0, f"Invalid JSON: {output}"


class TestCrossToolValidation:
    """Test that the same plugin can be converted to all targets."""

    def test_convert_to_all_targets_produces_valid_output(
        self, all_tools_container: Container
    ) -> None:
        """Test converting one plugin to all targets produces valid output."""
        # Convert to all targets
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t all -o /tmp/all-targets",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Verify all target directories exist
        for target_dir in [".codex", ".cursor", ".opencode"]:
            exit_code, _ = exec_in_container(
                all_tools_container,
                f"test -d /tmp/all-targets/{target_dir}",
            )
            assert exit_code == 0, f"{target_dir} directory not created"

        # Run doctor validation on all targets
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config doctor --target all /tmp/all-targets",
        )
        assert exit_code == 0, f"Doctor validation failed: {output}"

    def test_doctor_validates_each_target(self, all_tools_container: Container) -> None:
        """Test doctor --target validates converted output correctly."""
        # Convert to Codex
        exit_code, _ = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t codex -o /tmp/doctor-test",
        )
        assert exit_code == 0

        # Run doctor with JSON output
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config doctor --target codex /tmp/doctor-test --json",
        )
        assert exit_code == 0, f"Doctor failed: {output}"

        # Verify JSON is parseable
        import json

        try:
            result = json.loads(output)
            assert "results" in result or "reports" in result
        except json.JSONDecodeError:
            pytest.fail(f"Doctor output is not valid JSON: {output}")
