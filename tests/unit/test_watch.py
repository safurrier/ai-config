"""Tests for ai_config.watch module."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    MarketplaceConfig,
    PluginSource,
    TargetConfig,
)
from ai_config.watch import (
    ChangeCollector,
    FileChange,
    WatchConfig,
    collect_watch_paths,
)


@pytest.fixture
def sample_config_with_local_marketplace(tmp_path: Path) -> AIConfig:
    """Config with a local marketplace pointing to a directory."""
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()

    return AIConfig(
        version=1,
        targets=(
            TargetConfig(
                type="claude",
                config=ClaudeTargetConfig(
                    marketplaces={
                        "local-marketplace": MarketplaceConfig(
                            source=PluginSource.LOCAL,
                            path=str(plugin_dir),
                        ),
                    },
                    plugins=(),
                ),
            ),
        ),
    )


@pytest.fixture
def sample_config_with_github_marketplace() -> AIConfig:
    """Config with only GitHub marketplaces (no local paths to watch)."""
    return AIConfig(
        version=1,
        targets=(
            TargetConfig(
                type="claude",
                config=ClaudeTargetConfig(
                    marketplaces={
                        "github-marketplace": MarketplaceConfig(
                            source=PluginSource.GITHUB,
                            repo="owner/repo",
                        ),
                    },
                    plugins=(),
                ),
            ),
        ),
    )


@pytest.fixture
def sample_config_mixed(tmp_path: Path) -> AIConfig:
    """Config with both local and GitHub marketplaces."""
    plugin_dir1 = tmp_path / "plugin1"
    plugin_dir1.mkdir()
    plugin_dir2 = tmp_path / "plugin2"
    plugin_dir2.mkdir()

    return AIConfig(
        version=1,
        targets=(
            TargetConfig(
                type="claude",
                config=ClaudeTargetConfig(
                    marketplaces={
                        "local-mp1": MarketplaceConfig(
                            source=PluginSource.LOCAL,
                            path=str(plugin_dir1),
                        ),
                        "local-mp2": MarketplaceConfig(
                            source=PluginSource.LOCAL,
                            path=str(plugin_dir2),
                        ),
                        "github-mp": MarketplaceConfig(
                            source=PluginSource.GITHUB,
                            repo="owner/repo",
                        ),
                    },
                    plugins=(),
                ),
            ),
        ),
    )


class TestWatchConfig:
    """Tests for WatchConfig dataclass."""

    def test_default_debounce(self, tmp_path: Path) -> None:
        """Default debounce is 1.5 seconds."""
        config = WatchConfig(config_path=tmp_path / "config.yaml", plugin_directories=[])
        assert config.debounce_seconds == 1.5

    def test_custom_debounce(self, tmp_path: Path) -> None:
        """Can override debounce seconds."""
        config = WatchConfig(
            config_path=tmp_path / "config.yaml",
            plugin_directories=[],
            debounce_seconds=3.0,
        )
        assert config.debounce_seconds == 3.0


class TestCollectWatchPaths:
    """Tests for collect_watch_paths function."""

    def test_extracts_local_plugin_directory(
        self, sample_config_with_local_marketplace: AIConfig, tmp_path: Path
    ) -> None:
        """Extracts local marketplace paths as watch directories."""
        config_path = tmp_path / ".ai-config" / "config.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.touch()

        watch_config = collect_watch_paths(sample_config_with_local_marketplace, config_path)

        assert watch_config.config_path == config_path
        assert len(watch_config.plugin_directories) == 1
        assert str(watch_config.plugin_directories[0]).endswith("my-plugin")

    def test_ignores_github_marketplaces(
        self, sample_config_with_github_marketplace: AIConfig, tmp_path: Path
    ) -> None:
        """GitHub marketplaces don't add watch paths."""
        config_path = tmp_path / "config.yaml"
        config_path.touch()

        watch_config = collect_watch_paths(sample_config_with_github_marketplace, config_path)

        assert watch_config.config_path == config_path
        assert len(watch_config.plugin_directories) == 0

    def test_extracts_multiple_local_paths(
        self, sample_config_mixed: AIConfig, tmp_path: Path
    ) -> None:
        """Extracts all local marketplace paths, ignoring GitHub."""
        config_path = tmp_path / "config.yaml"
        config_path.touch()

        watch_config = collect_watch_paths(sample_config_mixed, config_path)

        # Should have 2 local dirs, not 3 (GitHub ignored)
        assert len(watch_config.plugin_directories) == 2


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_config_change(self) -> None:
        """FileChange for config file."""
        change = FileChange(
            path=Path("/path/to/config.yaml"),
            change_type="config",
            event_type="modified",
        )
        assert change.change_type == "config"
        assert change.event_type == "modified"

    def test_plugin_change(self) -> None:
        """FileChange for plugin directory."""
        change = FileChange(
            path=Path("/path/to/plugin/skill.md"),
            change_type="plugin_directory",
            event_type="created",
        )
        assert change.change_type == "plugin_directory"
        assert change.event_type == "created"


