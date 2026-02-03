"""Core operations for ai-config: sync, status, update."""

from ai_config.adapters import claude
from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    PluginSource,
    PluginStatus,
    StatusResult,
    SyncAction,
    SyncResult,
    TargetConfig,
)


def _sync_marketplaces(
    config: ClaudeTargetConfig,
    dry_run: bool = False,
) -> tuple[list[SyncAction], list[str]]:
    """Sync marketplaces to match config.

    Returns:
        Tuple of (actions taken, errors).
    """
    actions: list[SyncAction] = []
    errors: list[str] = []

    # Get currently installed marketplaces
    installed_mps, mp_errors = claude.list_installed_marketplaces()
    if mp_errors:
        return [], mp_errors

    installed_names = {mp.name for mp in installed_mps}

    # Add missing marketplaces
    for name, marketplace_config in config.marketplaces.items():
        if name not in installed_names:
            if marketplace_config.source == PluginSource.LOCAL:
                source_desc = marketplace_config.path
            else:
                source_desc = marketplace_config.repo

            action = SyncAction(
                action="register_marketplace",
                target=name,
                reason=f"Add marketplace from {source_desc}",
            )

            if not dry_run:
                is_github = marketplace_config.source == PluginSource.GITHUB
                repo = marketplace_config.repo if is_github else None
                path = marketplace_config.path if not is_github else None
                result = claude.add_marketplace(repo=repo, name=name, path=path)
                if not result.success:
                    errors.append(f"Failed to add marketplace '{name}': {result.stderr}")
                    continue

            actions.append(action)

    return actions, errors


def _sync_plugins(
    config: ClaudeTargetConfig,
    dry_run: bool = False,
) -> tuple[list[SyncAction], list[str]]:
    """Sync plugins to match config.

    Returns:
        Tuple of (actions taken, errors).
    """
    actions: list[SyncAction] = []
    errors: list[str] = []

    # Get currently installed plugins
    installed_plugins, plugin_errors = claude.list_installed_plugins()
    if plugin_errors:
        return [], plugin_errors

    installed_by_id = {p.id: p for p in installed_plugins}

    # Process each plugin in config
    for plugin_config in config.plugins:
        plugin_id = plugin_config.id
        installed = installed_by_id.get(plugin_id)

        if installed is None:
            # Plugin not installed - install it
            if plugin_config.enabled:
                action = SyncAction(
                    action="install",
                    target=plugin_id,
                    scope=plugin_config.scope,
                    reason="Plugin not installed",
                )

                if not dry_run:
                    result = claude.install_plugin(plugin_id, plugin_config.scope)
                    if not result.success:
                        errors.append(f"Failed to install '{plugin_id}': {result.stderr}")
                        continue

                actions.append(action)
        else:
            # Plugin installed - check enabled state
            if plugin_config.enabled and not installed.enabled:
                action = SyncAction(
                    action="enable",
                    target=plugin_id,
                    reason="Plugin should be enabled",
                )

                if not dry_run:
                    result = claude.enable_plugin(plugin_id)
                    if not result.success:
                        errors.append(f"Failed to enable '{plugin_id}': {result.stderr}")
                        continue

                actions.append(action)

            elif not plugin_config.enabled and installed.enabled:
                action = SyncAction(
                    action="disable",
                    target=plugin_id,
                    reason="Plugin should be disabled",
                )

                if not dry_run:
                    result = claude.disable_plugin(plugin_id)
                    if not result.success:
                        errors.append(f"Failed to disable '{plugin_id}': {result.stderr}")
                        continue

                actions.append(action)

    return actions, errors


def sync_target(
    target: TargetConfig,
    dry_run: bool = False,
    fresh: bool = False,
) -> SyncResult:
    """Sync a target to match its config.

    Args:
        target: Target configuration to sync.
        dry_run: If True, only report what would be done.
        fresh: If True, clear cache before syncing.

    Returns:
        SyncResult with actions taken and any errors.
    """
    if target.type != "claude":
        return SyncResult(
            success=False,
            errors=[f"v1 only supports 'claude', got: {target.type}"],
        )

    result = SyncResult()

    # Clear cache if fresh mode
    if fresh and not dry_run:
        cache_result = claude.clear_cache()
        if not cache_result.success:
            result.errors.append(f"Failed to clear cache: {cache_result.stderr}")

    # Sync marketplaces first (plugins depend on them)
    mp_actions, mp_errors = _sync_marketplaces(target.config, dry_run)
    for action in mp_actions:
        result.add_success(action)
    result.errors.extend(mp_errors)

    # Sync plugins
    plugin_actions, plugin_errors = _sync_plugins(target.config, dry_run)
    for action in plugin_actions:
        result.add_success(action)
    result.errors.extend(plugin_errors)

    # If there were any errors, mark as failed
    if result.errors:
        result.success = False

    return result


