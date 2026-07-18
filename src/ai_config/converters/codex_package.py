"""Naming and ownership paths for generated Codex plugin packages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ai_config.semver import SemanticVersion

CODEX_OUTPUT_ROOT = Path(".ai-config") / "codex"
CODEX_OWNERSHIP_FILE = CODEX_OUTPUT_ROOT / "ownership.json"


@dataclass(frozen=True)
class CodexPackageSpec:
    """Deterministic identity and paths for one ai-config-owned Codex package."""

    plugin_name: str
    version: str
    output_dir: Path
    source_plugin_id: str | None = None

    def __post_init__(self) -> None:
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.plugin_name) is None:
            raise ValueError(
                f"Invalid normalized Codex plugin identity '{self.plugin_name}': "
                "expected lowercase kebab-case."
            )
        SemanticVersion.parse(self.version, context=f"Codex package version for {self.plugin_name}")

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
        return self.output_dir.expanduser().resolve() / self.marketplace_relative_path

    @property
    def package_relative_path(self) -> Path:
        return self.marketplace_relative_path / "plugins" / self.plugin_name


def codex_package_spec(
    plugin_name: str,
    version: str | None,
    output_dir: Path,
    *,
    source_plugin_id: str | None = None,
) -> CodexPackageSpec:
    """Build the deterministic package spec used by emit and lifecycle code."""
    return CodexPackageSpec(
        plugin_name=plugin_name,
        version=version or "0.0.0",
        output_dir=output_dir,
        source_plugin_id=source_plugin_id,
    )
