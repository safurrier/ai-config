"""Core operations for ai-config: sync, status, update."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ai_config.adapters import claude
from ai_config.adapters.codex import CodexCommandError
from ai_config.codex_lifecycle import (
    CodexLifecycleAction,
    CodexLifecycleExecutionError,
    owned_codex_plugin_ids,
    sync_codex_packages,
    validate_codex_transitions,
)
from ai_config.converters import InstallScope, TargetTool, convert_plugin
from ai_config.converters.claude_parser import normalize_portable_name, parse_claude_plugin
from ai_config.converters.codex_package import CodexPackageSpec, codex_package_spec
from ai_config.converters.emitters import PiEmitter
from ai_config.pi_ownership import PiDesiredFile, apply_pi_reconciliation, load_pi_ownership
from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    ConversionConfig,
    PluginConfig,
    PluginSource,
    PluginStatus,
    StatusResult,
    SyncAction,
    SyncResult,
    TargetConfig,
)

_CONVERSION_CACHE_VERSION = 7


@dataclass(frozen=True)
class _ConversionCandidate:
    """Resolved source and normalized package identity for one configured plugin."""

    config_id: str
    plugin_path: Path
    codex_spec: CodexPackageSpec | None


def _conversion_cache_path() -> Path:
    """Return path for conversion hash cache file."""
    return Path.home() / ".ai-config" / "cache" / "conversion-hashes.json"


def _load_conversion_cache() -> dict:
    """Load conversion cache data from disk."""
    cache_path = _conversion_cache_path()
    if not cache_path.exists():
        return {
            "version": _CONVERSION_CACHE_VERSION,
            "entries": {},
            "codex_output_dirs": [],
        }
    try:
        raw = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Invalid conversion cache at {cache_path}; clear the cache and retry: {error}"
        ) from error
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid conversion cache object at {cache_path}; clear it and retry")
    if raw.get("version") != _CONVERSION_CACHE_VERSION:
        return {
            "version": _CONVERSION_CACHE_VERSION,
            "entries": {},
            "codex_output_dirs": [],
        }
    if not isinstance(raw.get("entries"), dict):
        raise ValueError(f"Invalid conversion cache entries at {cache_path}; clear it and retry")
    output_dirs = raw.get("codex_output_dirs")
    if not isinstance(output_dirs, list) or any(
        not isinstance(output_dir, str) or not output_dir for output_dir in output_dirs
    ):
        raise ValueError(
            f"Invalid conversion cache Codex output roots at {cache_path}; clear it and retry"
        )
    pi_dirs = raw.get("pi_output_dirs", [])
    if not isinstance(pi_dirs, list) or any(
        not isinstance(item, str) or not item for item in pi_dirs
    ):
        raise ValueError(
            f"Invalid conversion cache Pi output roots at {cache_path}; clear the cache and retry"
        )
    return raw


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
    }
    return json.dumps(payload, sort_keys=True)


def _compute_plugin_hash(plugin_path: Path) -> str | None:
    """Compute a hash of all files in a plugin directory."""
    if not plugin_path.is_dir():
        return None

    hasher = hashlib.sha256()
    try:
        for file_path in sorted(plugin_path.rglob("*")):
            if not file_path.is_file() or file_path.is_symlink():
                continue
            relpath = file_path.relative_to(plugin_path).as_posix()
            hasher.update(relpath.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(b"x" if file_path.stat().st_mode & 0o111 else b"-")
            data = file_path.read_bytes()
            hasher.update(len(data).to_bytes(8, "big"))
            hasher.update(data)
        return hasher.hexdigest()
    except OSError:
        return None


def _resolve_local_marketplace_plugin_path(
    marketplace_root: Path,
    plugin_name: str,
) -> Path | None:
    """Resolve a plugin path from a local marketplace manifest."""
    for manifest_path in (
        marketplace_root / ".claude-plugin" / "marketplace.json",
        marketplace_root / "marketplace.json",
    ):
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue

        plugins = manifest.get("plugins", [])
        if not isinstance(plugins, list):
            continue
        for entry in plugins:
            if not isinstance(entry, dict) or entry.get("name") != plugin_name:
                continue
            source = entry.get("source")
            if not isinstance(source, str):
                continue
            source_path = Path(source).expanduser()
            if not source_path.is_absolute():
                source_path = marketplace_root / source_path
            if source_path.is_dir():
                return source_path.resolve()

    fallback_path = marketplace_root / plugin_name
    if fallback_path.is_dir():
        return fallback_path

    return None


def _resolve_plugin_conversion_path(
    config: ClaudeTargetConfig,
    plugin_config: PluginConfig,
    installed: claude.InstalledPlugin | None,
) -> Path | None:
    """Resolve the source path to use for cross-tool conversion.

    Claude plugin list can report an installPath under its plugin cache even
    after that cache was cleared. Prefer a live installPath, but fall back to
    the configured local marketplace source path when possible.
    """
    installed_path = (
        Path(installed.install_path) if installed is not None and installed.install_path else None
    )
    if installed_path is not None and installed_path.is_dir():
        return installed_path

    marketplace_name = plugin_config.marketplace
    if marketplace_name is None:
        return installed_path

    marketplace = config.marketplaces.get(marketplace_name)
    if marketplace is None or marketplace.source != PluginSource.LOCAL:
        return installed_path

    return _resolve_local_marketplace_plugin_path(Path(marketplace.path), plugin_config.plugin_name)


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
    conversion_actions, conversion_failures, conversion_errors = _sync_conversions(
        target.config, dry_run, force_convert
    )
    for action in conversion_actions:
        result.add_success(action)
    if conversion_failures:
        result.actions_failed.extend(conversion_failures)
        result.success = False
    result.errors.extend(conversion_errors)

    # If there were any errors, mark as failed
    if result.errors:
        result.success = False

    return result


def _compute_owned_codex_hash(spec: CodexPackageSpec) -> str | None:
    """Hash an owned generated marketplace and reject symlinked content."""
    root = spec.marketplace_path
    if not root.is_dir() or root.is_symlink():
        return None
    hasher = hashlib.sha256()
    try:
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                return None
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            data = path.read_bytes()
            hasher.update(relative.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(b"x" if path.stat().st_mode & 0o111 else b"-")
            hasher.update(len(data).to_bytes(8, "big"))
            hasher.update(data)
    except OSError:
        return None
    return hasher.hexdigest()


def _owned_codex_output_dirs(
    conversion: ConversionConfig | None,
    cache: dict,
) -> list[Path]:
    """Find output roots only when they contain ai-config's ownership ledger."""
    candidates: set[Path] = {Path.cwd().resolve(), Path.home().resolve()}
    if conversion is not None:
        candidates.add(_resolve_conversion_output_dir(conversion).resolve())
    tracked_output_dirs = cache.get("codex_output_dirs", [])
    if not isinstance(tracked_output_dirs, list) or any(
        not isinstance(output_dir, str) or not output_dir for output_dir in tracked_output_dirs
    ):
        raise ValueError("Invalid cached Codex output roots; clear the cache and retry")
    candidates.update(Path(output_dir).expanduser().resolve() for output_dir in tracked_output_dirs)
    entries = cache.get("entries")
    if isinstance(entries, dict):
        for signature_map in entries.values():
            if not isinstance(signature_map, dict):
                raise ValueError("Invalid conversion cache entry table; clear the cache and retry")
            for signature in signature_map:
                if not isinstance(signature, str):
                    raise ValueError(
                        "Invalid conversion cache signature; clear the cache and retry"
                    )
                try:
                    settings = json.loads(signature)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        "Invalid conversion cache signature JSON; clear the cache and retry"
                    ) from error
                if not isinstance(settings, dict):
                    raise ValueError("Invalid conversion cache settings; clear the cache and retry")
                targets_value = settings.get("targets")
                output_dir_value = settings.get("output_dir")
                if (
                    isinstance(targets_value, list)
                    and "codex" in targets_value
                    and isinstance(output_dir_value, str)
                ):
                    candidates.add(Path(output_dir_value).expanduser().resolve())
    owned_roots: list[Path] = []
    for candidate in candidates:
        if (candidate / ".ai-config" / "codex" / "ownership.json").is_file():
            owned_roots.append(candidate)
    owned_roots.sort(key=lambda item: item.as_posix())
    return owned_roots