class TestChangeCollector:
    """Tests for ChangeCollector class."""

    @pytest.fixture
    def collector(self, tmp_path: Path) -> ChangeCollector:
        """Create a ChangeCollector for testing."""
        config_path = tmp_path / ".ai-config" / "config.yaml"
        config_path.parent.mkdir(parents=True)
        config_path.touch()

        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()

        return ChangeCollector(
            config_path=config_path,
            plugin_directories=[plugin_dir],
            debounce_seconds=0.1,  # Short for testing
            on_changes=MagicMock(),
        )

    def test_classifies_config_change(self, collector: ChangeCollector, tmp_path: Path) -> None:
        """Config file changes are classified as 'config'."""
        config_path = tmp_path / ".ai-config" / "config.yaml"

        # Simulate a modification event
        event = MagicMock()
        event.src_path = str(config_path)
        event.is_directory = False
        event.event_type = "modified"

        collector.on_modified(event)

        # Check pending changes
        assert len(collector._pending_changes) == 1
        change = list(collector._pending_changes.values())[0]
        assert change.change_type == "config"

    def test_classifies_plugin_change(self, collector: ChangeCollector, tmp_path: Path) -> None:
        """Plugin directory changes are classified as 'plugin_directory'."""
        plugin_file = tmp_path / "my-plugin" / "skill.md"

        event = MagicMock()
        event.src_path = str(plugin_file)
        event.is_directory = False
        event.event_type = "created"

        collector.on_created(event)

        assert len(collector._pending_changes) == 1
        change = list(collector._pending_changes.values())[0]
        assert change.change_type == "plugin_directory"

    def test_ignores_swap_files(self, collector: ChangeCollector, tmp_path: Path) -> None:
        """Vim swap files are ignored."""
        swap_file = tmp_path / "my-plugin" / ".skill.md.swp"

        event = MagicMock()
        event.src_path = str(swap_file)
        event.is_directory = False
        event.event_type = "modified"

        collector.on_modified(event)

        assert len(collector._pending_changes) == 0

    def test_ignores_tilde_backup_files(self, collector: ChangeCollector, tmp_path: Path) -> None:
        """Backup files ending with ~ are ignored."""
        backup_file = tmp_path / "my-plugin" / "skill.md~"

        event = MagicMock()
        event.src_path = str(backup_file)
        event.is_directory = False
        event.event_type = "modified"

        collector.on_modified(event)

        assert len(collector._pending_changes) == 0

    def test_ignores_git_directory(self, collector: ChangeCollector, tmp_path: Path) -> None:
        """Files in .git directory are ignored."""
        git_file = tmp_path / "my-plugin" / ".git" / "index"

        event = MagicMock()
        event.src_path = str(git_file)
        event.is_directory = False
        event.event_type = "modified"

        collector.on_modified(event)

        assert len(collector._pending_changes) == 0

    def test_ignores_pycache(self, collector: ChangeCollector, tmp_path: Path) -> None:
        """Files in __pycache__ directory are ignored."""
        cache_file = tmp_path / "my-plugin" / "__pycache__" / "module.pyc"

        event = MagicMock()
        event.src_path = str(cache_file)
        event.is_directory = False
        event.event_type = "modified"

        collector.on_modified(event)

        assert len(collector._pending_changes) == 0

    def test_debounces_rapid_changes(self, collector: ChangeCollector, tmp_path: Path) -> None:
        """Multiple changes within debounce window are batched."""
        plugin_file1 = tmp_path / "my-plugin" / "skill1.md"
        plugin_file2 = tmp_path / "my-plugin" / "skill2.md"

        event1 = MagicMock()
        event1.src_path = str(plugin_file1)
        event1.is_directory = False
        event1.event_type = "modified"

        event2 = MagicMock()
        event2.src_path = str(plugin_file2)
        event2.is_directory = False
        event2.event_type = "modified"

        # Fire both events rapidly
        collector.on_modified(event1)
        collector.on_modified(event2)

        # Both should be pending
        assert len(collector._pending_changes) == 2

        # Debounce timer should be active (only one timer)
        assert collector._debounce_timer is not None

    def test_same_file_multiple_events_deduplicated(
        self, collector: ChangeCollector, tmp_path: Path
    ) -> None:
        """Multiple events for same file result in one change."""
        plugin_file = tmp_path / "my-plugin" / "skill.md"

        event = MagicMock()
        event.src_path = str(plugin_file)
        event.is_directory = False
        event.event_type = "modified"

        # Fire same event multiple times
        collector.on_modified(event)
        collector.on_modified(event)
        collector.on_modified(event)

        # Should only have one entry
        assert len(collector._pending_changes) == 1

    def test_callback_receives_changes(self, tmp_path: Path) -> None:
        """Callback is called with collected changes after debounce."""
        config_path = tmp_path / "config.yaml"
        config_path.touch()

        callback = MagicMock()
        collector = ChangeCollector(
            config_path=config_path,
            plugin_directories=[],
            debounce_seconds=0.01,  # Very short
            on_changes=callback,
        )

        event = MagicMock()
        event.src_path = str(config_path)
        event.is_directory = False
        event.event_type = "modified"

        collector.on_modified(event)

        # Wait for debounce
        import time

        time.sleep(0.05)

        # Callback should have been called
        assert callback.called
        changes = callback.call_args[0][0]
        assert len(changes) == 1
        assert changes[0].change_type == "config"

    def test_clear_pending_after_callback(self, tmp_path: Path) -> None:
        """Pending changes are cleared after callback."""
        config_path = tmp_path / "config.yaml"
        config_path.touch()

        callback = MagicMock()
        collector = ChangeCollector(
            config_path=config_path,
            plugin_directories=[],
            debounce_seconds=0.01,
            on_changes=callback,
        )

        event = MagicMock()
        event.src_path = str(config_path)
        event.is_directory = False
        event.event_type = "modified"

        collector.on_modified(event)

        import time

        time.sleep(0.05)

        # Pending should be cleared
        assert len(collector._pending_changes) == 0

    def test_ignores_directory_events(self, collector: ChangeCollector, tmp_path: Path) -> None:
        """Directory events themselves are ignored (we watch files inside)."""
        event = MagicMock()
        event.src_path = str(tmp_path / "my-plugin")
        event.is_directory = True
        event.event_type = "modified"

        collector.on_modified(event)

        assert len(collector._pending_changes) == 0
