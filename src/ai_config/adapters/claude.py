"""Claude Code adapter for ai-config.

This module shells out to the `claude` CLI to manage plugins and marketplaces.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ai_config.types import PluginSource


@dataclass
class InstalledPlugin:
    """Information about an installed Claude Code plugin."""

    id: str
    version: str
    scope: Literal["user", "project", "local"]
    enabled: bool
    install_path: str


@dataclass
class InstalledMarketplace:
    """Information about an installed Claude Code marketplace."""

    name: str
    source: PluginSource
    repo: str
    install_location: str


@dataclass
class CommandResult:
    """Result of a CLI command execution."""

    success: bool
    stdout: str
    stderr: str
    returncode: int


def _run_claude_command(args: list[str], timeout: int = 60) -> CommandResult:
    """Run a claude CLI command and return the result.

    Args:
        args: Command arguments (without 'claude' prefix).
        timeout: Timeout in seconds.

    Returns:
        CommandResult with output and status.
    """
    cmd = ["claude"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            success=False,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            returncode=-1,
        )
    except FileNotFoundError:
        return CommandResult(
            success=False,
            stdout="",
            stderr="claude CLI not found. Is Claude Code installed?",
            returncode=-1,
        )


def list_installed_plugins() -> tuple[list[InstalledPlugin], list[str]]:
    """List all installed plugins.

    Returns:
        Tuple of (plugins, errors). Plugins list may be empty on error.
    """
    result = _run_claude_command(["plugin", "list", "--json"])

    if not result.success:
        return [], [f"Failed to list plugins: {result.stderr}"]

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return [], [f"Failed to parse plugin list JSON: {e}"]

    plugins: list[InstalledPlugin] = []
    for item in data:
        plugins.append(
            InstalledPlugin(
                id=item.get("id", ""),
                version=item.get("version", ""),
                scope=item.get("scope", "user"),
                enabled=item.get("enabled", True),
                install_path=item.get("installPath", ""),
            )
        )

    return plugins, []


def list_installed_marketplaces() -> tuple[list[InstalledMarketplace], list[str]]:
    """List all installed marketplaces.

    Returns:
        Tuple of (marketplaces, errors). Marketplaces list may be empty on error.
    """
    result = _run_claude_command(["plugin", "marketplace", "list", "--json"])

    if not result.success:
        return [], [f"Failed to list marketplaces: {result.stderr}"]

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return [], [f"Failed to parse marketplace list JSON: {e}"]

    marketplaces: list[InstalledMarketplace] = []
    for item in data:
        source_str = item.get("source", "github")
        # Claude CLI returns "directory" for local marketplaces, map to LOCAL
        if source_str == "directory":
            source = PluginSource.LOCAL
        else:
            try:
                source = PluginSource(source_str)
            except ValueError:
                source = PluginSource.GITHUB  # Default to github if unknown
        marketplaces.append(
            InstalledMarketplace(
                name=item.get("name", ""),
                source=source,
                repo=item.get("repo", item.get("path", "")),  # Use path for local
                install_location=item.get("installLocation", ""),
            )
        )

    return marketplaces, []


def install_plugin(
    plugin_id: str, scope: Literal["user", "project", "local"] = "user"
) -> CommandResult:
    """Install a plugin from a marketplace.

    Args:
        plugin_id: Plugin ID, optionally with @marketplace suffix.
        scope: Installation scope (user, project, or local).

    Returns:
        CommandResult from the install command.
    """
    return _run_claude_command(["plugin", "install", plugin_id, "--scope", scope])


def uninstall_plugin(plugin_id: str) -> CommandResult:
    """Uninstall a plugin.

    Args:
        plugin_id: Plugin ID to uninstall.

    Returns:
        CommandResult from the uninstall command.
    """
    return _run_claude_command(["plugin", "uninstall", plugin_id])


def enable_plugin(plugin_id: str) -> CommandResult:
    """Enable a disabled plugin.

    Args:
        plugin_id: Plugin ID to enable.

    Returns:
        CommandResult from the enable command.
    """
    return _run_claude_command(["plugin", "enable", plugin_id])


def disable_plugin(plugin_id: str) -> CommandResult:
    """Disable an enabled plugin.

    Args:
        plugin_id: Plugin ID to disable.

    Returns:
        CommandResult from the disable command.
    """
    return _run_claude_command(["plugin", "disable", plugin_id])


def update_plugin(plugin_id: str) -> CommandResult:
    """Update a plugin to the latest version.

    Args:
        plugin_id: Plugin ID to update.

    Returns:
        CommandResult from the update command.
    """
    return _run_claude_command(["plugin", "update", plugin_id])


def add_marketplace(
    repo: str | None = None,
    name: str | None = None,  # Note: --name flag not supported by Claude CLI, kept for API compat
    path: str | None = None,
) -> CommandResult:
    """Add a marketplace from a GitHub repo or local path.

    Args:
        repo: GitHub repo in owner/repo format (for github source).
        name: Ignored. Marketplace name comes from marketplace.json.
        path: Local filesystem path (for local source).

    Returns:
        CommandResult from the add command.
    """
    # Note: The name parameter is accepted but not used - Claude CLI doesn't support
    # custom naming. The marketplace name comes from the marketplace.json file.
    _ = name  # Unused, kept for backward compatibility

    if path:
        # Local marketplace: claude plugin marketplace add <path>
        args = ["plugin", "marketplace", "add", path]
    elif repo:
        # GitHub marketplace: claude plugin marketplace add <repo>
        args = ["plugin", "marketplace", "add", repo]
    else:
        return CommandResult(
            success=False,
            stdout="",
            stderr="Either repo or path must be provided",
            returncode=1,
        )

    return _run_claude_command(args)


def remove_marketplace(name: str) -> CommandResult:
    """Remove a marketplace.

    Args:
        name: Marketplace name to remove.

    Returns:
        CommandResult from the remove command.
    """
    return _run_claude_command(["plugin", "marketplace", "remove", name])


def update_marketplace(name: str | None = None) -> CommandResult:
    """Update marketplace(s) from their source.

    Args:
        name: Specific marketplace to update, or None to update all.

    Returns:
        CommandResult from the update command.
    """
    args = ["plugin", "marketplace", "update"]
    if name:
        args.append(name)
    return _run_claude_command(args)


def clear_cache() -> CommandResult:
    """Clear the plugin cache by removing the cache directory.

    Returns:
        CommandResult indicating success or failure.
    """
    cache_dir = Path.home() / ".claude" / "plugins" / "cache"
    if not cache_dir.exists():
        return CommandResult(
            success=True,
            stdout="Cache directory does not exist",
            stderr="",
            returncode=0,
        )

    import shutil

    try:
        shutil.rmtree(cache_dir)
        return CommandResult(
            success=True,
            stdout=f"Removed cache directory: {cache_dir}",
            stderr="",
            returncode=0,
        )
    except OSError as e:
        return CommandResult(
            success=False,
            stdout="",
            stderr=f"Failed to remove cache directory: {e}",
            returncode=1,
        )


def get_plugin_by_id(plugin_id: str) -> tuple[InstalledPlugin | None, list[str]]:
    """Get a specific installed plugin by ID.

    Args:
        plugin_id: Plugin ID to find.

    Returns:
        Tuple of (plugin or None, errors).
    """
    plugins, errors = list_installed_plugins()
    if errors:
        return None, errors

    for plugin in plugins:
        if plugin.id == plugin_id:
            return plugin, []

    return None, []


def get_marketplace_by_name(name: str) -> tuple[InstalledMarketplace | None, list[str]]:
    """Get a specific installed marketplace by name.

    Args:
        name: Marketplace name to find.

    Returns:
        Tuple of (marketplace or None, errors).
    """
    marketplaces, errors = list_installed_marketplaces()
    if errors:
        return None, errors

    for mp in marketplaces:
        if mp.name == name:
            return mp, []

    return None, []
