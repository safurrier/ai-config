"""Tests for ai_config.cli module."""

from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ai_config.adapters.claude import CommandResult
from ai_config.cli import main
from ai_config.converters.ir import PluginIdentity, TargetTool
from ai_config.converters.report import ConversionReport
from ai_config.types import PluginStatus, StatusResult, SyncAction, SyncResult


@pytest.fixture
def runner() -> CliRunner:
    """Click test runner."""
    return CliRunner()


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Create a sample config file."""
    config = tmp_path / "config.yaml"
    config.write_text(
        dedent("""
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
                  enabled: true
        """)
    )
    return config


@pytest.fixture
def minimal_plugin(tmp_path: Path) -> Path:
    """Create a minimal plugin directory for convert command tests."""
    plugin_dir = tmp_path / "plugin"
    (plugin_dir / ".claude-plugin").mkdir(parents=True)
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        '{"name": "test-plugin", "version": "1.0.0"}'
    )
    return plugin_dir


def _stub_report(target: TargetTool) -> ConversionReport:
    """Create a minimal conversion report for CLI tests."""
    identity = PluginIdentity(plugin_id="test-plugin", name="test-plugin", version="1.0.0")
    return ConversionReport(source_plugin=identity, target_tool=target)


class TestMainGroup:
    """Tests for main CLI group."""

    def test_version(self, runner: CliRunner) -> None:
        """Shows version info."""
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.4.2" in result.output

    def test_help(self, runner: CliRunner) -> None:
        """Shows help text."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "ai-config" in result.output


class TestSyncCommand:
    """Tests for sync command."""

    def test_sync_dry_run(self, runner: CliRunner, config_file: Path) -> None:
        """Dry run shows planned actions without changes."""
        sync_result = SyncResult()
        sync_result.add_success(
            SyncAction(action="install", target="my-plugin@my-marketplace", scope="user")
        )

        with patch("ai_config.cli.sync_config", return_value={"claude": sync_result}):
            result = runner.invoke(main, ["sync", "-c", str(config_file), "--dry-run"])

            assert result.exit_code == 0
            assert "Dry run mode" in result.output
            assert "install" in result.output

    def test_sync_with_errors(self, runner: CliRunner, config_file: Path) -> None:
        """Shows errors from sync."""
        sync_result = SyncResult(success=False, errors=["Something went wrong"])

        with patch("ai_config.cli.sync_config", return_value={"claude": sync_result}):
            result = runner.invoke(main, ["sync", "-c", str(config_file)])

            assert "Something went wrong" in result.output

    def test_sync_force_convert_flag(self, runner: CliRunner, config_file: Path) -> None:
        """Force-convert flag is passed through to sync_config."""
        sync_result = SyncResult()

        with patch("ai_config.cli.sync_config", return_value={"claude": sync_result}) as mock_sync:
            result = runner.invoke(
                main,
                ["sync", "-c", str(config_file), "--force-convert"],
            )

            assert result.exit_code == 0
            assert mock_sync.called
            kwargs = mock_sync.call_args.kwargs
            assert kwargs["force_convert"] is True

    def test_sync_config_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """Handles config loading errors."""
        invalid_config = tmp_path / "invalid.yaml"
        invalid_config.write_text("version: 2")  # Invalid version

        result = runner.invoke(main, ["sync", "-c", str(invalid_config)])

        assert result.exit_code == 1
        assert "Error loading config" in result.output


class TestStatusCommand:
    """Tests for status command."""

    def test_status_table_output(self, runner: CliRunner) -> None:
        """Shows status as table."""
        status_result = StatusResult(target_type="claude")
        status_result.plugins = [
            PluginStatus(
                id="my-plugin@mp",
                installed=True,
                enabled=True,
                scope="user",
                version="1.0.0",
            )
        ]
        status_result.marketplaces = ["my-marketplace"]

        with patch("ai_config.cli.get_status", return_value=status_result):
            result = runner.invoke(main, ["status"])

            assert result.exit_code == 0
            assert "my-plugin@mp" in result.output
            assert "my-marketplace" in result.output

    def test_status_json_output(self, runner: CliRunner) -> None:
        """Shows status as JSON."""
        status_result = StatusResult(target_type="claude")
        status_result.plugins = [
            PluginStatus(
                id="my-plugin",
                installed=True,
                enabled=True,
                scope="user",
                version="1.0.0",
            )
        ]

        with patch("ai_config.cli.get_status", return_value=status_result):
            result = runner.invoke(main, ["status", "--json"])

            assert result.exit_code == 0
            assert '"id": "my-plugin"' in result.output

    def test_status_no_plugins(self, runner: CliRunner) -> None:
        """Shows message when no plugins installed."""
        status_result = StatusResult(target_type="claude")

        with patch("ai_config.cli.get_status", return_value=status_result):
            result = runner.invoke(main, ["status"])

            assert result.exit_code == 0
            assert "No plugins installed" in result.output