def _pi_root_has_ownership(root: Path) -> bool:
    """Return whether a root has a readable ai-config Pi ledger."""
    try:
        return bool(load_pi_ownership(root))
    except ValueError:
        # The reconciliation call surfaces malformed state as a hard error.
        return True


def _sync_lifecycle_actions(actions: Iterable[CodexLifecycleAction]) -> list[SyncAction]:
    return [
        SyncAction(action=action.action, target=action.target, reason=action.reason)
        for action in actions
    ]


def _apply_codex_lifecycle(
    specs: list[CodexPackageSpec],
    *,
    output_dir: Path,
    refreshed_plugin_ids: set[str],
    retained_plugin_ids: set[str] | None = None,
    removal_reasons: dict[str, str] | None = None,
    default_removal_reason: str = "Source plugin is no longer configured",
) -> tuple[list[SyncAction], list[SyncAction], list[str]]:
    """Run one prevalidated lifecycle mutation while preserving partial progress."""
    try:
        completed = sync_codex_packages(
            specs,
            output_dir=output_dir,
            refreshed_plugin_ids=refreshed_plugin_ids,
            retained_plugin_ids=retained_plugin_ids,
            removal_reasons=removal_reasons,
            default_removal_reason=default_removal_reason,
        )
        return _sync_lifecycle_actions(completed), [], []
    except CodexLifecycleExecutionError as error:
        completed_actions = _sync_lifecycle_actions(error.completed_actions)
        failed_actions = (
            _sync_lifecycle_actions([error.failed_action])
            if error.failed_action is not None
            else []
        )
        return completed_actions, failed_actions, [str(error)]
    except (CodexCommandError, OSError, ValueError) as error:
        return [], [], [str(error)]


