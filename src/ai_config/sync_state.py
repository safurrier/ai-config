"""Filesystem observation and persistence helpers for sync.

This module owns state access below orchestration so planning and execution modules do not import
the public :mod:`ai_config.operations` entry point.
"""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

from ai_config.adapters import claude
from ai_config.converters.codex_package import CodexPackageSpec
from ai_config.pi_ownership import load_pi_ownership
from ai_config.source_safety import ContainedSource, SourceSafetyError
from ai_config.types import ClaudeTargetConfig, ConversionConfig, PluginConfig, PluginSource

_CONVERSION_CACHE_VERSION = 8


def conversion_cache_path() -> Path:
    return Path.home() / ".ai-config" / "cache" / "conversion-hashes.json"


def _validated_cached_output_dirs(raw: dict, key: str, cache_path: Path) -> list[str]:
    value = raw.get(key, [])
    label = "Codex" if key == "codex_output_dirs" else "Pi"
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item or "\0" in item for item in value
    ):
        raise ValueError(
            f"Invalid conversion cache {label} output roots at {cache_path}; clear it and retry"
        )
    return value


def load_conversion_cache() -> dict:
    cache_path = conversion_cache_path()
    empty = {
        "version": _CONVERSION_CACHE_VERSION,
        "entries": {},
        "codex_output_dirs": [],
        "pi_output_dirs": [],
    }
    if not cache_path.exists():
        return empty
    try:
        raw = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Invalid conversion cache at {cache_path}; clear the cache and retry: {error}"
        ) from error
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid conversion cache object at {cache_path}; clear it and retry")
    codex_dirs = _validated_cached_output_dirs(raw, "codex_output_dirs", cache_path)
    pi_dirs = _validated_cached_output_dirs(raw, "pi_output_dirs", cache_path)
    if raw.get("version") == 7:
        # Content hashes changed in v8, but ownership cleanup still needs prior custom roots.
        return {
            "version": _CONVERSION_CACHE_VERSION,
            "entries": {},
            "codex_output_dirs": codex_dirs,
            "pi_output_dirs": pi_dirs,
        }
    if raw.get("version") != _CONVERSION_CACHE_VERSION:
        return empty
    if not isinstance(raw.get("entries"), dict):
        raise ValueError(f"Invalid conversion cache entries at {cache_path}; clear it and retry")
    raw["codex_output_dirs"] = codex_dirs
    raw["pi_output_dirs"] = pi_dirs
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
    """Hash every safely readable plugin byte, failing closed on unsafe entries."""
    hasher = hashlib.sha256()
    try:
        source = ContainedSource(plugin_path)
        for relative in source.walk_all_files(context="plugin hash"):
            item = source.read_file(relative, context="plugin hash")
            hasher.update(relative.as_posix().encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(b"x" if item.executable else b"-")
            hasher.update(len(item.content).to_bytes(8, "big"))
            hasher.update(item.content)
        return hasher.hexdigest()
    except (OSError, SourceSafetyError):
        return None


def _lexical_regular_directory(path: Path) -> Path | None:
    """Return an absolute lexical directory path, rejecting a symlink at the selection root."""
    try:
        selected = path.expanduser().absolute()
        selected_stat = selected.lstat()
    except (OSError, RuntimeError, ValueError):
        return None
    if stat.S_ISLNK(selected_stat.st_mode) or not stat.S_ISDIR(selected_stat.st_mode):
        return None
    return selected


def resolve_local_marketplace_plugin_path(marketplace_root: Path, plugin_name: str) -> Path | None:
    for manifest_path in (
        marketplace_root / ".claude-plugin" / "marketplace.json",
        marketplace_root / "marketplace.json",
    ):
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        plugins = manifest.get("plugins", [])
        if not isinstance(plugins, list):
            continue
        for entry in plugins:
            if not isinstance(entry, dict) or entry.get("name") != plugin_name:
                continue
            source = entry.get("source")
            if not isinstance(source, str) or "\0" in source:
                continue
            try:
                source_path = Path(source).expanduser()
            except (RuntimeError, ValueError):
                continue
            if not source_path.is_absolute():
                source_path = marketplace_root / source_path
            selected = _lexical_regular_directory(source_path)
            if selected is not None:
                return selected
    return _lexical_regular_directory(marketplace_root / plugin_name)


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