class TestUpdateCommand:
    """Tests for update command."""

    def test_update_requires_plugins_or_all(self, runner: CliRunner) -> None:
        """Update requires plugins or --all flag."""
        result = runner.invoke(main, ["update"])

        assert result.exit_code == 1
        assert "Specify plugins" in result.output

    def test_update_all(self, runner: CliRunner) -> None:
        """Updates all plugins with --all."""
        update_result = SyncResult()
        update_result.add_success(SyncAction(action="install", target="plugin1"))

        with patch("ai_config.cli.update_plugins", return_value=update_result):
            result = runner.invoke(main, ["update", "--all"])

            assert result.exit_code == 0
            assert "plugin1" in result.output

    def test_update_specific(self, runner: CliRunner) -> None:
        """Updates specific plugins."""
        update_result = SyncResult()

        with patch("ai_config.cli.update_plugins", return_value=update_result) as mock_update:
            runner.invoke(main, ["update", "plugin1", "plugin2"])

            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert call_args[1]["plugin_ids"] == ["plugin1", "plugin2"]


class TestConvertCommand:
    """Tests for convert command."""

    def test_convert_scope_user_sets_output_dir(
        self, runner: CliRunner, minimal_plugin: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Scope user should map output_dir to home when --output not provided."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with patch(
            "ai_config.converters.convert_plugin",
            return_value={TargetTool.CODEX: _stub_report(TargetTool.CODEX)},
        ) as mock_convert:
            result = runner.invoke(
                main,
                ["convert", str(minimal_plugin), "--target", "codex", "--scope", "user"],
            )

        assert result.exit_code == 0
        call_args = mock_convert.call_args.kwargs
        assert call_args["output_dir"] == Path(tmp_path / "home")

    def test_convert_writes_report_file(
        self, runner: CliRunner, minimal_plugin: Path, tmp_path: Path
    ) -> None:
        """Convert with --report should write report to disk."""
        report_path = tmp_path / "report.json"

        with patch(
            "ai_config.converters.convert_plugin",
            return_value={TargetTool.CODEX: _stub_report(TargetTool.CODEX)},
        ):
            result = runner.invoke(
                main,
                [
                    "convert",
                    str(minimal_plugin),
                    "--target",
                    "codex",
                    "--report",
                    str(report_path),
                    "--report-format",
                    "json",
                ],
            )

        assert result.exit_code == 0
        assert report_path.exists()
        assert '"target_tool": "codex"' in report_path.read_text()


class TestCacheCommand:
    """Tests for cache commands."""

    def test_cache_clear_success(self, runner: CliRunner) -> None:
        """Clears cache successfully."""
        with patch(
            "ai_config.adapters.claude.clear_cache",
            return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
        ):
            result = runner.invoke(main, ["cache", "clear"])

            assert result.exit_code == 0
            assert "cleared successfully" in result.output

    def test_cache_clear_failure(self, runner: CliRunner) -> None:
        """Handles cache clear failure."""
        with patch(
            "ai_config.adapters.claude.clear_cache",
            return_value=CommandResult(
                success=False, stdout="", stderr="Permission denied", returncode=1
            ),
        ):
            result = runner.invoke(main, ["cache", "clear"])

            assert result.exit_code == 1
            assert "Permission denied" in result.output


class TestPluginCommand:
    """Tests for plugin commands."""

    def test_plugin_create(self, runner: CliRunner, tmp_path: Path) -> None:
        """Creates plugin scaffold."""
        result = runner.invoke(main, ["plugin", "create", "test-plugin", "--path", str(tmp_path)])

        assert result.exit_code == 0
        assert "Created plugin scaffold" in result.output
        assert (tmp_path / "test-plugin" / "manifest.yaml").exists()
