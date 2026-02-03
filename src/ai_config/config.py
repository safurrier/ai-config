"""Configuration loading and validation for ai-config."""

from pathlib import Path
from typing import Any

import yaml

from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    MarketplaceConfig,
    PluginConfig,
    PluginSource,
    TargetConfig,
)


class ConfigError(Exception):
    """Base exception for configuration errors."""


class ConfigNotFoundError(ConfigError):
    """Raised when config file is not found."""


class ConfigParseError(ConfigError):
    """Raised when YAML parsing fails."""


class ConfigValidationError(ConfigError):
    """Raised when config schema validation fails."""


DEFAULT_CONFIG_PATHS = [
    Path(".ai-config/config.yaml"),
    Path(".ai-config/config.yml"),
    Path.home() / ".ai-config" / "config.yaml",
    Path.home() / ".ai-config" / "config.yml",
]


def find_config_file(config_path: Path | None = None) -> Path:
    """Find the config file to use.

    Args:
        config_path: Explicit path to config file. If None, searches default locations.

    Returns:
        Path to the config file.

    Raises:
        ConfigNotFoundError: If no config file is found.
    """
    if config_path is not None:
        if config_path.exists():
            return config_path
        raise ConfigNotFoundError(f"Config file not found: {config_path}")

    for path in DEFAULT_CONFIG_PATHS:
        if path.exists():
            return path

    locations = "\n  ".join(str(p) for p in DEFAULT_CONFIG_PATHS)
    raise ConfigNotFoundError(f"No config file found. Searched:\n  {locations}")


def _parse_marketplace(
    name: str, data: dict[str, Any], base_dir: Path | None = None
) -> MarketplaceConfig:
    """Parse a single marketplace config from raw dict.

    Args:
        name: Marketplace name.
        data: Raw dict from YAML.
        base_dir: Base directory for resolving relative paths.
    """
    if not isinstance(data, dict):
        raise ConfigValidationError(f"Marketplace '{name}' must be a dict, got: {type(data)}")

    source_str = data.get("source")
    try:
        source = PluginSource(source_str)
    except ValueError as e:
        valid_sources = [s.value for s in PluginSource]
        raise ConfigValidationError(
            f"Marketplace '{name}' source must be one of {valid_sources}, got: {source_str}"
        ) from e

    if source == PluginSource.GITHUB:
        repo = data.get("repo")
        if not repo:
            raise ConfigValidationError(
                f"Marketplace '{name}' must have 'repo' field for github source"
            )
        return MarketplaceConfig(source=source, repo=repo)
    else:  # local
        path_str = data.get("path")
        if not path_str:
            raise ConfigValidationError(
                f"Marketplace '{name}' must have 'path' field for local source"
            )

        # Resolve relative paths against base_dir
        path = Path(path_str)
        if not path.is_absolute() and base_dir is not None:
            path = (base_dir / path).resolve()
        else:
            path = path.resolve()

        return MarketplaceConfig(source=source, path=str(path))


def _parse_plugin(data: dict[str, Any], index: int) -> PluginConfig:
    """Parse a single plugin config from raw dict."""
    if not isinstance(data, dict):
        raise ConfigValidationError(f"Plugin at index {index} must be a dict, got: {type(data)}")

    plugin_id = data.get("id")
    if not plugin_id:
        raise ConfigValidationError(f"Plugin at index {index} must have 'id' field")

    scope = data.get("scope", "user")
    if scope not in ("user", "project", "local"):
        raise ConfigValidationError(
            f"Plugin '{plugin_id}' scope must be 'user', 'project', or 'local', got: {scope}"
        )

    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigValidationError(
            f"Plugin '{plugin_id}' enabled must be boolean, got: {type(enabled)}"
        )

    return PluginConfig(id=plugin_id, scope=scope, enabled=enabled)


