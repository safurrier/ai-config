"""Filesystem observation and persistence helpers for sync.

This module owns state access below orchestration so planning and execution modules do not import
the public :mod:`ai_config.operations` entry point.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_config.adapters import claude
from ai_config.converters.codex_package import CodexPackageSpec
from ai_config.pi_ownership import load_pi_ownership
from ai_config.types import ClaudeTargetConfig, ConversionConfig, PluginConfig, PluginSource

_CONVERSION_CACHE_VERSION = 7


def conversion_cache_path() -> Path:
    return Path.home() / ".ai-config" / "cache" / "conversion-hashes.json"


def load_conversion_cache() -> dict:
    cache_path = conversion_cache_path()
    if not cache_path.exists():
        return {"version": _CONVERSION_CACHE_VERSION, "entries": {}, "codex_output_dirs": []}
    try:
        raw = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Invalid conversion cache at {cache_path}; clear the cache and retry: {error}"
        ) from error
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid conversion cache object at {cache_path}; clear it and retry")
    if raw.get("version") != _CONVERSION_CACHE_VERSION:
        return {"version": _CONVERSION_CACHE_VERSION, "entries": {}, "codex_output_dirs": []}
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


def save_conversion_cache(cache: dict) -> None:
    cache_path = conversion_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True))


def conversion_signature(conversion: ConversionConfig, output_dir: Path) -> str:
    return json.dumps(
        {
            "targets": sorted(conversion.targets),
            "scope": conversion.scope,
            "output_dir": str(output_dir),
        },
        sort_keys=True,
    )


def compute_plugin_hash(plugin_path: Path) -> str | None:
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


def resolve_local_marketplace_plugin_path(marketplace_root: Path, plugin_name: str) -> Path | None:
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
    return fallback_path if fallback_path.is_dir() else None


def resolve_plugin_conversion_path(
    config: ClaudeTargetConfig,
    plugin_config: PluginConfig,
    installed: claude.InstalledPlugin | None,
) -> Path | None:
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
    return resolve_local_marketplace_plugin_path(Path(marketplace.path), plugin_config.plugin_name)


def compute_owned_codex_hash(spec: CodexPackageSpec) -> str | None:
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
        return hasher.hexdigest()
    except OSError:
        return None


def resolve_conversion_output_dir(conversion: ConversionConfig) -> Path:
    if conversion.output_dir:
        return Path(conversion.output_dir)
    return Path.home() if conversion.scope == "user" else Path.cwd()


def owned_codex_output_dirs(conversion: ConversionConfig | None, cache: dict) -> list[Path]:
    candidates: set[Path] = {Path.cwd().resolve(), Path.home().resolve()}
    if conversion is not None:
        candidates.add(resolve_conversion_output_dir(conversion).resolve())
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
    return sorted(
        (
            candidate
            for candidate in candidates
            if (candidate / ".ai-config" / "codex" / "ownership.json").is_file()
        ),
        key=lambda item: item.as_posix(),
    )


def pi_root_has_ownership(root: Path) -> bool:
    try:
        return bool(load_pi_ownership(root))
    except ValueError:
        return True
