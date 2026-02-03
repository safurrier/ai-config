"""File watching for auto-sync on changes."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Timer
from typing import Literal

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ai_config.types import AIConfig, PluginSource


@dataclass
class FileChange:
    """Represents a detected file change."""

    path: Path
    change_type: Literal["config", "plugin_directory"]
    event_type: str  # "created", "modified", "deleted"


@dataclass
class WatchConfig:
    """Configuration for file watching."""

    config_path: Path
    plugin_directories: list[Path]
    debounce_seconds: float = 1.5


# Patterns to ignore when watching files
IGNORE_PATTERNS = frozenset(
    {
        ".swp",  # Vim swap files
        ".swo",  # Vim swap overflow
        ".swn",  # Vim swap
        "~",  # Backup files
        ".tmp",  # Temp files
        ".bak",  # Backup files
    }
)

IGNORE_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        ".venv",
        "venv",
    }
)


def collect_watch_paths(config: AIConfig, config_path: Path) -> WatchConfig:
    """Extract paths to watch from config.

    Args:
        config: The loaded AIConfig.
        config_path: Path to the config file itself.

    Returns:
        WatchConfig with paths to monitor.
    """
    plugin_directories: list[Path] = []

    for target in config.targets:
        if target.type == "claude":
            for marketplace in target.config.marketplaces.values():
                if marketplace.source == PluginSource.LOCAL:
                    plugin_directories.append(Path(marketplace.path))

    return WatchConfig(
        config_path=config_path,
        plugin_directories=plugin_directories,
    )


def _should_ignore_path(path: Path) -> bool:
    """Check if a path should be ignored.

    Args:
        path: Path to check.

    Returns:
        True if the path should be ignored.
    """
    # Check file suffixes/patterns
    name = path.name
    for pattern in IGNORE_PATTERNS:
        if name.endswith(pattern):
            return True

    # Check for hidden files starting with .
    if name.startswith(".") and not name.startswith(".."):
        # Allow normal dotfiles but check for swap pattern
        if name.endswith(".swp") or name.endswith(".swo"):
            return True

    # Check if any parent is an ignored directory
    for part in path.parts:
        if part in IGNORE_DIRS:
            return True

    return False


class ChangeCollector(FileSystemEventHandler):
    """Collects file changes and debounces callback invocation."""

    def __init__(
        self,
        config_path: Path,
        plugin_directories: list[Path],
        debounce_seconds: float,
        on_changes: Callable[[list[FileChange]], None],
    ) -> None:
        """Initialize the collector.

        Args:
            config_path: Path to the config file.
            plugin_directories: List of plugin directories to monitor.
            debounce_seconds: Seconds to wait before firing callback.
            on_changes: Callback to invoke with collected changes.
        """
        super().__init__()
        self._config_path = config_path.resolve()
        self._plugin_directories = [d.resolve() for d in plugin_directories]
        self._debounce_seconds = debounce_seconds
        self._on_changes = on_changes
        self._pending_changes: dict[Path, FileChange] = {}
        self._debounce_timer: Timer | None = None

    def _classify_change(self, path: Path) -> Literal["config", "plugin_directory"] | None:
        """Classify a file change by type.

        Args:
            path: Path of the changed file.

        Returns:
            Change type or None if not a watched path.
        """
        resolved = path.resolve()

        if resolved == self._config_path:
            return "config"

        for plugin_dir in self._plugin_directories:
            try:
                resolved.relative_to(plugin_dir)
                return "plugin_directory"
            except ValueError:
                continue

        return None

    def _handle_event(self, event: FileSystemEvent) -> None:
        """Handle a file system event.

        Args:
            event: The watchdog event.
        """
        if event.is_directory:
            return

        src_path = event.src_path
        if isinstance(src_path, bytes):
            src_path = src_path.decode()
        path = Path(src_path)

        if _should_ignore_path(path):
            return

        change_type = self._classify_change(path)
        if change_type is None:
            return

        # Add to pending changes (deduplicate by path)
        self._pending_changes[path] = FileChange(
            path=path,
            change_type=change_type,
            event_type=event.event_type,
        )

        # Reset debounce timer
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()

        self._debounce_timer = Timer(self._debounce_seconds, self._fire_callback)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _fire_callback(self) -> None:
        """Fire the callback with collected changes."""
        if not self._pending_changes:
            return

        changes = list(self._pending_changes.values())
        self._pending_changes.clear()
        self._debounce_timer = None

        self._on_changes(changes)

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file created event."""
        self._handle_event(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modified event."""
        self._handle_event(event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deleted event."""
        self._handle_event(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file moved event."""
        self._handle_event(event)


@dataclass
class WatchResult:
    """Result of a watch operation."""

    config_changes: int = 0
    plugin_changes: int = 0
    errors: list[str] = field(default_factory=list)


def run_watch_loop(
    watch_config: WatchConfig,
    on_changes: Callable[[list[FileChange]], None],
    stop_event: Event,
    debounce_seconds: float = 1.5,
) -> None:
    """Run the watch loop until stop_event is set.

    Args:
        watch_config: Configuration for what to watch.
        on_changes: Callback to invoke when changes are detected.
        stop_event: Event to signal the loop should stop.
        debounce_seconds: Seconds to wait before syncing after changes.
    """
    collector = ChangeCollector(
        config_path=watch_config.config_path,
        plugin_directories=watch_config.plugin_directories,
        debounce_seconds=debounce_seconds,
        on_changes=on_changes,
    )

    observer = Observer()

    # Watch config file's directory
    if watch_config.config_path.parent.exists():
        observer.schedule(
            collector,
            str(watch_config.config_path.parent),
            recursive=False,
        )

    # Watch plugin directories recursively
    for plugin_dir in watch_config.plugin_directories:
        if plugin_dir.exists():
            observer.schedule(
                collector,
                str(plugin_dir),
                recursive=True,
            )

    observer.start()

    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=0.5)
    finally:
        observer.stop()
        observer.join()
