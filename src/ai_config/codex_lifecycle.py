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
        parsed[plugin_id] = _OwnershipEntry(
            marketplace_name=marketplace_name,
            marketplace_path=Path(marketplace_path).resolve(),
            version=version,
        )
    return parsed


def _write_ownership(output_dir: Path, specs: list[CodexPackageSpec]) -> None:
    path = output_dir / CODEX_OWNERSHIP_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    packages = {
        spec.plugin_id: {
            "marketplace_name": spec.marketplace_name,
            "marketplace_path": str(spec.marketplace_path),
            "version": spec.version,
        }
        for spec in sorted(specs, key=lambda item: item.plugin_id)
    }
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
) -> list[CodexLifecycleAction]:
    actions: list[CodexLifecycleAction] = []
    stale_ids = sorted(set(previous) - set(desired))

    for plugin_id in stale_ids:
        entry = previous[plugin_id]
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
            actions.append(
                CodexLifecycleAction(
                    "remove_codex_plugin", plugin_id, "Source plugin is no longer configured"
                )
            )
        if marketplace is not None:
            actions.append(
                CodexLifecycleAction(
                    "remove_codex_marketplace",
                    entry.marketplace_name,
                    "Generated marketplace is no longer configured",
                )
            )

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


def sync_codex_packages(
    specs: list[CodexPackageSpec],
    *,
    output_dir: Path,
    refreshed_plugin_ids: set[str],
    dry_run: bool = False,
    cli: CodexLifecycleClient | None = None,
) -> list[CodexLifecycleAction]:
    """Converge generated Codex packages without touching unrelated Codex state."""
    desired = _index_specs(specs)
    previous = _load_ownership(output_dir)
    codex: CodexLifecycleClient = cli or CodexCLI()
    marketplaces = _index_marketplaces(codex.list_marketplaces())
    plugins = _index_plugins(codex.list_plugins())
    actions = _plan_actions(desired, previous, marketplaces, plugins, refreshed_plugin_ids)

    if dry_run:
        return actions

    stale_ids = sorted(set(previous) - set(desired))
    for plugin_id in stale_ids:
        entry = previous[plugin_id]
        if plugin_id in plugins:
            codex.remove_plugin(plugin_id)
        if entry.marketplace_name in marketplaces:
            codex.remove_marketplace(entry.marketplace_name)
        owned_root = (output_dir / ".ai-config" / "codex" / "marketplaces").resolve()
        if entry.marketplace_path != owned_root and owned_root in entry.marketplace_path.parents:
            shutil.rmtree(entry.marketplace_path, ignore_errors=True)

    action_by_plugin = {
        action.target: action.action
        for action in actions
        if action.action
        in {"install_codex_plugin", "update_codex_plugin", "reinstall_codex_plugin"}
    }
    for plugin_id, spec in sorted(desired.items()):
        if spec.marketplace_name not in marketplaces:
            codex.add_marketplace(str(spec.marketplace_path), spec.marketplace_name)
        plugin_action = action_by_plugin.get(plugin_id)
        if plugin_action in {"update_codex_plugin", "reinstall_codex_plugin"}:
            codex.remove_plugin(plugin_id)
        if plugin_action in {
            "install_codex_plugin",
            "update_codex_plugin",
            "reinstall_codex_plugin",
        }:
            installed = codex.add_plugin(plugin_id)
            if installed.plugin_id != plugin_id or installed.version != spec.version:
                raise ValueError(
                    f"Codex install result for '{plugin_id}' did not converge to generated version "
                    f"{spec.version}; reported {installed.plugin_id} at {installed.version}."
                )

    _write_ownership(output_dir, specs)
    return actions
