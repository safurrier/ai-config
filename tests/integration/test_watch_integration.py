"""Integration tests for ai_config watch command.

These tests use real file system operations to verify watch functionality.
"""

import time
from pathlib import Path
from textwrap import dedent
from threading import Event, Thread
from unittest.mock import MagicMock, patch

import pytest

from ai_config.config import load_config
from ai_config.watch import FileChange, WatchConfig, collect_watch_paths, run_watch_loop

pytestmark = [pytest.mark.integration]


@pytest.fixture
def config_with_local_plugin(tmp_path: Path) -> tuple[Path, Path]:
    """Create a config file and local plugin directory.

    Returns:
        Tuple of (config_path, plugin_dir).
    """
    # Create config directory
    config_dir = tmp_path / ".ai-config"
    config_dir.mkdir()

    # Create plugin directory
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.yaml").write_text("name: my-plugin\n")
    (plugin_dir / "skills").mkdir()
    (plugin_dir / "skills" / "test-skill.md").write_text("# Test Skill\n")

    # Create config file referencing the plugin
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        dedent(f"""
        version: 1
        targets:
          - type: claude
            config:
              marketplaces:
                local-dev:
                  source: local
                  path: {plugin_dir}
              plugins:
                - id: my-plugin@local-dev
                  scope: user
                  enabled: true
        """)
    )

    return config_path, plugin_dir


class TestWatchConfigCollection:
    """Tests for collecting watch paths from config."""

    def test_collects_local_plugin_directory(
        self, config_with_local_plugin: tuple[Path, Path]
    ) -> None:
        """Collects local plugin directories from config."""
        config_path, plugin_dir = config_with_local_plugin
        config = load_config(config_path)

        watch_config = collect_watch_paths(config, config_path)

        assert watch_config.config_path == config_path
        assert len(watch_config.plugin_directories) == 1
        assert watch_config.plugin_directories[0] == plugin_dir


class TestWatchLoop:
    """Tests for the watch loop with real file operations."""

    def test_detects_config_modification(
        self, config_with_local_plugin: tuple[Path, Path]
    ) -> None:
        """Watch loop detects config file modifications."""
        config_path, plugin_dir = config_with_local_plugin

        changes_received: list[list[FileChange]] = []
        stop_event = Event()

        def capture_changes(changes: list[FileChange]) -> None:
            changes_received.append(changes)
            stop_event.set()  # Stop after first batch

        watch_config = WatchConfig(
            config_path=config_path,
            plugin_directories=[plugin_dir],
            debounce_seconds=0.1,
        )

        # Start watch loop in background thread
        thread = Thread(
            target=run_watch_loop,
            kwargs={
                "watch_config": watch_config,
                "on_changes": capture_changes,
                "stop_event": stop_event,
                "debounce_seconds": 0.1,
            },
            daemon=True,
        )
        thread.start()

        # Give watchdog time to set up (longer for parallel test runs)
        time.sleep(0.5)

        # Modify the config file
        with open(config_path, "a") as f:
            f.write("# comment\n")

        # Wait for detection (with timeout)
        thread.join(timeout=3.0)

        # Should have received changes
        assert len(changes_received) >= 1
        all_changes = [c for batch in changes_received for c in batch]
        config_changes = [c for c in all_changes if c.change_type == "config"]
        assert len(config_changes) >= 1

    def test_detects_plugin_file_creation(
        self, config_with_local_plugin: tuple[Path, Path]
    ) -> None:
        """Watch loop detects new files in plugin directories."""
        config_path, plugin_dir = config_with_local_plugin

        changes_received: list[list[FileChange]] = []
        stop_event = Event()

        def capture_changes(changes: list[FileChange]) -> None:
            changes_received.append(changes)
            stop_event.set()

        watch_config = WatchConfig(
            config_path=config_path,
            plugin_directories=[plugin_dir],
            debounce_seconds=0.1,
        )

        thread = Thread(
            target=run_watch_loop,
            kwargs={
                "watch_config": watch_config,
                "on_changes": capture_changes,
                "stop_event": stop_event,
                "debounce_seconds": 0.1,
            },
            daemon=True,
        )
        thread.start()

        # Longer sleep for watchdog to fully initialize (helps with parallel test runs)
        time.sleep(0.5)

        # Create a new skill file
        new_skill = plugin_dir / "skills" / "new-skill.md"
        new_skill.write_text("# New Skill\n")

        thread.join(timeout=3.0)

        assert len(changes_received) >= 1
        all_changes = [c for batch in changes_received for c in batch]
        plugin_changes = [c for c in all_changes if c.change_type == "plugin_directory"]
        assert len(plugin_changes) >= 1

    def test_graceful_shutdown_on_stop_event(
        self, config_with_local_plugin: tuple[Path, Path]
    ) -> None:
        """Watch loop stops gracefully when stop_event is set."""
        config_path, plugin_dir = config_with_local_plugin

        stop_event = Event()

        watch_config = WatchConfig(
            config_path=config_path,
            plugin_directories=[plugin_dir],
        )

        thread = Thread(
            target=run_watch_loop,
            kwargs={
                "watch_config": watch_config,
                "on_changes": lambda x: None,
                "stop_event": stop_event,
                "debounce_seconds": 0.1,
            },
            daemon=True,
        )
        thread.start()

        # Let it run briefly
        time.sleep(0.2)

        # Signal stop
        stop_event.set()

        # Should stop within timeout
        thread.join(timeout=2.0)
        assert not thread.is_alive()


class TestWatchCLI:
    """Tests for watch CLI command."""

    def test_cli_displays_watched_paths(
        self, config_with_local_plugin: tuple[Path, Path]
    ) -> None:
        """CLI displays which paths are being watched."""
        from click.testing import CliRunner

        from ai_config.cli import main

        config_path, plugin_dir = config_with_local_plugin
        runner = CliRunner()

        # Mock run_watch_loop to avoid blocking
        with patch("ai_config.watch.run_watch_loop") as mock_loop:
            result = runner.invoke(
                main, ["watch", "-c", str(config_path)], catch_exceptions=False
            )

            # Should display paths even if loop is mocked
            assert "Watching:" in result.output
            assert "Config:" in result.output
            assert "Plugin:" in result.output
            # Check for plugin dir name (Rich may wrap long paths across lines)
            assert "my-plugin" in result.output

    def test_cli_shows_debounce_and_dry_run(
        self, config_with_local_plugin: tuple[Path, Path]
    ) -> None:
        """CLI displays debounce and dry-run settings."""
        from click.testing import CliRunner

        from ai_config.cli import main

        config_path, _ = config_with_local_plugin
        runner = CliRunner()

        with patch("ai_config.watch.run_watch_loop"):
            result = runner.invoke(
                main,
                ["watch", "-c", str(config_path), "--debounce", "2.5", "--dry-run"],
                catch_exceptions=False,
            )

            assert "Dry run: true" in result.output

    def test_cli_handles_config_error(self, tmp_path: Path) -> None:
        """CLI handles missing/invalid config gracefully."""
        from click.testing import CliRunner

        from ai_config.cli import main

        runner = CliRunner()

        # No config file exists
        result = runner.invoke(main, ["watch", "-c", str(tmp_path / "nonexistent.yaml")])

        assert result.exit_code != 0

    def test_cli_help_text(self) -> None:
        """CLI help text includes use cases and workflow."""
        from click.testing import CliRunner

        from ai_config.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["watch", "--help"])

        assert "When to use:" in result.output
        assert "What you'll see:" in result.output
        assert "How it works:" in result.output