def sync_config(
    config: AIConfig,
    dry_run: bool = False,
    fresh: bool = False,
) -> dict[str, SyncResult]:
    """Sync all targets in a config.

    Args:
        config: Configuration to sync.
        dry_run: If True, only report what would be done.
        fresh: If True, clear cache before syncing.

    Returns:
        Dict mapping target type to SyncResult.
    """
    results: dict[str, SyncResult] = {}

    for target in config.targets:
        results[target.type] = sync_target(target, dry_run, fresh)

    return results


def get_status(target_type: str = "claude") -> StatusResult:
    """Get current status of plugins and marketplaces.

    Args:
        target_type: Target to get status for (only "claude" supported).

    Returns:
        StatusResult with current state.
    """
    if target_type != "claude":
        return StatusResult(
            target_type="claude",
            errors=[f"v1 only supports 'claude', got: {target_type}"],
        )

    result = StatusResult(target_type="claude")

    # Get plugins
    plugins, plugin_errors = claude.list_installed_plugins()
    result.errors.extend(plugin_errors)

    for plugin in plugins:
        result.plugins.append(
            PluginStatus(
                id=plugin.id,
                installed=True,
                enabled=plugin.enabled,
                scope=plugin.scope,
                version=plugin.version,
            )
        )

    # Get marketplaces
    marketplaces, mp_errors = claude.list_installed_marketplaces()
    result.errors.extend(mp_errors)

    for mp in marketplaces:
        result.marketplaces.append(mp.name)

    return result


def update_plugins(
    plugin_ids: list[str] | None = None,
    fresh: bool = False,
) -> SyncResult:
    """Update plugins to latest versions.

    Args:
        plugin_ids: Specific plugins to update, or None for all.
        fresh: If True, clear cache before updating.

    Returns:
        SyncResult with update actions.
    """
    result = SyncResult()

    # Clear cache if fresh mode
    if fresh:
        cache_result = claude.clear_cache()
        if not cache_result.success:
            result.errors.append(f"Failed to clear cache: {cache_result.stderr}")

    # Get installed plugins
    installed, errors = claude.list_installed_plugins()
    if errors:
        result.errors.extend(errors)
        result.success = False
        return result

    # Determine which plugins to update
    if plugin_ids is None:
        plugins_to_update = [p.id for p in installed]
    else:
        installed_ids = {p.id for p in installed}
        plugins_to_update = [pid for pid in plugin_ids if pid in installed_ids]

        # Warn about plugins that aren't installed
        for pid in plugin_ids:
            if pid not in installed_ids:
                result.errors.append(f"Plugin '{pid}' is not installed, skipping")

    # Update each plugin
    for plugin_id in plugins_to_update:
        update_result = claude.update_plugin(plugin_id)
        action = SyncAction(
            action="install",  # update is like reinstall
            target=plugin_id,
            reason="Update to latest version",
        )

        if update_result.success:
            result.add_success(action)
        else:
            result.add_failure(action, update_result.stderr)

    return result


def verify_sync(config: AIConfig) -> list[str]:
    """Verify that current state matches config.

    Args:
        config: Configuration to verify against.

    Returns:
        List of discrepancies found (empty if in sync).
    """
    discrepancies: list[str] = []

    for target in config.targets:
        if target.type != "claude":
            discrepancies.append(f"Unknown target type: {target.type}")
            continue

        # Check marketplaces
        installed_mps, mp_errors = claude.list_installed_marketplaces()
        if mp_errors:
            discrepancies.extend(mp_errors)
            continue

        installed_mp_names = {mp.name for mp in installed_mps}
        for name in target.config.marketplaces:
            if name not in installed_mp_names:
                discrepancies.append(f"Marketplace '{name}' is not registered")

        # Check plugins
        installed_plugins, plugin_errors = claude.list_installed_plugins()
        if plugin_errors:
            discrepancies.extend(plugin_errors)
            continue

        installed_by_id = {p.id: p for p in installed_plugins}

        for plugin_config in target.config.plugins:
            plugin_id = plugin_config.id
            installed = installed_by_id.get(plugin_id)

            if installed is None:
                if plugin_config.enabled:
                    discrepancies.append(f"Plugin '{plugin_id}' is not installed")
            else:
                if plugin_config.enabled and not installed.enabled:
                    discrepancies.append(f"Plugin '{plugin_id}' should be enabled")
                elif not plugin_config.enabled and installed.enabled:
                    discrepancies.append(f"Plugin '{plugin_id}' should be disabled")

    return discrepancies