def _sync_conversions(
    config: ClaudeTargetConfig,
    dry_run: bool = False,
    force_convert: bool = False,
) -> tuple[list[SyncAction], list[SyncAction], list[str]]:
    """Convert plugins and converge every prior owned Codex package root."""
    actions: list[SyncAction] = []
    failed_actions: list[SyncAction] = []
    errors: list[str] = []
    try:
        cache = _load_conversion_cache()
    except ValueError as error:
        return [], [], [str(error)]
    cache_entries = cache.get("entries")
    if not isinstance(cache_entries, dict):
        return [], [], ["Invalid conversion cache entries; clear the cache and retry"]
    tracked_output_dirs = cache.get("codex_output_dirs", [])
    if not isinstance(tracked_output_dirs, list) or any(
        not isinstance(tracked, str) or not tracked for tracked in tracked_output_dirs
    ):
        return [], [], ["Invalid cached Codex output roots; clear the cache and retry"]
    cache["codex_output_dirs"] = tracked_output_dirs
    tracked_pi_output_dirs = cache.get("pi_output_dirs", [])
    if not isinstance(tracked_pi_output_dirs, list) or any(
        not isinstance(tracked, str) or not tracked for tracked in tracked_pi_output_dirs
    ):
        return [], [], ["Invalid cached Pi output roots; clear the cache and retry"]
    cache["pi_output_dirs"] = tracked_pi_output_dirs
    cache_dirty = False

    conversion = config.conversion
    conversion_active = conversion is not None and conversion.enabled
    if conversion_active and conversion is not None:
        targets = [TargetTool(target) for target in conversion.targets]
        output_dir = _resolve_conversion_output_dir(conversion)
        scope = InstallScope(conversion.scope)
        signature = _conversion_signature(conversion, output_dir)
    else:
        targets = []
        output_dir = (
            _resolve_conversion_output_dir(conversion) if conversion is not None else Path.cwd()
        )
        scope = InstallScope.PROJECT
        signature = ""
    codex_enabled = TargetTool.CODEX in targets
    pi_enabled = TargetTool.PI in targets
    resolved_output_dir = str(output_dir.resolve())
    if pi_enabled and resolved_output_dir not in tracked_pi_output_dirs:
        tracked_pi_output_dirs.append(resolved_output_dir)
        tracked_pi_output_dirs.sort()
        cache_dirty = True
    if codex_enabled and resolved_output_dir not in tracked_output_dirs:
        tracked_output_dirs.append(resolved_output_dir)
        tracked_output_dirs.sort()
        cache_dirty = True
    try:
        prior_output_dirs = _owned_codex_output_dirs(conversion, cache)
    except ValueError as error:
        return [], [], [str(error)]
    retained_root_strings = {str(root.resolve()) for root in prior_output_dirs}
    if codex_enabled:
        retained_root_strings.add(resolved_output_dir)
    pruned_output_dirs = [
        tracked for tracked in tracked_output_dirs if tracked in retained_root_strings
    ]
    if pruned_output_dirs != tracked_output_dirs:
        tracked_output_dirs[:] = pruned_output_dirs
        cache_dirty = True
    retiring_output_dirs = [
        root
        for root in prior_output_dirs
        if not codex_enabled or root.resolve() != output_dir.resolve()
    ]
    prior_pi_output_dirs = [
        Path(item).expanduser().resolve()
        for item in tracked_pi_output_dirs
        if _pi_root_has_ownership(Path(item).expanduser().resolve())
    ]
    retiring_pi_output_dirs = [
        root for root in prior_pi_output_dirs if not pi_enabled or root != output_dir.resolve()
    ]

    installed_by_id: dict[str, claude.InstalledPlugin] = {}
    if conversion_active:
        installed_plugins, plugin_errors = claude.list_installed_plugins()
        if plugin_errors:
            return [], [], plugin_errors
        installed_by_id = {plugin.id: plugin for plugin in installed_plugins}

    codex_specs: list[CodexPackageSpec] = []
    retained_codex_ids: set[str] = set()
    removal_reasons: dict[str, str] = {}
    candidates: list[_ConversionCandidate] = []
    codex_sources: dict[str, str] = {}
    unavailable_pi_sources: set[str] = set()
    has_blocking_errors = False

    if conversion_active:
        for plugin_config in config.plugins:
            configured_identity = normalize_portable_name(plugin_config.plugin_name, "plugin")
            configured_codex_id = f"{configured_identity}@ai-config-{configured_identity}"
            if not plugin_config.enabled:
                if codex_enabled:
                    removal_reasons[configured_codex_id] = "Source plugin is disabled"
                continue

            installed = installed_by_id.get(plugin_config.id)
            plugin_path = _resolve_plugin_conversion_path(config, plugin_config, installed)
            if plugin_path is None:
                if codex_enabled:
                    retained_codex_ids.add(configured_codex_id)
                if pi_enabled:
                    unavailable_pi_sources.add(plugin_config.id)
                install_path = (
                    installed.install_path
                    if installed is not None and installed.install_path
                    else "<unavailable>"
                )
                errors.append(
                    f"Conversion source for {plugin_config.id} is temporarily unavailable "
                    f"(installPath={install_path}); prior owned conversion state was retained"
                )
                continue

            spec: CodexPackageSpec | None = None
            if codex_enabled:
                try:
                    ir = parse_claude_plugin(plugin_path)
                except (OSError, ValueError) as error:
                    has_blocking_errors = True
                    errors.append(f"Conversion failed for {plugin_config.id}: {error}")
                    continue
                parse_errors = [
                    diagnostic.message
                    for diagnostic in ir.diagnostics
                    if diagnostic.severity.value == "error"
                ]
                if parse_errors:
                    has_blocking_errors = True
                    errors.extend(
                        f"Conversion failed for {plugin_config.id}: {message}"
                        for message in parse_errors
                    )
                    continue
                if configured_identity != ir.identity.plugin_id:
                    has_blocking_errors = True
                    errors.append(
                        f"Codex identity mismatch for configured plugin '{plugin_config.id}': "
                        f"config normalizes to '{configured_identity}', but source manifest "
                        f"normalizes to '{ir.identity.plugin_id}'. Make the config selector and "
                        "manifest name agree; no package or lifecycle state was changed."
                    )
                    continue
                try:
                    spec = codex_package_spec(
                        configured_identity,
                        ir.identity.version,
                        output_dir,
                        source_plugin_id=plugin_config.id,
                    )
                except ValueError as error:
                    has_blocking_errors = True
                    errors.append(f"Conversion failed for {plugin_config.id}: {error}")
                    continue
                conflicting_source = codex_sources.get(spec.plugin_id)
                if conflicting_source is not None:
                    has_blocking_errors = True
                    errors.append(
                        f"Normalized Codex plugin identity collision for '{spec.plugin_id}' from "
                        f"'{conflicting_source}' and '{plugin_config.id}'. Rename one source plugin; "
                        "no Codex package or lifecycle state was changed."
                    )
                    continue
                codex_sources[spec.plugin_id] = plugin_config.id
                codex_specs.append(spec)
            candidates.append(_ConversionCandidate(plugin_config.id, plugin_path, spec))

    if has_blocking_errors:
        return [], [], errors

    if codex_enabled:
        try:
            validate_codex_transitions(codex_specs, prior_output_dirs)
        except ValueError as error:
            errors.append(str(error))
            return [], [], errors

    # Pi is reconciled as one owned output set, rather than plugin-by-plugin writes.
    # Its parser/emitter diagnostics must be fatal before any lifecycle plan can mutate output.
    pi_desired: list[PiDesiredFile] = []
    pi_diagnostic_errors = False
    if pi_enabled:
        for candidate in candidates:
            try:
                ir = parse_claude_plugin(candidate.plugin_path)
                parse_errors = [
                    diagnostic.message
                    for diagnostic in ir.diagnostics
                    if diagnostic.severity.value == "error"
                ]
                if parse_errors:
                    pi_diagnostic_errors = True
                    errors.extend(
                        f"Pi conversion failed for {candidate.config_id}: {message}"
                        for message in parse_errors
                    )
                    continue
                emitted = PiEmitter(scope).emit(ir)
                emit_errors = [
                    diagnostic.message
                    for diagnostic in emitted.diagnostics
                    if diagnostic.severity.value == "error"
                ]
                if emit_errors:
                    pi_diagnostic_errors = True
                    errors.extend(
                        f"Pi conversion failed for {candidate.config_id}: {message}"
                        for message in emit_errors
                    )
                    continue
            except (OSError, ValueError) as error:
                pi_diagnostic_errors = True
                errors.append(f"Pi conversion failed for {candidate.config_id}: {error}")
                continue
            for file in emitted.files:
                content = (
                    file.content.encode("utf-8") if isinstance(file.content, str) else file.content
                )
                pi_desired.append(
                    PiDesiredFile(candidate.config_id, file.path, content, file.executable)
                )
        if pi_diagnostic_errors:
            return [], [], errors

    candidates_to_convert: list[tuple[_ConversionCandidate, str | None]] = []
    for candidate in candidates:
        plugin_hash = _compute_plugin_hash(candidate.plugin_path)
        cache_valid = False
        if not force_convert and plugin_hash is not None:
            signature_map = cache_entries.get(str(candidate.plugin_path))
            cached = signature_map.get(signature) if isinstance(signature_map, dict) else None
            cache_valid = isinstance(cached, dict) and cached.get("hash") == plugin_hash
            if cache_valid and candidate.codex_spec is not None:
                if not isinstance(cached, dict):
                    cache_valid = False
                else:
                    cached_output_hash = cached.get("codex_output_hash")
                    cache_valid = isinstance(
                        cached_output_hash, str
                    ) and cached_output_hash == _compute_owned_codex_hash(candidate.codex_spec)
        if not cache_valid:
            candidates_to_convert.append((candidate, plugin_hash))

    # Pi has its own ownership-aware write path; other targets retain existing behavior.
    non_pi_targets = [target for target in targets if target != TargetTool.PI]

    # Validate every emitter result in memory before lifecycle cleanup or generated writes.
    for candidate, _plugin_hash in candidates_to_convert:
        try:
            reports = convert_plugin(
                plugin_path=candidate.plugin_path,
                targets=non_pi_targets,
                output_dir=output_dir,
                scope=scope,
                dry_run=True,
                best_effort=True,
            )
        except (OSError, ValueError) as error:
            errors.append(f"Conversion failed for {candidate.config_id}: {error}")
            continue
        report_errors = [
            f"{target.value}: {diagnostic.message}"
            for target, report in reports.items()
            for diagnostic in report.errors
        ]
        errors.extend(
            f"Conversion failed for {candidate.config_id}: {message}" for message in report_errors
        )

    preflight_actions: list[SyncAction] = []
    target_removed_reason = "Codex conversion target is disabled or removed"
    try:
        pi_plan_roots = [(output_dir, pi_desired, unavailable_pi_sources)] if pi_enabled else []
        pi_plan_roots.extend((root, [], set()) for root in retiring_pi_output_dirs)
        for pi_root, desired, retained_sources in pi_plan_roots:
            preflight_actions.extend(
                SyncAction(action=action.action, target=str(action.path), reason=action.reason)
                for action in apply_pi_reconciliation(
                    pi_root, desired, dry_run=True, retained_sources=retained_sources
                )
            )
        for retiring_root in retiring_output_dirs:
            planned = sync_codex_packages(
                [],
                output_dir=retiring_root,
                refreshed_plugin_ids=set(),
                dry_run=True,
                removal_reasons={},
                default_removal_reason=target_removed_reason,
            )
            preflight_actions.extend(_sync_lifecycle_actions(planned))
        if codex_enabled:
            migrating_ids = {
                plugin_id
                for retiring_root in retiring_output_dirs
                for plugin_id in owned_codex_plugin_ids(retiring_root)
            }
            migrating_marketplaces = {
                f"ai-config-{plugin_id.rsplit('@', 1)[0]}" for plugin_id in migrating_ids
            }
            planned = sync_codex_packages(
                codex_specs,
                output_dir=output_dir,
                refreshed_plugin_ids={
                    candidate.codex_spec.plugin_id
                    for candidate, _hash in candidates_to_convert
                    if candidate.codex_spec is not None
                },
                retained_plugin_ids=retained_codex_ids,
                removal_reasons=removal_reasons,
                ignored_runtime_plugin_ids=migrating_ids,
                ignored_runtime_marketplace_names=migrating_marketplaces,
                dry_run=True,
            )
            preflight_actions.extend(_sync_lifecycle_actions(planned))
    except (CodexCommandError, OSError, ValueError) as error:
        errors.append(str(error))

    if errors:
        return (preflight_actions if dry_run else []), [], errors
    if dry_run:
        return preflight_actions, [], []

    # Do not checkpoint ownership until each root's entire filesystem plan succeeds.
    for pi_root, desired, retained_sources in (
        [(output_dir, pi_desired, unavailable_pi_sources)] if pi_enabled else []
    ) + [(root, [], set()) for root in retiring_pi_output_dirs]:
        try:
            completed_pi = apply_pi_reconciliation(
                pi_root, desired, retained_sources=retained_sources
            )
            actions.extend(
                SyncAction(action=item.action, target=str(item.path), reason=item.reason)
                for item in completed_pi
            )
        except (OSError, ValueError) as error:
            return actions, failed_actions, [str(error)]
    retained_pi_roots = {str(output_dir.resolve())} if pi_enabled else set()
    if tracked_pi_output_dirs != sorted(retained_pi_roots):
        tracked_pi_output_dirs[:] = sorted(retained_pi_roots)
        cache_dirty = True

    for retiring_root in retiring_output_dirs:
        completed, failed, lifecycle_errors = _apply_codex_lifecycle(
            [],
            output_dir=retiring_root,
            refreshed_plugin_ids=set(),
            removal_reasons={},
            default_removal_reason=target_removed_reason,
        )
        actions.extend(completed)
        failed_actions.extend(failed)
        errors.extend(lifecycle_errors)
        if lifecycle_errors:
            return actions, failed_actions, errors
        retiring_root_text = str(retiring_root.resolve())
        if retiring_root_text in tracked_output_dirs:
            tracked_output_dirs.remove(retiring_root_text)
            cache_dirty = True

    refreshed_codex_ids: set[str] = set()
    for candidate, plugin_hash in candidates_to_convert:
        try:
            reports = convert_plugin(
                plugin_path=candidate.plugin_path,
                targets=non_pi_targets,
                output_dir=output_dir,
                scope=scope,
                dry_run=False,
                best_effort=True,
            )
            report_errors = [
                f"{target.value}: {diagnostic.message}"
                for target, report in reports.items()
                for diagnostic in report.errors
            ]
            if report_errors:
                errors.extend(
                    f"Conversion failed for {candidate.config_id}: {message}"
                    for message in report_errors
                )
                continue
            if candidate.codex_spec is not None:
                codex_report = reports.get(TargetTool.CODEX)
                if codex_report is None:
                    errors.append(
                        f"Conversion failed for {candidate.config_id}: missing Codex conversion report"
                    )
                    continue
                if (
                    codex_report.source_plugin.plugin_id != candidate.codex_spec.plugin_name
                    or (codex_report.source_plugin.version or "0.0.0")
                    != candidate.codex_spec.version
                ):
                    errors.append(
                        f"Conversion failed for {candidate.config_id}: normalized source identity "
                        "changed between lifecycle preflight and package emission"
                    )
                    continue
                refreshed_codex_ids.add(candidate.codex_spec.plugin_id)
            if plugin_hash is not None:
                signature_map = cache_entries.setdefault(str(candidate.plugin_path), {})
                if not isinstance(signature_map, dict):
                    signature_map = {}
                    cache_entries[str(candidate.plugin_path)] = signature_map
                cache_value = {
                    "hash": plugin_hash,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                if candidate.codex_spec is not None:
                    output_hash = _compute_owned_codex_hash(candidate.codex_spec)
                    if output_hash is None:
                        errors.append(
                            f"Conversion failed for {candidate.config_id}: generated Codex output "
                            "is missing or contains symlinks"
                        )
                        continue
                    cache_value["codex_output_hash"] = output_hash
                signature_map[signature] = cache_value
                cache_dirty = True
        except (OSError, ValueError) as error:
            errors.append(f"Conversion failed for {candidate.config_id}: {error}")

    if errors:
        return actions, failed_actions, errors

    if codex_enabled:
        completed, failed, lifecycle_errors = _apply_codex_lifecycle(
            codex_specs,
            output_dir=output_dir,
            refreshed_plugin_ids=refreshed_codex_ids,
            retained_plugin_ids=retained_codex_ids,
            removal_reasons=removal_reasons,
        )
        actions.extend(completed)
        failed_actions.extend(failed)
        errors.extend(lifecycle_errors)

    if cache_dirty and not errors:
        try:
            _save_conversion_cache(cache)
        except OSError as error:
            errors.append(f"Failed to save conversion cache: {error}")
    return actions, failed_actions, errors


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


def sync_discrepancies(results: dict[str, SyncResult]) -> list[str]:
    """Translate dry-run lifecycle plans and inspection failures into verification truth."""
    discrepancies: list[str] = []
    for target_type, result in results.items():
        discrepancies.extend(f"{target_type}: {error}" for error in result.errors)
        discrepancies.extend(
            f"{target_type}: failed to inspect {action.action} for {action.target}"
            for action in result.actions_failed
        )
        discrepancies.extend(
            f"{target_type}: {action.action} required for {action.target}: {action.reason}"
            for action in result.actions_taken
            if action.action not in {"noop_codex_plugin", "noop_pi_output"}
        )
    return discrepancies


def verify_sync(config: AIConfig) -> list[str]:
    """Verify all configured targets using the same dry-run planner as sync."""
    return sync_discrepancies(sync_config(config, dry_run=True))
