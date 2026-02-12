"""E2E tests for plugin conversion.

Tests that converted plugins are valid and can be used by target tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.e2e.conftest import exec_in_container

if TYPE_CHECKING:
    from docker.models.containers import Container


@pytest.mark.e2e
@pytest.mark.docker
class TestConversionCLI:
    """Tests for the convert CLI command."""

    def test_convert_help(self, claude_container: Container) -> None:
        """Test that convert command help is accessible."""
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert --help",
        )

        assert exit_code == 0
        assert "Convert a Claude Code plugin" in output
        assert "codex" in output
        assert "cursor" in output
        assert "opencode" in output

    def test_convert_dry_run(self, claude_container: Container) -> None:
        """Test conversion dry-run mode."""
        # First, verify the test fixture exists
        exit_code, output = exec_in_container(
            claude_container,
            "ls tests/fixtures/sample-plugins/complete-plugin/.claude-plugin/plugin.json",
        )
        assert exit_code == 0, f"Test fixture not found: {output}"

        # Run dry-run conversion
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin --dry-run -t codex",
        )

        assert exit_code == 0, f"Conversion failed: {output}"
        assert "preview" in output.lower() or "CODEX" in output
        # Verify no files were actually created in dry-run
        assert "dev-tools" in output  # Plugin name should appear

    def test_convert_all_targets(self, claude_container: Container) -> None:
        """Test conversion to all targets."""
        # Create output directory
        exit_code, _ = exec_in_container(
            claude_container,
            "mkdir -p /tmp/converted",
        )
        assert exit_code == 0

        # Run conversion to all targets
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t all -o /tmp/converted",
        )

        assert exit_code == 0, f"Conversion failed: {output}"

        # Check that output directories were created for each target
        exit_code, listing = exec_in_container(
            claude_container,
            "ls -la /tmp/converted/",
        )
        assert exit_code == 0

        # Codex output
        exit_code, _ = exec_in_container(
            claude_container,
            "test -d /tmp/converted/.codex",
        )
        assert exit_code == 0, "Codex output directory not created"

        # Cursor output
        exit_code, _ = exec_in_container(
            claude_container,
            "test -d /tmp/converted/.cursor",
        )
        assert exit_code == 0, "Cursor output directory not created"

        # OpenCode output
        exit_code, _ = exec_in_container(
            claude_container,
            "test -d /tmp/converted/.opencode",
        )
        assert exit_code == 0, "OpenCode output directory not created"


@pytest.mark.e2e
@pytest.mark.docker
class TestCodexConversion:
    """Tests for Codex-specific conversion output."""

    def test_skill_files_created(self, claude_container: Container) -> None:
        """Test that skill files are created correctly for Codex."""
        # Run conversion
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/codex-test && mkdir -p /tmp/codex-test",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t codex -o /tmp/codex-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Check skill directories exist
        exit_code, _ = exec_in_container(
            claude_container,
            "test -f /tmp/codex-test/.codex/skills/dev-tools-code-review/SKILL.md",
        )
        assert exit_code == 0, "SKILL.md not created for code-review"

        # Check SKILL.md content
        exit_code, content = exec_in_container(
            claude_container,
            "cat /tmp/codex-test/.codex/skills/dev-tools-code-review/SKILL.md",
        )
        assert exit_code == 0
        assert "name:" in content
        assert "description:" in content
        # Claude-specific fields should be stripped
        assert "allowed-tools:" not in content

    def test_mcp_config_created(self, claude_container: Container) -> None:
        """Test that MCP config is created in TOML format for Codex."""
        # Run conversion
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/codex-mcp && mkdir -p /tmp/codex-mcp",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t codex -o /tmp/codex-mcp",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Check MCP config exists
        exit_code, content = exec_in_container(
            claude_container,
            "cat /tmp/codex-mcp/.codex/mcp-config.toml",
        )
        assert exit_code == 0
        assert "[mcp_servers." in content
        assert "command" in content

    def test_prompts_user_scope_written_to_home(self, claude_container: Container) -> None:
        """User-scope prompts should be written to ~/.codex/prompts/."""
        # Clean any prior prompts
        exec_in_container(claude_container, "rm -rf /home/testuser/.codex/prompts")

        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t codex --scope user",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        exit_code, listing = exec_in_container(
            claude_container,
            "ls /home/testuser/.codex/prompts",
        )
        assert exit_code == 0
        assert "dev-tools-commit.md" in listing


@pytest.mark.e2e
@pytest.mark.docker
class TestCursorConversion:
    """Tests for Cursor-specific conversion output."""

    def test_hooks_converted(self, claude_container: Container) -> None:
        """Test that hooks are converted to Cursor format."""
        # Run conversion
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/cursor-test && mkdir -p /tmp/cursor-test",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t cursor -o /tmp/cursor-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Check hooks.json was created
        exit_code, content = exec_in_container(
            claude_container,
            "cat /tmp/cursor-test/.cursor/hooks.json",
        )
        assert exit_code == 0
        assert '"hooks"' in content
        assert '"version"' in content

    def test_mcp_json_created(self, claude_container: Container) -> None:
        """Test that MCP config is created in JSON format for Cursor."""
        # Run conversion
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/cursor-mcp && mkdir -p /tmp/cursor-mcp",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t cursor -o /tmp/cursor-mcp",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Check MCP config exists
        exit_code, content = exec_in_container(
            claude_container,
            "cat /tmp/cursor-mcp/.cursor/mcp.json",
        )
        assert exit_code == 0
        assert '"mcpServers"' in content

    def test_env_var_syntax_transformed(self, claude_container: Container) -> None:
        """Cursor MCP env vars should use ${env:VAR} syntax."""
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/cursor-env && mkdir -p /tmp/cursor-env",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t cursor -o /tmp/cursor-env",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        exit_code, content = exec_in_container(
            claude_container,
            "cat /tmp/cursor-env/.cursor/mcp.json",
        )
        assert exit_code == 0
        assert "${env:DB_URL}" in content or "${env:GITHUB_TOKEN}" in content


@pytest.mark.e2e
@pytest.mark.docker
class TestOpenCodeConversion:
    """Tests for OpenCode-specific conversion output."""

    def test_lsp_config_created(self, claude_container: Container) -> None:
        """Test that LSP config is created for OpenCode."""
        # Run conversion
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/opencode-test && mkdir -p /tmp/opencode-test",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t opencode -o /tmp/opencode-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Check LSP config exists
        exit_code, content = exec_in_container(
            claude_container,
            "cat /tmp/opencode-test/opencode.lsp.json",
        )
        assert exit_code == 0
        assert '"lsp"' in content

    def test_multi_lsp_aggregated(self, claude_container: Container) -> None:
        """Multiple LSP servers should be aggregated into one config."""
        # Create a minimal plugin with multiple LSP servers
        exec_in_container(
            claude_container,
            "rm -rf /tmp/multi-lsp && mkdir -p /tmp/multi-lsp/.claude-plugin",
        )
        exec_in_container(
            claude_container,
            "cat > /tmp/multi-lsp/.claude-plugin/plugin.json <<'EOF'\n"
            "{\n"
            "  \"name\": \"multi-lsp\",\n"
            "  \"lspServers\": \"./.lsp.json\"\n"
            "}\n"
            "EOF",
        )
        exec_in_container(
            claude_container,
            "cat > /tmp/multi-lsp/.lsp.json <<'EOF'\n"
            "{\n"
            "  \"py\": {\"command\": \"pylsp\"},\n"
            "  \"go\": {\"command\": \"gopls\"}\n"
            "}\n"
            "EOF",
        )

        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert /tmp/multi-lsp -t opencode -o /tmp/multi-lsp-out",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        exit_code, content = exec_in_container(
            claude_container,
            "cat /tmp/multi-lsp-out/opencode.lsp.json",
        )
        assert exit_code == 0
        assert "multi-lsp-py" in content
        assert "multi-lsp-go" in content

    def test_env_var_syntax_transformed(self, claude_container: Container) -> None:
        """OpenCode MCP env vars should use {env:VAR} syntax."""
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/opencode-env && mkdir -p /tmp/opencode-env",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
            "-t opencode -o /tmp/opencode-env",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        exit_code, content = exec_in_container(
            claude_container,
            "cat /tmp/opencode-env/opencode.json",
        )
        assert exit_code == 0
        assert "{env:DB_URL}" in content or "{env:GITHUB_TOKEN}" in content


@pytest.mark.e2e
@pytest.mark.docker
class TestBinarySkillAssets:
    """Tests for binary asset conversion."""

    def test_binary_files_emitted(self, claude_container: Container) -> None:
        """Binary files in skills should be emitted to output."""
        exec_in_container(
            claude_container,
            "rm -rf /tmp/bin-plugin && mkdir -p /tmp/bin-plugin/.claude-plugin "
            "/tmp/bin-plugin/skills/bin-skill",
        )
        exec_in_container(
            claude_container,
            "cat > /tmp/bin-plugin/.claude-plugin/plugin.json <<'EOF'\n"
            "{\n"
            "  \"name\": \"bin-plugin\",\n"
            "  \"skills\": \"./skills\"\n"
            "}\n"
            "EOF",
        )
        exec_in_container(
            claude_container,
            "cat > /tmp/bin-plugin/skills/bin-skill/SKILL.md <<'EOF'\n"
            "---\n"
            "name: bin-skill\n"
            "description: binary\n"
            "---\n"
            "\n"
            "Body\n"
            "EOF",
        )
        exec_in_container(
            claude_container,
            "python - <<'PY'\n"
            "from pathlib import Path\n"
            "Path('/tmp/bin-plugin/skills/bin-skill/asset.bin').write_bytes(b'\\xff\\xfe\\x00\\x80binary')\n"
            "PY",
        )

        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert /tmp/bin-plugin -t codex -o /tmp/bin-out",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        exit_code, size = exec_in_container(
            claude_container,
            "python - <<'PY'\n"
            "from pathlib import Path\n"
            "p = Path('/tmp/bin-out/.codex/skills/bin-plugin-bin-skill/asset.bin')\n"
            "print(p.stat().st_size)\n"
            "PY",
        )
        assert exit_code == 0
        assert size.strip() != "0"


@pytest.mark.e2e
@pytest.mark.docker
class TestConversionReports:
    """Tests for conversion report generation."""

    def test_json_report_format(self, claude_container: Container) -> None:
        """Test JSON report output."""
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t codex --format json -o /tmp/report-test",
        )
        assert exit_code == 0, f"Conversion failed: {output}"
        # JSON output should be valid
        assert '"source_plugin"' in output or '"target_tool"' in output

    def test_markdown_report_format(self, claude_container: Container) -> None:
        """Test Markdown report output."""
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t codex --format markdown -o /tmp/report-test-md",
        )
        assert exit_code == 0, f"Conversion failed: {output}"
        assert "# Conversion Report" in output


@pytest.mark.e2e
@pytest.mark.docker
class TestDoctorTargetValidation:
    """E2E tests for doctor --target command validating converted output."""

    def test_doctor_target_codex_valid(self, claude_container: Container) -> None:
        """Test doctor validates valid Codex conversion output."""
        # First convert the plugin
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/doctor-codex && mkdir -p /tmp/doctor-codex",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t codex -o /tmp/doctor-codex",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Now validate with doctor
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config doctor --target codex /tmp/doctor-codex",
        )
        assert exit_code == 0, f"Doctor validation failed: {output}"
        assert "codex" in output.lower()
        # Should show passed status
        assert "pass" in output.lower()

    def test_doctor_target_cursor_valid(self, claude_container: Container) -> None:
        """Test doctor validates valid Cursor conversion output."""
        # First convert the plugin
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/doctor-cursor && mkdir -p /tmp/doctor-cursor",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t cursor -o /tmp/doctor-cursor",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Now validate with doctor
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config doctor --target cursor /tmp/doctor-cursor",
        )
        assert exit_code == 0, f"Doctor validation failed: {output}"
        assert "cursor" in output.lower()
        assert "pass" in output.lower()

    def test_doctor_target_opencode_valid(self, claude_container: Container) -> None:
        """Test doctor validates valid OpenCode conversion output."""
        # First convert the plugin
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/doctor-opencode && mkdir -p /tmp/doctor-opencode",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t opencode -o /tmp/doctor-opencode",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Now validate with doctor
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config doctor --target opencode /tmp/doctor-opencode",
        )
        assert exit_code == 0, f"Doctor validation failed: {output}"
        assert "opencode" in output.lower()
        assert "pass" in output.lower()

    def test_doctor_target_all(self, claude_container: Container) -> None:
        """Test doctor validates all targets at once."""
        # First convert the plugin to all targets
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/doctor-all && mkdir -p /tmp/doctor-all",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t all -o /tmp/doctor-all",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Now validate all with doctor
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config doctor --target all /tmp/doctor-all",
        )
        assert exit_code == 0, f"Doctor validation failed: {output}"
        # Should mention all three targets
        output_lower = output.lower()
        assert "codex" in output_lower
        assert "cursor" in output_lower
        assert "opencode" in output_lower

    def test_doctor_target_json_output(self, claude_container: Container) -> None:
        """Test doctor target can output JSON."""
        # First convert the plugin
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/doctor-json && mkdir -p /tmp/doctor-json",
        )
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin -t codex -o /tmp/doctor-json",
        )
        assert exit_code == 0, f"Conversion failed: {output}"

        # Validate with JSON output
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config doctor --target codex /tmp/doctor-json --json",
        )
        assert exit_code == 0, f"Doctor validation failed: {output}"
        # Should be valid JSON
        assert '"reports"' in output or '"results"' in output

    def test_doctor_target_invalid_output_fails(self, claude_container: Container) -> None:
        """Test doctor fails on invalid converted output."""
        # Create a broken Codex output directory
        exit_code, _ = exec_in_container(
            claude_container,
            "rm -rf /tmp/doctor-broken && mkdir -p /tmp/doctor-broken/.codex/skills/broken-skill",
        )
        # Create skill directory without SKILL.md
        assert exit_code == 0

        # Doctor should fail
        exit_code, output = exec_in_container(
            claude_container,
            "uv run ai-config doctor --target codex /tmp/doctor-broken",
        )
        assert exit_code == 1, f"Doctor should fail on invalid output: {output}"
        # Should mention the missing SKILL.md
        assert "SKILL.md" in output or "fail" in output.lower()
