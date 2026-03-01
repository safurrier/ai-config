"""Core operations for ai-config: sync, status, update."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ai_config.adapters import claude
from ai_config.converters import InstallScope, TargetTool, convert_plugin
from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    ConversionConfig,
    PluginSource,
    PluginStatus,
    StatusResult,
    SyncAction,
    SyncResult,
    TargetConfig,
)

_CONVERSION_CACHE_VERSION = 1


def _conversion_cache_path() -> Path:
    """Return path for conversion hash cache file."""
    return Path.home() / ".ai-config" / "cache" / "conversion-hashes.json"


def _load_conversion_cache() -> dict:
    """Load conversion cache data from disk."""
    cache_path = _conversion_cache_path()
    if not cache_path.exists():
        return {"version": _CONVERSION_CACHE_VERSION, "entries": {}}
    try:
        raw = json.loads(cache_path.read_text())
        if not isinstance(raw, dict):
            return {"version": _CONVERSION_CACHE_VERSION, "entries": {}}
        if raw.get("version") != _CONVERSION_CACHE_VERSION:
            return {"version": _CONVERSION_CACHE_VERSION, "entries": {}}
        if not isinstance(raw.get("entries"), dict):
            raw["entries"] = {}
        return raw
    except (OSError, json.JSONDecodeError):
        return {"version": _CONVERSION_CACHE_VERSION, "entries": {}}


def _save_conversion_cache(cache: dict) -> None:
    """Persist conversion cache data to disk."""
    cache_path = _conversion_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True))


def _conversion_signature(conversion: ConversionConfig, output_dir: Path) -> str:
    """Build a stable signature for conversion settings."""
    payload = {
        "targets": sorted(conversion.targets),
        "scope": conversion.scope,
        "output_dir": str(output_dir),
        "commands_as_skills": conversion.commands_as_skills,
    }
    return json.dumps(payload, sort_keys=True)


def _compute_plugin_hash(plugin_path: Path) -> str | None:
    """Compute a hash of all files in a plugin directory."""
    hasher = hashlib.sha256()
    try:
        for file_path in sorted(plugin_path.rglob("*")):
            if not file_path.is_file() or file_path.is_symlink():
                continue
            relpath = file_path.relative_to(plugin_path).as_posix()
            hasher.update(relpath.encode("utf-8"))
            hasher.update(b"\0")
            data = file_path.read_bytes()
            hasher.update(len(data).to_bytes(8, "big"))
            hasher.update(data)
        return hasher.hexdigest()
    except OSError:
        return None


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

                # Snapshot names before this add so we can detect renames
                pre_add_mps, _ = claude.list_installed_marketplaces()
                pre_add_names = {mp.name for mp in pre_add_mps}

                result = claude.add_marketplace(repo=repo, name=name, path=path)
                if not result.success:
                    errors.append(f"Failed to add marketplace '{name}': {result.stderr}")
                    continue

                # Check if the registered name matches our config key
                post_mps, _ = claude.list_installed_marketplaces()
                post_names = {mp.name for mp in post_mps}
                if name not in post_names:
                    # The marketplace was registered under a different name
                    # (Claude CLI uses the name from marketplace.json)
                    new_names = post_names - pre_add_names
                    if new_names:
                        actual = next(iter(new_names))
                        errors.append(
                            f"Marketplace registered as '{actual}' (from marketplace.json), "
                            f"but config uses '{name}'. "
                            f"Update your config key from '{name}' to '{actual}' to match."
                        )

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
    force_convert: bool = False,
) -> SyncResult:
    """Sync a target to match its config.

    Args:
        target: Target configuration to sync.
        dry_run: If True, only report what would be done.
        fresh: If True, clear cache before syncing.
        force_convert: If True, bypass conversion hash cache.

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

    # Run conversion if configured
    conversion_errors = _sync_conversions(target.config, dry_run, force_convert)
    result.errors.extend(conversion_errors)

    # If there were any errors, mark as failed
    if result.errors:
        result.success = False

    return result


def _sync_conversions(
    config: ClaudeTargetConfig,
    dry_run: bool = False,
    force_convert: bool = False,
) -> list[str]:
    """Convert installed plugins to other targets when configured."""
    if config.conversion is None or not config.conversion.enabled:
        return []

    errors: list[str] = []
    cache = _load_conversion_cache()
    cache_entries = cache.setdefault("entries", {})
    cache_dirty = False

    installed_plugins, plugin_errors = claude.list_installed_plugins()
    if plugin_errors:
        return plugin_errors

    installed_by_id = {p.id: p for p in installed_plugins}

    conversion = config.conversion
    output_dir = _resolve_conversion_output_dir(conversion)
    targets = [TargetTool(t) for t in conversion.targets]
    scope = InstallScope(conversion.scope)
    signature = _conversion_signature(conversion, output_dir)

    for plugin_config in config.plugins:
        if not plugin_config.enabled:
            continue
        installed = installed_by_id.get(plugin_config.id)
        if not installed:
            continue
        plugin_path = Path(installed.install_path)
        plugin_hash = _compute_plugin_hash(plugin_path)
        if not force_convert and plugin_hash is not None:
            signature_map = cache_entries.get(str(plugin_path), {})
            if isinstance(signature_map, dict):
                cached = signature_map.get(signature)
                if isinstance(cached, dict) and cached.get("hash") == plugin_hash:
                    continue
        try:
            reports = convert_plugin(
                plugin_path=plugin_path,
                targets=targets,
                output_dir=output_dir,
                scope=scope,
                dry_run=dry_run,
                best_effort=True,
                commands_as_skills=conversion.commands_as_skills,
            )
            if not dry_run and plugin_hash is not None:
                if not any(report.has_errors() for report in reports.values()):
                    signature_map = cache_entries.setdefault(str(plugin_path), {})
                    signature_map[signature] = {
                        "hash": plugin_hash,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    cache_dirty = True
        except Exception as e:
            errors.append(f"Conversion failed for {plugin_config.id}: {e}")

    if cache_dirty:
        _save_conversion_cache(cache)

    return errors


def _resolve_conversion_output_dir(conversion: ConversionConfig) -> Path:
    """Resolve output directory based on conversion config."""
    if conversion.output_dir:
        return Path(conversion.output_dir)
    return Path.home() if conversion.scope == "user" else Path.cwd()


def sync_config(
    config: AIConfig,
    dry_run: bool = False,
    fresh: bool = False,
    force_convert: bool = False,
) -> dict[str, SyncResult]:
    """Sync all targets in a config.

    Args:
        config: Configuration to sync.
        dry_run: If True, only report what would be done.
        fresh: If True, clear cache before syncing.
        force_convert: If True, bypass conversion hash cache.

    Returns:
        Dict mapping target type to SyncResult.
    """
    results: dict[str, SyncResult] = {}

    for target in config.targets:
        results[target.type] = sync_target(target, dry_run, fresh, force_convert)

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
