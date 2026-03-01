"""Validation context for sharing state across validators."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_config.adapters.claude import InstalledMarketplace, InstalledPlugin
    from ai_config.types import AIConfig


@dataclass
class ValidationContext:
    """Shared context passed to all validators."""

    config: AIConfig
    config_path: Path
    target_type: str = "claude"

    # Cached data from Claude CLI (lazy-loaded)
    _installed_plugins: list[InstalledPlugin] | None = field(default=None, repr=False)
    _installed_marketplaces: list[InstalledMarketplace] | None = field(default=None, repr=False)
    _known_marketplaces_json: dict | None = field(default=None, repr=False)
    _errors: list[str] = field(default_factory=list, repr=False)

    @property
    def installed_plugins(self) -> list[InstalledPlugin]:
        """Lazy-load installed plugins from Claude CLI."""
        if self._installed_plugins is None:
            from ai_config.adapters import claude

            plugins, errors = claude.list_installed_plugins()
            self._installed_plugins = plugins
            self._errors.extend(errors)
        return self._installed_plugins

    @property
    def installed_marketplaces(self) -> list[InstalledMarketplace]:
        """Lazy-load installed marketplaces from Claude CLI."""
        if self._installed_marketplaces is None:
            from ai_config.adapters import claude

            marketplaces, errors = claude.list_installed_marketplaces()
            self._installed_marketplaces = marketplaces
            self._errors.extend(errors)
        return self._installed_marketplaces

    @property
    def known_marketplaces_json(self) -> dict:
        """Lazy-load Claude's known_marketplaces.json file."""
        if self._known_marketplaces_json is None:
            import json

            known_path = Path.home() / ".claude" / "plugins" / "known_marketplaces.json"
            if known_path.exists():
                try:
                    with open(known_path) as f:
                        self._known_marketplaces_json = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    self._errors.append(f"Failed to read known_marketplaces.json: {e}")
                    self._known_marketplaces_json = {}
            else:
                self._known_marketplaces_json = {}
        return self._known_marketplaces_json

    @property
    def errors(self) -> list[str]:
        """Return accumulated errors from lazy loading."""
        return self._errors
