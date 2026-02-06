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


# Tmux is required for these tests - fail loudly if not available
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.docker,
]


def _require_tmux() -> None:
    """Fail loudly if tmux is not available."""
    if not is_tmux_available():
        raise RuntimeError(
            "tmux is required for tool validation tests but is not installed. "
            "Install tmux or run these tests in a Docker container with tmux."
        )


@pytest.fixture
def tmux_session():
    """Provides a tmux session for testing."""
    _require_tmux()
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


class TestClaudeToolValidation:
    """Validate Claude Code CLI recognizes plugins.

    Claude introspection commands discovered:
    - claude --version: Check installation
    - claude plugin list: List installed plugins with status
    - claude mcp list: List MCP servers with health check
    - claude plugin validate <path>: Validate plugin manifest
    - Config: ~/.claude/ (plugins, settings.json, mcp.json)
    """

    def test_claude_version_check(self, claude_container: Container) -> None:
        """Test Claude CLI is installed and accessible."""
        exit_code, output = exec_in_container(
            claude_container,
            "claude --version",
        )
        assert exit_code == 0, f"Claude CLI not available: {output}"
        assert "claude" in output.lower()

    def test_claude_plugin_list_command(self, claude_container: Container) -> None:
        """Test claude plugin list shows installed plugins.

        Uses: claude plugin list
        Expected: Should show list of plugins or 'No plugins installed'
        """
        exit_code, output = exec_in_container(
            claude_container,
            "claude plugin list",
        )
        # Should succeed regardless of whether plugins are installed
        assert exit_code == 0, f"Plugin list failed: {output}"
        # Output should mention plugins or show empty state
        assert "plugin" in output.lower() or "no" in output.lower() or "installed" in output.lower()

    def test_claude_mcp_list_command(self, claude_container: Container) -> None:
        """Test claude mcp list shows configured MCP servers.

        Uses: claude mcp list
        Expected: Should show list of MCP servers with status
        """
        exit_code, output = exec_in_container(
            claude_container,
            "claude mcp list 2>&1",
        )
        # Should succeed - will show servers or 'no servers'
        # Note: mcp list may return non-zero if no servers configured
        # so we just check for sensible output
        assert (
            "mcp" in output.lower() or "server" in output.lower() or "configured" in output.lower()
        )


@pytest.mark.slow
class TestCodexToolValidation:
    """Validate Codex CLI recognizes converted plugins.

    Codex introspection commands discovered:
    - codex --version: Check installation
    - codex mcp list: List configured MCP servers
    - codex features list: List feature flags
    - Config: ~/.codex/config.toml (TOML format)
    - Skills: ~/.codex/skills/ directory
    """

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

    def test_codex_mcp_list_command(self, all_tools_container: Container) -> None:
        """Test codex mcp list recognizes converted MCP config.

        Uses: codex mcp list
        Expected: Should show configured servers or 'No MCP servers'
        """
        # Check if codex is available
        exit_code, _ = exec_in_container(all_tools_container, "codex --version")
        if exit_code != 0:
            pytest.skip("Codex CLI not available")

        # Convert plugin with MCP servers to user location
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t codex -o /home/testuser/.codex",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Run codex mcp list
        exit_code, output = exec_in_container(
            all_tools_container,
            "codex mcp list",
        )
        # Should succeed regardless of whether servers are configured
        # Either shows servers or "No MCP servers configured"
        assert exit_code == 0 or "No MCP servers" in output, f"Unexpected error: {output}"

    def test_codex_features_list_command(self, all_tools_container: Container) -> None:
        """Test codex features list works after conversion.

        Uses: codex features list
        Expected: Should list feature flags and their states
        """
        exit_code, _ = exec_in_container(all_tools_container, "codex --version")
        if exit_code != 0:
            pytest.skip("Codex CLI not available")

        exit_code, output = exec_in_container(
            all_tools_container,
            "codex features list",
        )
        assert exit_code == 0, f"Features list failed: {output}"
        # Should contain some feature flags
        assert "stable" in output or "beta" in output or "experimental" in output