def _parse_claude_config(data: dict[str, Any], base_dir: Path | None = None) -> ClaudeTargetConfig:
    """Parse Claude-specific target config.

    Args:
        data: Raw dict from YAML.
        base_dir: Base directory for resolving relative paths.
    """
    if not isinstance(data, dict):
        raise ConfigValidationError(f"Claude config must be a dict, got: {type(data)}")

    marketplaces: dict[str, MarketplaceConfig] = {}
    raw_marketplaces = data.get("marketplaces", {})
    if raw_marketplaces:
        if not isinstance(raw_marketplaces, dict):
            raise ConfigValidationError(
                f"Marketplaces must be a dict, got: {type(raw_marketplaces)}"
            )
        for name, marketplace_data in raw_marketplaces.items():
            marketplaces[name] = _parse_marketplace(name, marketplace_data, base_dir)

    plugins: list[PluginConfig] = []
    raw_plugins = data.get("plugins", [])
    if raw_plugins:
        if not isinstance(raw_plugins, list):
            raise ConfigValidationError(f"Plugins must be a list, got: {type(raw_plugins)}")
        for i, plugin_data in enumerate(raw_plugins):
            plugins.append(_parse_plugin(plugin_data, i))

    return ClaudeTargetConfig(marketplaces=marketplaces, plugins=tuple(plugins))


def _parse_target(data: dict[str, Any], index: int, base_dir: Path | None = None) -> TargetConfig:
    """Parse a single target config from raw dict.

    Args:
        data: Raw dict from YAML.
        index: Index in targets list for error messages.
        base_dir: Base directory for resolving relative paths.
    """
    if not isinstance(data, dict):
        raise ConfigValidationError(f"Target at index {index} must be a dict, got: {type(data)}")

    target_type = data.get("type")
    if target_type != "claude":
        raise ConfigValidationError(
            f"Target at index {index} type must be 'claude', got: {target_type}"
        )

    config_data = data.get("config", {})
    claude_config = _parse_claude_config(config_data, base_dir)

    return TargetConfig(type=target_type, config=claude_config)


def load_config(config_path: Path | None = None) -> AIConfig:
    """Load and validate ai-config from a YAML file.

    Args:
        config_path: Explicit path to config file. If None, searches default locations.

    Returns:
        Validated AIConfig object.

    Raises:
        ConfigNotFoundError: If config file is not found.
        ConfigParseError: If YAML parsing fails.
        ConfigValidationError: If schema validation fails.
    """
    path = find_config_file(config_path)

    try:
        with open(path) as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigParseError(f"Failed to parse YAML from {path}: {e}") from e

    if raw_config is None:
        raise ConfigValidationError(f"Config file is empty: {path}")

    if not isinstance(raw_config, dict):
        raise ConfigValidationError(f"Config must be a dict, got: {type(raw_config)}")

    version = raw_config.get("version")
    if version != 1:
        raise ConfigValidationError(f"Config version must be 1, got: {version}")

    # Resolve the base directory for relative paths
    # Use the parent of the config file, then go up one more level
    # (config is in .ai-config/config.yaml, so base is the repo root)
    base_dir = path.resolve().parent.parent

    targets: list[TargetConfig] = []
    raw_targets = raw_config.get("targets", [])
    if raw_targets:
        if not isinstance(raw_targets, list):
            raise ConfigValidationError(f"Targets must be a list, got: {type(raw_targets)}")
        for i, target_data in enumerate(raw_targets):
            targets.append(_parse_target(target_data, i, base_dir))

    return AIConfig(version=version, targets=tuple(targets))


def validate_marketplace_references(config: AIConfig) -> list[str]:
    """Validate that all plugin marketplace references exist.

    Args:
        config: The AIConfig to validate.

    Returns:
        List of validation error messages (empty if valid).
    """
    errors: list[str] = []

    for target in config.targets:
        if target.type == "claude":
            available_marketplaces = set(target.config.marketplaces.keys())
            for plugin in target.config.plugins:
                if plugin.marketplace and plugin.marketplace not in available_marketplaces:
                    errors.append(
                        f"Plugin '{plugin.id}' references undefined marketplace "
                        f"'{plugin.marketplace}'. Available: {sorted(available_marketplaces)}"
                    )

    return errors
