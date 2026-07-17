"""Declarative lifecycle for ai-config-owned Codex plugin packages."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ai_config.adapters.codex import (
    CodexCLI,
    CodexCommandError,
    CodexInstalledPlugin,
    CodexMarketplace,
    CodexPluginInstall,
)
from ai_config.converters.codex_package import CODEX_OWNERSHIP_FILE, CodexPackageSpec
from ai_config.semver import SemanticVersion
from ai_config.types import CodexLifecycleActionName

_OWNERSHIP_VERSION = 1


class _DuplicateOwnershipKey(ValueError):
    """Raised when ownership JSON contains duplicate object keys."""


def _ownership_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateOwnershipKey(f"duplicate key '{key}'")
        result[key] = value
    return result


@dataclass(frozen=True)
class CodexLifecycleAction:
    """One planned or completed Codex CLI lifecycle action."""

    action: CodexLifecycleActionName
    target: str
    reason: str


@dataclass(frozen=True)
class CodexLifecycleExecutionError(RuntimeError):
    """Lifecycle failure retaining the complete plan and partial progress."""

    planned_actions: tuple[CodexLifecycleAction, ...]
    completed_actions: tuple[CodexLifecycleAction, ...]
    failed_action: CodexLifecycleAction | None
    cause: str

    def __str__(self) -> str:
        failed = (
            f"{self.failed_action.action} for {self.failed_action.target}"
            if self.failed_action is not None
            else "ownership checkpoint"
        )
        return (
            f"Codex lifecycle failed during {failed} after "
            f"{len(self.completed_actions)}/{len(self.planned_actions)} planned actions: "
            f"{self.cause}"
        )


@dataclass(frozen=True)
class _OwnershipEntry:
    marketplace_name: str
    marketplace_path: Path
    version: str


class CodexLifecycleClient(Protocol):
    """Typed Codex operations required by lifecycle convergence."""

    def list_marketplaces(self) -> list[CodexMarketplace]: ...

    def add_marketplace(self, path: str, expected_name: str) -> CodexMarketplace: ...

    def remove_marketplace(self, name: str) -> None: ...

    def list_plugins(self) -> list[CodexInstalledPlugin]: ...

    def add_plugin(self, plugin_id: str) -> CodexPluginInstall: ...

    def remove_plugin(self, plugin_id: str) -> None: ...


def _load_ownership(output_dir: Path) -> dict[str, _OwnershipEntry]:
    path = output_dir / CODEX_OWNERSHIP_FILE
    if not path.exists():
        return {}
    try:
        payload: object = json.loads(path.read_text(), object_pairs_hook=_ownership_object)
    except (OSError, json.JSONDecodeError, _DuplicateOwnershipKey) as error:
        raise ValueError(
            f"Invalid ai-config Codex ownership state at {path}: {error}. "
            "Repair or remove only this ai-config-owned state file, then retry."
        ) from error
    if not isinstance(payload, dict) or payload.get("version") != _OWNERSHIP_VERSION:
        raise ValueError(
            f"Unsupported ai-config Codex ownership state at {path}; "
            "do not edit Codex config manually. Remove only this state file to rebuild ownership."
        )
    packages = payload.get("packages")
    if not isinstance(packages, dict):
        raise ValueError(f"Invalid ai-config Codex ownership packages table at {path}")
    parsed: dict[str, _OwnershipEntry] = {}
    for plugin_id, value in packages.items():
        if not isinstance(plugin_id, str) or not isinstance(value, dict):
            raise ValueError(f"Invalid ai-config Codex ownership entry at {path}")
        marketplace_name = value.get("marketplace_name")
        marketplace_path = value.get("marketplace_path")
        version = value.get("version")
        if (
            not isinstance(marketplace_name, str)
            or not marketplace_name
            or not isinstance(marketplace_path, str)
            or not marketplace_path
            or not isinstance(version, str)
        ):
            raise ValueError(
                f"Incomplete ai-config Codex ownership entry for {plugin_id} at {path}"
            )
        plugin_name, separator, selector_marketplace = plugin_id.rpartition("@")
        if (
            separator != "@"
            or not plugin_name
            or selector_marketplace != marketplace_name
            or marketplace_name != f"ai-config-{plugin_name}"
            or Path(marketplace_path).name != marketplace_name
        ):
            raise ValueError(
                f"Inconsistent ai-config Codex ownership identity for '{plugin_id}' at {path}; "
                "refusing ambiguous lifecycle state."
            )
        SemanticVersion.parse(version, context=f"owned Codex package {plugin_id} version")
        resolved_marketplace_path = Path(marketplace_path).resolve()
        owned_root = (output_dir / ".ai-config" / "codex" / "marketplaces").resolve()
        if resolved_marketplace_path.parent != owned_root:
            raise ValueError(
                f"Owned Codex marketplace path for '{plugin_id}' is outside {owned_root}; "
                "refusing filesystem cleanup."
            )
        parsed[plugin_id] = _OwnershipEntry(
            marketplace_name=marketplace_name,
            marketplace_path=resolved_marketplace_path,
            version=version,
        )
    return parsed


def _write_ownership(
    output_dir: Path,
    specs: list[CodexPackageSpec],
    retained: dict[str, _OwnershipEntry] | None = None,
) -> None:
    path = output_dir / CODEX_OWNERSHIP_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    packages = {
        plugin_id: {
            "marketplace_name": entry.marketplace_name,
            "marketplace_path": str(entry.marketplace_path),
            "version": entry.version,
        }
        for plugin_id, entry in sorted((retained or {}).items())
    }
    packages.update(
        {
            spec.plugin_id: {
                "marketplace_name": spec.marketplace_name,
                "marketplace_path": str(spec.marketplace_path),
                "version": spec.version,
            }
            for spec in sorted(specs, key=lambda item: item.plugin_id)
        }
    )
    if not packages:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"version": _OWNERSHIP_VERSION, "packages": packages}, indent=2) + "\n"
    )
    os.replace(temporary, path)


def _index_specs(specs: list[CodexPackageSpec]) -> dict[str, CodexPackageSpec]:
    desired: dict[str, CodexPackageSpec] = {}
    for spec in specs:
        existing = desired.get(spec.plugin_id)
        if existing is not None:
            sources = sorted(
                {
                    existing.source_plugin_id or existing.plugin_name,
                    spec.source_plugin_id or spec.plugin_name,
                }
            )
            raise ValueError(
                f"Normalized Codex plugin identity collision for '{spec.plugin_id}' from "
                f"{sources}. Rename one source plugin; no package or lifecycle state was changed."
            )
        desired[spec.plugin_id] = spec
    return desired


def _index_marketplaces(entries: list[CodexMarketplace]) -> dict[str, CodexMarketplace]:
    indexed: dict[str, CodexMarketplace] = {}
    for entry in entries:
        if entry.name in indexed:
            raise ValueError(
                f"Codex reported duplicate marketplace '{entry.name}'; refusing ambiguous state."
            )
        indexed[entry.name] = entry
    return indexed


def _index_plugins(entries: list[CodexInstalledPlugin]) -> dict[str, CodexInstalledPlugin]:
    indexed: dict[str, CodexInstalledPlugin] = {}
    for entry in entries:
        if entry.plugin_id in indexed:
            raise ValueError(
                f"Codex reported duplicate plugin '{entry.plugin_id}'; refusing ambiguous state."
            )
        indexed[entry.plugin_id] = entry
    return indexed


def _validate_transition(plugin_id: str, previous: str, desired: str, *, source: str) -> None:
    old_version = SemanticVersion.parse(previous, context=f"{source} {plugin_id} version")
    new_version = SemanticVersion.parse(
        desired, context=f"desired Codex package {plugin_id} version"
    )
    if new_version < old_version:
        raise ValueError(
            f"Invalid Codex package version transition for '{plugin_id}': {previous} -> {desired} "
            f"would downgrade {source} state. Bump the source manifest version or explicitly remove "
            "the owned package before retrying."
        )


def owned_codex_plugin_ids(output_dir: Path) -> set[str]:
    """Return strictly validated plugin IDs from one owned output ledger."""
    return set(_load_ownership(output_dir))


def validate_codex_transitions(
    specs: list[CodexPackageSpec],
    prior_output_dirs: list[Path],
) -> None:
    """Reject downgrades across current and retired generated output roots."""
    desired = _index_specs(specs)
    for output_dir in prior_output_dirs:
        for plugin_id, entry in _load_ownership(output_dir).items():
            spec = desired.get(plugin_id)
            if spec is not None:
                _validate_transition(plugin_id, entry.version, spec.version, source="ownership")


def _validate_runtime_identity(spec: CodexPackageSpec, installed: CodexInstalledPlugin) -> None:
    expected_source = (spec.marketplace_path / "plugins" / spec.plugin_name).resolve()
    if (
        installed.name != spec.plugin_name
        or installed.marketplace_name != spec.marketplace_name
        or installed.marketplace_root != spec.marketplace_path
        or installed.source_path != expected_source
    ):
        raise ValueError(
            f"Codex plugin identity collision for '{spec.plugin_id}': runtime source "
            f"{installed.source_path} does not match generated package {expected_source}. "
            "ai-config will not remove or replace ambiguous plugin state."
        )


def _plan_actions(
    desired: dict[str, CodexPackageSpec],
    previous: dict[str, _OwnershipEntry],
    marketplaces: dict[str, CodexMarketplace],
    plugins: dict[str, CodexInstalledPlugin],
    refreshed_plugin_ids: set[str],
    retained_plugin_ids: set[str],
    removal_reasons: dict[str, str],
    default_removal_reason: str,
) -> list[CodexLifecycleAction]:
    actions: list[CodexLifecycleAction] = []
    if set(desired) & retained_plugin_ids:
        raise ValueError("A Codex package cannot be both desired and temporarily unavailable")
    stale_ids = sorted(set(previous) - set(desired) - retained_plugin_ids)

    for plugin_id in stale_ids:
        entry = previous[plugin_id]
        removal_reason = removal_reasons.get(plugin_id, default_removal_reason)
        marketplace = marketplaces.get(entry.marketplace_name)
        if marketplace is not None and marketplace.root != entry.marketplace_path:
            raise ValueError(
                f"Codex marketplace ownership changed for '{entry.marketplace_name}': "
                f"registered root is {marketplace.root}, expected {entry.marketplace_path}. "
                "ai-config will not remove the marketplace or plugin. Resolve the collision and retry."
            )
        installed = plugins.get(plugin_id)
        if installed is not None:
            plugin_name = plugin_id.rsplit("@", 1)[0]
            expected_source = (entry.marketplace_path / "plugins" / plugin_name).resolve()
            if (
                installed.name != plugin_name
                or installed.marketplace_name != entry.marketplace_name
                or installed.marketplace_root != entry.marketplace_path
                or installed.source_path != expected_source
            ):
                raise ValueError(
                    f"Codex plugin ownership changed for '{plugin_id}'; ai-config will not remove "
                    "ambiguous runtime state. Resolve the collision and retry."
                )
            actions.append(CodexLifecycleAction("remove_codex_plugin", plugin_id, removal_reason))
        if marketplace is not None:
            actions.append(
                CodexLifecycleAction(
                    "remove_codex_marketplace",
                    entry.marketplace_name,
                    removal_reason,
                )
            )
        actions.append(CodexLifecycleAction("remove_codex_package", plugin_id, removal_reason))

    for plugin_id, spec in sorted(desired.items()):
        old = previous.get(plugin_id)
        if old is not None:
            if (
                old.marketplace_name != spec.marketplace_name
                or old.marketplace_path != spec.marketplace_path
            ):
                raise ValueError(
                    f"Owned Codex identity for '{plugin_id}' no longer matches its generated path; "
                    "refusing an ambiguous rename."
                )
            _validate_transition(plugin_id, old.version, spec.version, source="ownership")

        marketplace = marketplaces.get(spec.marketplace_name)
        marketplace_missing = marketplace is None
        if marketplace_missing:
            actions.append(
                CodexLifecycleAction(
                    "register_codex_marketplace",
                    spec.marketplace_name,
                    f"Generated marketplace is not registered at {spec.marketplace_path}",
                )
            )
        elif marketplace is not None and marketplace.root != spec.marketplace_path:
            raise ValueError(
                f"Codex marketplace name collision for '{spec.marketplace_name}': "
                f"registered root is {marketplace.root}, expected {spec.marketplace_path}. "
                "ai-config will not modify the unrelated marketplace. Rename/remove the collision and retry."
            )

        installed = plugins.get(plugin_id)
        if installed is None:
            actions.append(
                CodexLifecycleAction(
                    "install_codex_plugin",
                    plugin_id,
                    "Generated Codex plugin is not installed",
                )
            )
            continue

        _validate_runtime_identity(spec, installed)
        _validate_transition(plugin_id, installed.version, spec.version, source="installed")
        installed_version = SemanticVersion.parse(
            installed.version, context=f"installed Codex plugin {plugin_id} version"
        )
        desired_version = SemanticVersion.parse(
            spec.version, context=f"desired Codex package {plugin_id} version"
        )
        if installed_version < desired_version:
            actions.append(
                CodexLifecycleAction(
                    "update_codex_plugin",
                    plugin_id,
                    f"Installed version {installed.version} is older than generated {spec.version}",
                )
            )
        elif marketplace_missing:
            actions.append(
                CodexLifecycleAction(
                    "reinstall_codex_plugin",
                    plugin_id,
                    "Generated marketplace registration drifted; reinstall to repair ownership",
                )
            )
        elif not installed.enabled:
            actions.append(
                CodexLifecycleAction(
                    "reinstall_codex_plugin",
                    plugin_id,
                    "Installed generated plugin is disabled; reinstall to restore enabled state",
                )
            )
        elif plugin_id in refreshed_plugin_ids:
            actions.append(
                CodexLifecycleAction(
                    "update_codex_plugin",
                    plugin_id,
                    "Generated package content changed; reinstall through Codex CLI",
                )
            )
        else:
            actions.append(
                CodexLifecycleAction(
                    "noop_codex_plugin",
                    plugin_id,
                    f"Marketplace, installed version {spec.version}, and enabled state already match",
                )
            )
    return actions


def _validate_install_result(
    plugin_id: str,
    spec: CodexPackageSpec,
    installed: CodexPluginInstall,
) -> None:
    if installed.plugin_id != plugin_id or installed.version != spec.version:
        raise ValueError(
            f"Codex install result for '{plugin_id}' did not converge to generated version "
            f"{spec.version}; reported {installed.plugin_id} at {installed.version}."
        )


def sync_codex_packages(
    specs: list[CodexPackageSpec],
    *,
    output_dir: Path,
    refreshed_plugin_ids: set[str],
    dry_run: bool = False,
    cli: CodexLifecycleClient | None = None,
    retained_plugin_ids: set[str] | None = None,
    removal_reasons: dict[str, str] | None = None,
    default_removal_reason: str = "Source plugin is no longer configured",
    ignored_runtime_plugin_ids: set[str] | None = None,
    ignored_runtime_marketplace_names: set[str] | None = None,
) -> list[CodexLifecycleAction]:
    """Converge generated Codex packages without touching unrelated Codex state."""
    desired = _index_specs(specs)
    previous = _load_ownership(output_dir)
    codex: CodexLifecycleClient = cli or CodexCLI()
    marketplaces = _index_marketplaces(codex.list_marketplaces())
    plugins = _index_plugins(codex.list_plugins())
    ignored_plugins = ignored_runtime_plugin_ids or set()
    ignored_marketplaces = ignored_runtime_marketplace_names or set()
    if (ignored_plugins or ignored_marketplaces) and not dry_run:
        raise ValueError("Runtime state may be ignored only during a validated dry-run migration")
    for plugin_id in ignored_plugins:
        plugins.pop(plugin_id, None)
    for marketplace_name in ignored_marketplaces:
        marketplaces.pop(marketplace_name, None)
    retained_ids = retained_plugin_ids or set()
    actions = _plan_actions(
        desired,
        previous,
        marketplaces,
        plugins,
        refreshed_plugin_ids,
        retained_ids,
        removal_reasons or {},
        default_removal_reason,
    )

    if dry_run:
        return actions
    if not actions and not desired and retained_ids:
        return []

    completed: list[CodexLifecycleAction] = []
    for action in actions:
        try:
            if action.action == "remove_codex_plugin":
                codex.remove_plugin(action.target)
            elif action.action == "remove_codex_marketplace":
                codex.remove_marketplace(action.target)
            elif action.action == "remove_codex_package":
                entry = previous[action.target]
                if entry.marketplace_path.is_dir() and not entry.marketplace_path.is_symlink():
                    shutil.rmtree(entry.marketplace_path)
                elif entry.marketplace_path.exists() or entry.marketplace_path.is_symlink():
                    entry.marketplace_path.unlink()
            elif action.action == "register_codex_marketplace":
                spec = next(
                    item for item in desired.values() if item.marketplace_name == action.target
                )
                codex.add_marketplace(str(spec.marketplace_path), spec.marketplace_name)
            elif action.action in {"update_codex_plugin", "reinstall_codex_plugin"}:
                spec = desired[action.target]
                codex.remove_plugin(action.target)
                installed = codex.add_plugin(action.target)
                _validate_install_result(action.target, spec, installed)
            elif action.action == "install_codex_plugin":
                spec = desired[action.target]
                installed = codex.add_plugin(action.target)
                _validate_install_result(action.target, spec, installed)
            elif action.action != "noop_codex_plugin":
                raise ValueError(f"Unsupported Codex lifecycle action: {action.action}")
            completed.append(action)
        except (CodexCommandError, OSError, ValueError) as error:
            raise CodexLifecycleExecutionError(
                planned_actions=tuple(actions),
                completed_actions=tuple(completed),
                failed_action=action,
                cause=str(error),
            ) from error

    retained_entries = {
        plugin_id: previous[plugin_id] for plugin_id in retained_ids if plugin_id in previous
    }
    ownership_action = CodexLifecycleAction(
        "write_codex_ownership",
        str(output_dir / CODEX_OWNERSHIP_FILE),
        "Persist the converged ai-config ownership ledger",
    )
    try:
        _write_ownership(output_dir, specs, retained_entries)
    except OSError as error:
        raise CodexLifecycleExecutionError(
            planned_actions=(*actions, ownership_action),
            completed_actions=tuple(completed),
            failed_action=ownership_action,
            cause=str(error),
        ) from error
    return completed
