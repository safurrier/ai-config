"""Integration smoke test — replaces validate_integration.sh.

Covers the full ai-config workflow in a single class:
  1. Preflight: CLI is functional
  2. Conversion: Convert complete-plugin to each target
  3. File verification: Assert expected output files exist
  4. Sync: Write config, sync, verify via claude plugin commands
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from tests.e2e.conftest import exec_in_container

if TYPE_CHECKING:
    from docker.models.containers import Container


@pytest.mark.e2e
@pytest.mark.docker
class TestIntegrationSmoke:
    """Integration smoke test — replaces validate_integration.sh."""

    def test_preflight(self, claude_container: Container) -> None:
        """ai-config CLI is functional."""
        exit_code, output = exec_in_container(claude_container, "uv run ai-config --version")
        assert exit_code == 0, f"ai-config not working: {output}"
        assert "ai-config" in output

    def test_convert_all_targets(self, claude_container: Container) -> None:
        """Convert complete-plugin to codex, cursor, opencode."""
        for target in ("codex", "cursor", "opencode"):
            exit_code, output = exec_in_container(
                claude_container,
                f"uv run ai-config convert tests/fixtures/sample-plugins/complete-plugin "
                f"-t {target} -o /tmp/smoke-{target}",
            )
            assert exit_code == 0, f"convert to {target} failed: {output}"

    def test_converted_files_exist(self, claude_container: Container) -> None:
        """Verify key output files from conversion."""
        checks = [
            # Codex
            ("test -d /tmp/smoke-codex/.codex/skills", "Codex skills dir"),
            ("ls /tmp/smoke-codex/.codex/skills/*/SKILL.md", "Codex SKILL.md"),
            # Cursor
            ("test -d /tmp/smoke-cursor/.cursor/skills", "Cursor skills dir"),
            ("ls /tmp/smoke-cursor/.cursor/skills/*/SKILL.md", "Cursor SKILL.md"),
            ("test -f /tmp/smoke-cursor/.cursor/mcp.json", "Cursor mcp.json"),
            ("test -f /tmp/smoke-cursor/.cursor/hooks.json", "Cursor hooks.json"),
            # OpenCode
            ("test -d /tmp/smoke-opencode/.opencode/skills", "OpenCode skills dir"),
            ("ls /tmp/smoke-opencode/.opencode/skills/*/SKILL.md", "OpenCode SKILL.md"),
            ("test -f /tmp/smoke-opencode/opencode.json", "OpenCode MCP config"),
            ("test -f /tmp/smoke-opencode/opencode.lsp.json", "OpenCode LSP config"),
        ]
        for cmd, label in checks:
            exit_code, _ = exec_in_container(claude_container, cmd)
            assert exit_code == 0, f"{label} missing"

    def test_sync_and_verify(self, claude_container: Container) -> None:
        """Write config, sync, verify marketplace + plugin in Claude."""
        # Use absolute path — config lives in ~/.ai-config/ so relative paths
        # would resolve against /home/testuser instead of the repo checkout.
        repo = "/home/testuser/ai-config"
        config = textwrap.dedent(f"""\
            version: 1
            targets:
              - type: claude
                config:
                  marketplaces:
                    test-marketplace:
                      source: local
                      path: {repo}/tests/fixtures/test-marketplace
                  plugins:
                    - id: test-plugin@test-marketplace
                      scope: user
                      enabled: true
        """)
        # Write config
        exit_code, output = exec_in_container(
            claude_container,
            f"mkdir -p ~/.ai-config && cat > ~/.ai-config/config.yaml << 'EOF'\n{config}EOF",
        )
        assert exit_code == 0, f"Failed to write config: {output}"

        # Sync
        exit_code, output = exec_in_container(claude_container, "uv run ai-config sync")
        assert exit_code == 0, f"sync failed: {output}"
        assert "Failed" not in output

        # Verify marketplace
        exit_code, output = exec_in_container(
            claude_container,
            "claude plugin marketplace list --json",
        )
        assert exit_code == 0, f"claude plugin marketplace list failed: {output}"
        assert "test-marketplace" in output

        # Verify plugin
        exit_code, output = exec_in_container(
            claude_container,
            "claude plugin list --json",
        )
        assert exit_code == 0, f"claude plugin list failed: {output}"
        assert "test-plugin" in output
