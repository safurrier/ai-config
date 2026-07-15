"""Naming and ownership paths for generated Codex plugin packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CODEX_OUTPUT_ROOT = Path(".ai-config") / "codex"
CODEX_OWNERSHIP_FILE = CODEX_OUTPUT_ROOT / "ownership.json"


@dataclass(frozen=True)
class CodexPackageSpec:
    """Deterministic identity and paths for one ai-config-owned Codex package."""

    plugin_name: str
    version: str
    output_dir: Path

    @property
    def marketplace_name(self) -> str:
        return f"ai-config-{self.plugin_name}"

    @property
    def plugin_id(self) -> str:
        return f"{self.plugin_name}@{self.marketplace_name}"

    @property
    def marketplace_relative_path(self) -> Path:
        return CODEX_OUTPUT_ROOT / "marketplaces" / self.marketplace_name

    @property
    def marketplace_path(self) -> Path:
        return (self.output_dir / self.marketplace_relative_path).resolve()

    @property
    def package_relative_path(self) -> Path:
        return self.marketplace_relative_path / "plugins" / self.plugin_name


def codex_package_spec(plugin_name: str, version: str | None, output_dir: Path) -> CodexPackageSpec:
    """Build the deterministic package spec used by emit and lifecycle code."""
    return CodexPackageSpec(
        plugin_name=plugin_name,
        version=version or "0.0.0",
        output_dir=output_dir,
    )
