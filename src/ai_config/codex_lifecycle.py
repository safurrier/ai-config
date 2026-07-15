"""Declarative lifecycle for ai-config-owned Codex plugin packages."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_config.adapters.codex import CodexCLI
from ai_config.converters.codex_package import CODEX_OWNERSHIP_FILE, CodexPackageSpec

_OWNERSHIP_VERSION = 1


@dataclass(frozen=True)
class CodexLifecycleAction:
    """One planned or completed Codex CLI lifecycle action."""

    action: str
    target: str
    reason: str


def _load_ownership(output_dir: Path) -> dict[str, dict[str, str]]:
    path = output_dir / CODEX_OWNERSHIP_FILE
    if not path.exists():
        return {}
    try:
        payload: object = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
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
    parsed: dict[str, dict[str, str]] = {}
    for plugin_id, entry in packages.items():
        if not isinstance(plugin_id, str) or not isinstance(entry, dict):
            raise ValueError(f"Invalid ai-config Codex ownership entry at {path}")
        required = ("marketplace_name", "marketplace_path", "version")
        if not all(isinstance(entry.get(key), str) for key in required):
            raise ValueError(
                f"Incomplete ai-config Codex ownership entry for {plugin_id} at {path}"
            )
        parsed[plugin_id] = {key: entry[key] for key in required}
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
    path.write_text(
        json.dumps({"version": _OWNERSHIP_VERSION, "packages": packages}, indent=2) + "\n"
    )


def _entry_by(entries: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {value: entry for entry in entries if isinstance((value := entry.get(key)), str)}


def _marketplace_root(entry: dict[str, Any]) -> str | None:
    for key in ("root", "installedRoot", "path"):
        value = entry.get(key)
        if isinstance(value, str):
            return str(Path(value).resolve())
    source = entry.get("source")
    if isinstance(source, dict):
        value = source.get("source") or source.get("path")
        if isinstance(value, str):
            return str(Path(value).resolve())
    return None


def sync_codex_packages(
    specs: list[CodexPackageSpec],
    *,
    output_dir: Path,
    refreshed_plugin_ids: set[str],
    dry_run: bool = False,
    cli: CodexCLI | None = None,
) -> list[CodexLifecycleAction]:
    """Converge generated Codex packages without touching unrelated Codex state."""
    previous = _load_ownership(output_dir)
    desired = {spec.plugin_id: spec for spec in specs}
    actions: list[CodexLifecycleAction] = []

    stale_ids = sorted(set(previous) - set(desired))
    for plugin_id in stale_ids:
        actions.append(
            CodexLifecycleAction(
                "remove_codex_plugin", plugin_id, "Source plugin is no longer configured"
            )
        )
        actions.append(
            CodexLifecycleAction(
                "remove_codex_marketplace",
                previous[plugin_id]["marketplace_name"],
                "Generated marketplace is no longer configured",
            )
        )

    for spec in sorted(specs, key=lambda item: item.plugin_id):
        old = previous.get(spec.plugin_id)
        if old is None:
            actions.extend(
                [
                    CodexLifecycleAction(
                        "register_codex_marketplace",
                        spec.marketplace_name,
                        f"Register generated marketplace at {spec.marketplace_path}",
                    ),
                    CodexLifecycleAction(
                        "install_codex_plugin",
                        spec.plugin_id,
                        "Install and enable generated Codex plugin package",
                    ),
                ]
            )
        elif spec.plugin_id in refreshed_plugin_ids:
            actions.append(
                CodexLifecycleAction(
                    "update_codex_plugin",
                    spec.plugin_id,
                    "Generated package content changed; reinstall through Codex CLI",
                )
            )

    if dry_run:
        return actions

    codex = cli or CodexCLI()
    marketplaces = _entry_by(codex.list_marketplaces(), "name")
    plugins = _entry_by(codex.list_plugins(), "pluginId")

    # Preflight every owned removal before mutating anything. A user may have replaced an
    # ai-config marketplace with an unrelated source that happens to reuse its old name.
    for plugin_id in stale_ids:
        entry = previous[plugin_id]
        marketplace = marketplaces.get(entry["marketplace_name"])
        if marketplace is None:
            continue
        expected_root = str(Path(entry["marketplace_path"]).resolve())
        actual_root = _marketplace_root(marketplace)
        if actual_root != expected_root:
            rendered_root = actual_root or "<unknown>"
            raise ValueError(
                f"Codex marketplace ownership changed for '{entry['marketplace_name']}': "
                f"registered root is {rendered_root}, expected {expected_root}. "
                "ai-config will not remove the marketplace or plugin. Resolve the collision and retry."
            )

    for plugin_id in stale_ids:
        entry = previous[plugin_id]
        if plugin_id in plugins:
            codex.remove_plugin(plugin_id)
        marketplace_name = entry["marketplace_name"]
        if marketplace_name in marketplaces:
            codex.remove_marketplace(marketplace_name)
        marketplace_path = Path(entry["marketplace_path"])
        owned_root = (output_dir / ".ai-config" / "codex" / "marketplaces").resolve()
        if marketplace_path != owned_root and owned_root in marketplace_path.parents:
            shutil.rmtree(marketplace_path, ignore_errors=True)

    for spec in sorted(specs, key=lambda item: item.plugin_id):
        marketplace = marketplaces.get(spec.marketplace_name)
        if marketplace is not None:
            actual_root = _marketplace_root(marketplace)
            if actual_root != str(spec.marketplace_path):
                rendered_root = actual_root or "<unknown>"
                raise ValueError(
                    f"Codex marketplace name collision for '{spec.marketplace_name}': "
                    f"registered root is {rendered_root}, expected {spec.marketplace_path}. "
                    "ai-config will not modify the unrelated marketplace. Rename/remove the collision and retry."
                )
        else:
            codex.add_marketplace(str(spec.marketplace_path))
            marketplaces[spec.marketplace_name] = {"name": spec.marketplace_name}

        installed = plugins.get(spec.plugin_id)
        needs_reinstall = spec.plugin_id in refreshed_plugin_ids or installed is None
        if installed is not None and installed.get("enabled") is not True:
            needs_reinstall = True
        if installed is not None and needs_reinstall:
            codex.remove_plugin(spec.plugin_id)
            installed = None
        if installed is None:
            codex.add_plugin(spec.plugin_id)

    _write_ownership(output_dir, specs)
    return actions