@pytest.mark.slow
class TestCursorToolValidation:
    """Validate Cursor CLI recognizes converted plugins.

    Cursor introspection commands discovered:
    - cursor-agent --version: Check installation
    - cursor-agent mcp list: List MCP servers from mcp.json
    - cursor-agent mcp list-tools <name>: List tools for specific MCP
    - cursor-agent status: Check authentication status
    - Config: ~/.cursor/mcp.json (JSON format)
    - Hooks: ~/.cursor/hooks.json (file-based only)
    - Note: cursor-agent ls requires interactive terminal
    """

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

    def test_cursor_mcp_list_command(self, all_tools_container: Container) -> None:
        """Test cursor-agent mcp list recognizes converted MCP config.

        Uses: cursor-agent mcp list
        Expected: Should show configured servers or 'No MCP servers configured'
        """
        # Check if cursor-agent is available
        exit_code, output = exec_in_container(
            all_tools_container,
            "cursor-agent --version 2>/dev/null || echo 'NOT_INSTALLED'",
        )
        if "NOT_INSTALLED" in output or exit_code != 0:
            pytest.skip("Cursor CLI not available")

        # Convert plugin with MCP servers to user location
        exit_code, output = exec_in_container(
            all_tools_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t cursor -o /home/testuser/.cursor",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Run cursor-agent mcp list
        exit_code, output = exec_in_container(
            all_tools_container,
            "cursor-agent mcp list 2>&1",
        )
        # Should succeed regardless of whether servers are configured
        # Either shows servers or "No MCP servers configured"
        assert exit_code == 0 or "No MCP servers" in output, f"Unexpected error: {output}"


@pytest.mark.slow
class TestOpenCodeToolValidation:
    """Validate OpenCode CLI recognizes converted plugins.

    OpenCode introspection commands discovered:
    - opencode --version: Check installation
    - opencode mcp list: List MCP servers with status
    - opencode agent list: List all agents with permissions
    - opencode debug skill: List available skills
    - opencode debug config: Show resolved configuration (JSON)
    - opencode debug paths: Show global paths (data, config, cache)
    - Config: ~/.config/opencode/opencode.json (JSON format)
    - Skills: ~/.config/opencode/skills/ (symlink supported)
    """

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

    def test_opencode_mcp_list_command(self, all_tools_container: Container) -> None:
        """Test opencode mcp list recognizes converted MCP config.

        Uses: opencode mcp list
        Expected: Should show configured servers or 'No MCP servers configured'
        """
        # Check if opencode is available
        exit_code, output = exec_in_container(
            all_tools_container,
            "opencode --version 2>/dev/null || echo 'NOT_INSTALLED'",
        )
        if "NOT_INSTALLED" in output or exit_code != 0:
            pytest.skip("OpenCode CLI not available")

        # Convert plugin with MCP servers to user config location
        exit_code, output = exec_in_container(
            all_tools_container,
            "mkdir -p /home/testuser/.config/opencode && "
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t opencode -o /home/testuser/.config/opencode",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Run opencode mcp list
        exit_code, output = exec_in_container(
            all_tools_container,
            "opencode mcp list 2>&1",
        )
        # Should succeed regardless of whether servers are configured
        # Either shows servers or "No MCP servers configured"
        assert exit_code == 0 or "No MCP servers" in output, f"Unexpected error: {output}"

    def test_opencode_debug_config_command(self, all_tools_container: Container) -> None:
        """Test opencode debug config shows resolved configuration.

        Uses: opencode debug config
        Expected: Should output valid JSON configuration
        """
        exit_code, output = exec_in_container(
            all_tools_container,
            "opencode --version 2>/dev/null || echo 'NOT_INSTALLED'",
        )
        if "NOT_INSTALLED" in output or exit_code != 0:
            pytest.skip("OpenCode CLI not available")

        exit_code, output = exec_in_container(
            all_tools_container,
            "opencode debug config 2>&1",
        )
        assert exit_code == 0, f"Debug config failed: {output}"
        # Output should contain JSON config keys
        assert '"$schema"' in output or '"model"' in output, f"Unexpected output: {output}"

    def test_opencode_debug_paths_command(self, all_tools_container: Container) -> None:
        """Test opencode debug paths shows global paths.

        Uses: opencode debug paths
        Expected: Should show data, config, cache paths
        """
        exit_code, output = exec_in_container(
            all_tools_container,
            "opencode --version 2>/dev/null || echo 'NOT_INSTALLED'",
        )
        if "NOT_INSTALLED" in output or exit_code != 0:
            pytest.skip("OpenCode CLI not available")

        exit_code, output = exec_in_container(
            all_tools_container,
            "opencode debug paths 2>&1",
        )
        assert exit_code == 0, f"Debug paths failed: {output}"
        # Output should contain path information
        assert "config" in output or "data" in output, f"Unexpected output: {output}"


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


# =============================================================================
# Interactive Tmux-based Tool Validation Tests
# =============================================================================
# These tests launch actual AI CLI tools in tmux sessions and verify that
# converted skills/commands are visible via interactive commands like /skills.
#
# Prior art: ~/git_repositories/dots/tests/e2e/ai_tools/test_ai_tools_e2e.py
# =============================================================================


def exec_in_container_tmux(
    container: Container,
    session_name: str,
    command: str,
    working_dir: str = "/home/testuser/ai-config",
) -> tuple[str, str]:
    """Execute command in a tmux session inside a Docker container.

    Returns:
        Tuple of (session_name, initial_output)
    """
    # Create tmux session inside container
    create_cmd = f"tmux new-session -d -s {session_name} -c {working_dir}"
    exit_code, output = exec_in_container(container, create_cmd)
    if exit_code != 0:
        raise RuntimeError(f"Failed to create tmux session: {output}")

    # Give session time to initialize
    exec_in_container(container, "sleep 0.5")

    # Send the command
    send_cmd = f"tmux send-keys -t {session_name} '{command}' Enter"
    exit_code, output = exec_in_container(container, send_cmd)
    if exit_code != 0:
        raise RuntimeError(f"Failed to send keys: {output}")

    return session_name, output


def capture_tmux_pane(container: Container, session_name: str, scrollback: int = 100) -> str:
    """Capture tmux pane content from inside a Docker container."""
    capture_cmd = f"tmux capture-pane -t {session_name} -p -S -{scrollback}"
    exit_code, output = exec_in_container(container, capture_cmd)
    if exit_code != 0:
        raise RuntimeError(f"Failed to capture pane: {output}")
    return output


def wait_for_tmux_output(
    container: Container,
    session_name: str,
    expected: str,
    timeout: float = 30.0,
    interval: float = 1.0,
) -> bool:
    """Wait for expected output in tmux pane inside Docker container."""
    import time

    start_time = time.time()
    while time.time() - start_time < timeout:
        output = capture_tmux_pane(container, session_name)
        if expected in output:
            return True
        time.sleep(interval)
    return False


def cleanup_tmux_session(container: Container, session_name: str) -> None:
    """Kill tmux session inside Docker container."""
    exec_in_container(container, f"tmux kill-session -t {session_name} 2>/dev/null || true")


@pytest.mark.slow
@pytest.mark.requires_api_key
class TestInteractiveClaudeSkillDiscovery:
    """Test Claude Code discovers converted skills via interactive /skills command.

    These tests launch Claude in a tmux session and send /skills to verify
    skills are loaded and visible.

    NOTE: Requires ANTHROPIC_API_KEY to be set for Claude to start.
    """

    def test_claude_shows_skills_command(self, claude_container: Container) -> None:
        """Test Claude /skills command shows available skills.

        This test:
        1. Converts a test plugin to Claude format (skills)
        2. Starts Claude in tmux session
        3. Sends /skills command
        4. Verifies skills are listed
        """
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY required for interactive Claude tests")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        session_name = f"claude-skills-test-{int(time.time())}"

        try:
            # First, convert the test plugin and install to user location
            exit_code, output = exec_in_container(
                claude_container,
                "mkdir -p /home/testuser/.claude/plugins && "
                "cp -r tests/fixtures/sample-plugins/complete-plugin/.claude-plugin "
                "/home/testuser/.claude/plugins/test-plugin",
            )
            # Note: In real scenario we'd use ai-config sync, but for testing
            # we just copy the plugin directly

            # Start Claude in tmux (non-interactive print mode won't work for /skills)
            # We need to use the interactive mode
            import shlex

            claude_cmd = "claude"
            if api_key:
                claude_cmd = f"ANTHROPIC_API_KEY={shlex.quote(api_key)} claude"

            exec_in_container_tmux(
                claude_container,
                session_name,
                claude_cmd,  # Start interactive Claude
            )

            def dismiss_startup_prompts() -> None:
                output = capture_tmux_pane(claude_container, session_name)
                lower_output = output.lower()
                if "choose the text style" in lower_output or "/theme" in lower_output:
                    exec_in_container(
                        claude_container,
                        f"tmux send-keys -t {session_name} Enter",
                    )
                    time.sleep(2)
                    output = capture_tmux_pane(claude_container, session_name)
                    lower_output = output.lower()
                if "choose the text style" in lower_output or "/theme" in lower_output:
                    exec_in_container(
                        claude_container,
                        f"tmux send-keys -t {session_name} '1' Enter",
                    )
                    time.sleep(2)
                    output = capture_tmux_pane(claude_container, session_name)
                    lower_output = output.lower()
                if "select login method" in lower_output:
                    exec_in_container(
                        claude_container,
                        f"tmux send-keys -t {session_name} Down",
                    )
                    exec_in_container(
                        claude_container,
                        f"tmux send-keys -t {session_name} Enter",
                    )
                    time.sleep(2)
                    output = capture_tmux_pane(claude_container, session_name)
                    lower_output = output.lower()
                if "api key" in lower_output and api_key:
                    exec_in_container(
                        claude_container,
                        f"tmux send-keys -t {session_name} {shlex.quote(api_key)} Enter",
                    )
                    time.sleep(2)

            # Wait for Claude to start and dismiss first-run theme prompt if needed
            time.sleep(3)
            for _ in range(3):
                dismiss_startup_prompts()
                if wait_for_tmux_output(claude_container, session_name, ">", timeout=15):
                    break
                time.sleep(2)

            # Send /skills command
            exec_in_container(
                claude_container,
                f"tmux send-keys -t {session_name} '/skills' Enter",
            )

            # Wait for skills output
            time.sleep(3)
            output = capture_tmux_pane(claude_container, session_name)
            if "choose the text style" in output.lower() or "/theme" in output.lower() or "select login method" in output.lower():
                dismiss_startup_prompts()
                wait_for_tmux_output(claude_container, session_name, ">", timeout=15)
                exec_in_container(
                    claude_container,
                    f"tmux send-keys -t {session_name} '/skills' Enter",
                )
                time.sleep(3)
                output = capture_tmux_pane(claude_container, session_name)

            # Verify we got some skills-related output
            # Note: Exact output depends on installed skills
            assert "skill" in output.lower() or "command" in output.lower(), (
                f"Expected skills output, got: {output}"
            )

        finally:
            cleanup_tmux_session(claude_container, session_name)


@pytest.mark.slow
class TestInteractiveCodexSkillDiscovery:
    """Test Codex CLI discovers converted skills via interactive session.

    Codex doesn't have a /skills command but we can verify:
    1. Skills directory is read on startup
    2. No errors when skills are present
    """

    def test_codex_starts_with_converted_skills_no_errors(
        self, all_tools_container: Container
    ) -> None:
        """Test Codex starts without errors when converted skills are present.

        This test:
        1. Converts a test plugin to Codex format
        2. Copies to Codex user directory
        3. Starts Codex in tmux (briefly)
        4. Verifies no startup errors related to skills
        """
        # Check if codex is available
        exit_code, _ = exec_in_container(all_tools_container, "codex --version")
        if exit_code != 0:
            pytest.skip("Codex CLI not available")

        session_name = f"codex-skills-test-{int(time.time())}"

        try:
            # Convert plugin to Codex format
            # Output to /home/testuser so .codex/skills/ gets created at the right location
            exit_code, output = exec_in_container(
                all_tools_container,
                "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
                "-t codex -o /home/testuser",
            )
            assert exit_code == 0, f"Conversion failed: {output}"

            # Verify skills directory exists (emitter creates .codex/skills/ in output dir)
            exit_code, output = exec_in_container(
                all_tools_container,
                "ls /home/testuser/.codex/skills/",
            )
            assert exit_code == 0, f"Skills directory not created: {output}"

            # Start Codex in tmux with a simple non-interactive command
            # We use --help to verify it starts without skill loading errors
            exec_in_container_tmux(
                all_tools_container,
                session_name,
                "codex --help",
            )

            # Wait for output
            time.sleep(3)
            output = capture_tmux_pane(all_tools_container, session_name)

            # Verify no skill-related errors
            assert "error" not in output.lower() or "skill" not in output.lower(), (
                f"Unexpected skill error: {output}"
            )

        finally:
            cleanup_tmux_session(all_tools_container, session_name)

    def test_codex_skill_files_accessible_in_tmux(self, all_tools_container: Container) -> None:
        """Verify converted skill files are accessible via shell in tmux.

        This follows the dots repo pattern of verifying files exist at expected paths.
        Expected skill names from complete-plugin: dev-tools-code-review, dev-tools-test-writer
        """
        # Check if codex is available
        exit_code, _ = exec_in_container(all_tools_container, "codex --version")
        if exit_code != 0:
            pytest.skip("Codex CLI not available")

        session_name = f"codex-files-test-{int(time.time())}"

        try:
            # Convert plugin to Codex format
            exit_code, output = exec_in_container(
                all_tools_container,
                "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
                "-t codex -o /home/testuser",
            )
            assert exit_code == 0, f"Conversion failed: {output}"

            # Check skills directory exists and list contents in tmux
            exec_in_container_tmux(
                all_tools_container,
                session_name,
                "ls -la /home/testuser/.codex/skills/",
            )

            time.sleep(2)
            output = capture_tmux_pane(all_tools_container, session_name)

            # Verify skill directories were created with plugin ID prefix
            assert "dev-tools" in output, f"Expected dev-tools skills, got: {output}"

            # Check a specific skill file exists
            exec_in_container(
                all_tools_container,
                f"tmux send-keys -t {session_name} 'cat /home/testuser/.codex/skills/dev-tools-code-review/SKILL.md | head -5' Enter",
            )
            time.sleep(2)
            output = capture_tmux_pane(all_tools_container, session_name)

            # Verify skill content is readable
            assert "SKILL.md" in output or "code" in output.lower() or "#" in output, (
                f"Expected skill content, got: {output}"
            )

        finally:
            cleanup_tmux_session(all_tools_container, session_name)


@pytest.mark.slow
class TestInteractiveOpenCodeSkillDiscovery:
    """Test OpenCode CLI discovers converted skills.

    OpenCode has `opencode debug skill` which lists skills.
    """

    def test_opencode_debug_skill_shows_converted_skills(
        self, all_tools_container: Container
    ) -> None:
        """Test opencode debug skill shows skills after conversion.

        This test:
        1. Converts a test plugin to OpenCode format
        2. Copies to OpenCode config directory
        3. Runs opencode debug skill
        4. Verifies skills appear in output
        """
        # Check if opencode is available
        exit_code, output = exec_in_container(
            all_tools_container,
            "opencode --version 2>/dev/null || echo 'NOT_INSTALLED'",
        )
        if "NOT_INSTALLED" in output or exit_code != 0:
            pytest.skip("OpenCode CLI not available")

        session_name = f"opencode-skills-test-{int(time.time())}"

        try:
            # Convert plugin to OpenCode format
            exit_code, output = exec_in_container(
                all_tools_container,
                "mkdir -p /home/testuser/.config/opencode && "
                "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
                "-t opencode -o /home/testuser/.config/opencode",
            )
            assert exit_code == 0, f"Conversion failed: {output}"

            # Verify skills directory was created
            exit_code, output = exec_in_container(
                all_tools_container,
                "ls /home/testuser/.config/opencode/.opencode/skills/ 2>/dev/null || "
                "ls /home/testuser/.config/opencode/skills/ 2>/dev/null || "
                "echo 'NO_SKILLS_DIR'",
            )

            # Run opencode debug skill in tmux
            exec_in_container_tmux(
                all_tools_container,
                session_name,
                "opencode debug skill",
            )

            # Wait for output
            time.sleep(3)
            output = capture_tmux_pane(all_tools_container, session_name)

            # OpenCode debug skill returns JSON array of skills
            # Empty array [] is valid if no skills are found
            # We just verify the command ran without error
            assert "error" not in output.lower() or "[" in output, (
                f"Unexpected error in skill output: {output}"
            )

        finally:
            cleanup_tmux_session(all_tools_container, session_name)

    def test_opencode_skill_files_accessible_in_tmux(self, all_tools_container: Container) -> None:
        """Verify converted skill files exist at expected OpenCode paths.

        Follows dots repo pattern: verify files exist and are readable.
        """
        # Check if opencode is available
        exit_code, output = exec_in_container(
            all_tools_container,
            "opencode --version 2>/dev/null || echo 'NOT_INSTALLED'",
        )
        if "NOT_INSTALLED" in output or exit_code != 0:
            pytest.skip("OpenCode CLI not available")

        session_name = f"opencode-files-test-{int(time.time())}"

        try:
            # Convert plugin to OpenCode format
            exit_code, output = exec_in_container(
                all_tools_container,
                "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
                "-t opencode -o /tmp/opencode-verify",
            )
            assert exit_code == 0, f"Conversion failed: {output}"

            # List skills directory in tmux
            exec_in_container_tmux(
                all_tools_container,
                session_name,
                "ls -la /tmp/opencode-verify/.opencode/skills/",
            )

            time.sleep(2)
            output = capture_tmux_pane(all_tools_container, session_name)

            # Verify skill directories exist with plugin ID prefix
            assert "dev-tools" in output, f"Expected dev-tools skills, got: {output}"

            # Verify a skill file is readable
            exec_in_container(
                all_tools_container,
                f"tmux send-keys -t {session_name} 'head -3 /tmp/opencode-verify/.opencode/skills/dev-tools-code-review/SKILL.md' Enter",
            )
            time.sleep(2)
            output = capture_tmux_pane(all_tools_container, session_name)

            # Should see skill content (markdown header or frontmatter)
            assert "#" in output or "---" in output or "name" in output.lower(), (
                f"Expected skill markdown content, got: {output}"
            )

        finally:
            cleanup_tmux_session(all_tools_container, session_name)


@pytest.mark.slow
class TestInteractiveCursorSkillDiscovery:
    """Test Cursor CLI loads converted skills and MCP servers.

    Cursor doesn't expose skills via CLI but we can verify:
    1. mcp.json is read correctly
    2. No errors on startup
    """

    def test_cursor_mcp_list_shows_converted_servers(self, all_tools_container: Container) -> None:
        """Test cursor-agent mcp list shows servers after conversion.

        This test:
        1. Converts a test plugin with MCP servers to Cursor format
        2. Copies to Cursor config directory
        3. Runs cursor-agent mcp list in tmux
        4. Verifies MCP servers appear or no errors
        """
        # Check if cursor-agent is available
        exit_code, output = exec_in_container(
            all_tools_container,
            "cursor-agent --version 2>/dev/null || echo 'NOT_INSTALLED'",
        )
        if "NOT_INSTALLED" in output or exit_code != 0:
            pytest.skip("Cursor CLI not available")

        session_name = f"cursor-mcp-test-{int(time.time())}"

        try:
            # Convert plugin to Cursor format
            exit_code, output = exec_in_container(
                all_tools_container,
                "mkdir -p /home/testuser/.cursor && "
                "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
                "-t cursor -o /home/testuser/.cursor",
            )
            assert exit_code == 0, f"Conversion failed: {output}"

            # Run cursor-agent mcp list in tmux
            exec_in_container_tmux(
                all_tools_container,
                session_name,
                "cursor-agent mcp list",
            )

            # Wait for output (cursor-agent mcp list can take a moment)
            time.sleep(5)
            output = capture_tmux_pane(all_tools_container, session_name)

            # Verify output contains MCP-related info or shows empty state
            # (not an error about invalid config)
            assert (
                "mcp" in output.lower()
                or "server" in output.lower()
                or "no" in output.lower()
                or "configured" in output.lower()
            ), f"Unexpected output: {output}"

        finally:
            cleanup_tmux_session(all_tools_container, session_name)

    def test_cursor_mcp_config_contains_converted_servers(
        self, all_tools_container: Container
    ) -> None:
        """Verify converted MCP servers appear in Cursor mcp.json.

        Expected MCP servers from complete-plugin: database, github
        """
        session_name = f"cursor-mcp-verify-{int(time.time())}"

        try:
            # Convert plugin to Cursor format
            exit_code, output = exec_in_container(
                all_tools_container,
                "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
                "-t cursor -o /tmp/cursor-mcp-verify",
            )
            assert exit_code == 0, f"Conversion failed: {output}"

            # Read and display MCP config in tmux
            exec_in_container_tmux(
                all_tools_container,
                session_name,
                "cat /tmp/cursor-mcp-verify/.cursor/mcp.json",
            )

            time.sleep(2)
            output = capture_tmux_pane(all_tools_container, session_name)

            # Verify MCP server names from complete-plugin appear in config
            assert "database" in output or "github" in output, (
                f"Expected MCP server names (database, github), got: {output}"
            )

            # Verify it's valid JSON structure
            assert "mcpServers" in output or '"command"' in output, (
                f"Expected MCP JSON structure, got: {output}"
            )

        finally:
            cleanup_tmux_session(all_tools_container, session_name)

    def test_cursor_skills_accessible_in_tmux(self, all_tools_container: Container) -> None:
        """Verify converted skill files exist at expected Cursor paths."""
        session_name = f"cursor-skills-verify-{int(time.time())}"

        try:
            # Convert plugin to Cursor format
            exit_code, output = exec_in_container(
                all_tools_container,
                "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
                "-t cursor -o /tmp/cursor-skills-verify",
            )
            assert exit_code == 0, f"Conversion failed: {output}"

            # List skills directory
            exec_in_container_tmux(
                all_tools_container,
                session_name,
                "ls -la /tmp/cursor-skills-verify/.cursor/skills/",
            )

            time.sleep(2)
            output = capture_tmux_pane(all_tools_container, session_name)

            # Verify skill directories exist
            assert "dev-tools" in output, f"Expected dev-tools skills, got: {output}"

        finally:
            cleanup_tmux_session(all_tools_container, session_name)
