"""Marketplace validators for ai-config.

Validates marketplace.json manifests per the official Claude Code schema:
https://code.claude.com/docs/en/plugin-marketplaces
"""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ai_config.types import PluginSource
from ai_config.validators.base import ValidationResult

if TYPE_CHECKING:
    from ai_config.validators.context import ValidationContext


# Reserved marketplace names that cannot be used
RESERVED_MARKETPLACE_NAMES = frozenset(
    [
        "claude-code-marketplace",
        "claude-code-plugins",
        "claude-plugins-official",
        "anthropic-marketplace",
        "anthropic-plugins",
        "agent-skills",
        "life-sciences",
    ]
)

# Pattern for valid kebab-case names
KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def is_kebab_case(name: str) -> bool:
    """Check if a name is valid kebab-case."""
    if not name:
        return False
    return bool(KEBAB_CASE_PATTERN.match(name))


class MarketplacePathValidator:
    """Validates that local marketplace paths exist."""

    name = "marketplace_path"
    description = "Validates that local marketplace directories exist"

    async def validate(self, context: "ValidationContext") -> list[ValidationResult]:
        """Validate marketplace path existence.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        for target in context.config.targets:
            if target.type != "claude":
                continue

            for mp_name, mp_config in target.config.marketplaces.items():
                # Only check local marketplaces
                if mp_config.source != PluginSource.LOCAL:
                    continue

                mp_path = Path(mp_config.path)
                if mp_path.exists():
                    results.append(
                        ValidationResult(
                            check_name="marketplace_path_exists",
                            status="pass",
                            message=f"Marketplace '{mp_name}' path exists: {mp_path}",
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            check_name="marketplace_path_exists",
                            status="fail",
                            message=f"Marketplace '{mp_name}' path does not exist: {mp_path}",
                            details=f"Expected directory at: {mp_path}",
                            fix_hint=f"Create the directory: mkdir -p {mp_path}",
                        )
                    )

        return results


class MarketplaceManifestValidator:
    """Validates that local marketplaces have valid marketplace.json manifests.

    Per the official Claude Code marketplace schema:
    - name: Required, kebab-case, not a reserved name
    - owner: Required, must have 'name' field
    - plugins: Required, must be an array of plugin entries
    - Each plugin entry must have 'name' and 'source'
    """

    name = "marketplace_manifest"
    description = "Validates marketplace.json manifest files"

    async def validate(self, context: "ValidationContext") -> list[ValidationResult]:
        """Validate marketplace manifest files.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        for target in context.config.targets:
            if target.type != "claude":
                continue

            for mp_name, mp_config in target.config.marketplaces.items():
                # Only check local marketplaces
                if mp_config.source != PluginSource.LOCAL:
                    continue

                mp_path = Path(mp_config.path)
                if not mp_path.exists():
                    # Path validation will catch this
                    continue

                manifest_path = mp_path / ".claude-plugin" / "marketplace.json"
                if not manifest_path.exists():
                    results.append(
                        ValidationResult(
                            check_name="marketplace_manifest_exists",
                            status="fail",
                            message=f"Marketplace '{mp_name}' is missing marketplace.json",
                            details=f"Expected file at: {manifest_path}",
                            fix_hint=(
                                f'Create manifest with: {{"name": "{mp_name}", '
                                '"owner": {"name": "..."}, "plugins": []}'
                            ),
                        )
                    )
                    continue

                # Validate manifest JSON
                try:
                    with open(manifest_path) as f:
                        manifest = json.load(f)

                    manifest_results = self._validate_manifest(mp_name, manifest)
                    results.extend(manifest_results)

                    if not any(r.status == "fail" for r in manifest_results):
                        results.append(
                            ValidationResult(
                                check_name="marketplace_manifest_valid",
                                status="pass",
                                message=f"Marketplace '{mp_name}' manifest is valid",
                            )
                        )

                except json.JSONDecodeError as e:
                    results.append(
                        ValidationResult(
                            check_name="marketplace_manifest_valid",
                            status="fail",
                            message=f"Marketplace '{mp_name}' has invalid JSON in marketplace.json",
                            details=str(e),
                            fix_hint="Fix the JSON syntax in marketplace.json",
                        )
                    )
                except OSError as e:
                    results.append(
                        ValidationResult(
                            check_name="marketplace_manifest_readable",
                            status="fail",
                            message=f"Failed to read marketplace.json for '{mp_name}'",
                            details=str(e),
                        )
                    )

        return results

    def _validate_manifest(self, mp_name: str, manifest: dict) -> list[ValidationResult]:
        """Validate marketplace manifest content.

        Args:
            mp_name: The marketplace name from config.
            manifest: The parsed marketplace.json content.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        if not isinstance(manifest, dict):
            results.append(
                ValidationResult(
                    check_name="marketplace_manifest_valid",
                    status="fail",
                    message=f"Marketplace '{mp_name}' manifest is not a JSON object",
                )
            )
            return results

        # Check required 'name' field
        name = manifest.get("name")
        if not name:
            results.append(
                ValidationResult(
                    check_name="marketplace_manifest_name_required",
                    status="fail",
                    message=f"Marketplace '{mp_name}' manifest is missing required 'name' field",
                    fix_hint="Add 'name' field to marketplace.json",
                )
            )
        elif not isinstance(name, str):
            results.append(
                ValidationResult(
                    check_name="marketplace_manifest_name_type",
                    status="fail",
                    message=f"Marketplace '{mp_name}' manifest 'name' must be a string",
                )
            )
        else:
            # Check kebab-case
            if not is_kebab_case(name):
                results.append(
                    ValidationResult(
                        check_name="marketplace_manifest_name_format",
                        status="fail",
                        message=f"Marketplace '{mp_name}' manifest 'name' must be kebab-case",
                        details=f"Got: '{name}'. Use lowercase letters, numbers, and hyphens only.",
                    )
                )

            # Check reserved names
            if name.lower() in RESERVED_MARKETPLACE_NAMES:
                results.append(
                    ValidationResult(
                        check_name="marketplace_manifest_name_reserved",
                        status="fail",
                        message=f"Marketplace '{mp_name}' manifest uses reserved name: '{name}'",
                        details=f"Reserved names: {', '.join(sorted(RESERVED_MARKETPLACE_NAMES))}",
                        fix_hint="Choose a different marketplace name",
                    )
                )

        # Check required 'owner' field
        owner = manifest.get("owner")
        if owner is None:
            results.append(
                ValidationResult(
                    check_name="marketplace_manifest_owner_required",
                    status="fail",
                    message=f"Marketplace '{mp_name}' manifest is missing required 'owner' field",
                    fix_hint='Add \'owner\': {"name": "Your Name"} to marketplace.json',
                )
            )
        elif not isinstance(owner, dict):
            results.append(
                ValidationResult(
                    check_name="marketplace_manifest_owner_type",
                    status="fail",
                    message=f"Marketplace '{mp_name}' manifest 'owner' must be an object",
                )
            )
        elif not owner.get("name"):
            results.append(
                ValidationResult(
                    check_name="marketplace_manifest_owner_name_required",
                    status="fail",
                    message=(
                        f"Marketplace '{mp_name}' manifest 'owner' is missing required 'name' field"
                    ),
                    fix_hint='Add \'name\' to owner: {"owner": {"name": "Your Name"}}',
                )
            )

        # Check required 'plugins' field
        plugins = manifest.get("plugins")
        if plugins is None:
            results.append(
                ValidationResult(
                    check_name="marketplace_manifest_plugins_required",
                    status="fail",
                    message=f"Marketplace '{mp_name}' manifest is missing required 'plugins' field",
                    fix_hint="Add 'plugins': [] to marketplace.json",
                )
            )
        elif not isinstance(plugins, list):
            results.append(
                ValidationResult(
                    check_name="marketplace_manifest_plugins_type",
                    status="fail",
                    message=f"Marketplace '{mp_name}' manifest 'plugins' must be an array (list)",
                )
            )
        else:
            # Validate each plugin entry
            for i, plugin_entry in enumerate(plugins):
                plugin_results = self._validate_plugin_entry(mp_name, i, plugin_entry)
                results.extend(plugin_results)

        return results

    def _validate_plugin_entry(
        self, mp_name: str, index: int, entry: dict
    ) -> list[ValidationResult]:
        """Validate a plugin entry in the plugins array.

        Args:
            mp_name: The marketplace name.
            index: Index of the plugin entry.
            entry: The plugin entry dict.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        if not isinstance(entry, dict):
            results.append(
                ValidationResult(
                    check_name="marketplace_plugin_entry_type",
                    status="fail",
                    message=f"Marketplace '{mp_name}' plugins[{index}] must be an object",
                )
            )
            return results

        # Check required 'name' field
        if not entry.get("name"):
            results.append(
                ValidationResult(
                    check_name="marketplace_plugin_name_required",
                    status="fail",
                    message=(
                        f"Marketplace '{mp_name}' plugins[{index}] is missing required 'name' field"
                    ),
                )
            )

        # Check required 'source' field
        if not entry.get("source"):
            results.append(
                ValidationResult(
                    check_name="marketplace_plugin_source_required",
                    status="fail",
                    message=(
                        f"Marketplace '{mp_name}' plugins[{index}] "
                        "is missing required 'source' field"
                    ),
                )
            )

        return results


class PathDriftValidator:
    """Validates that config marketplace paths match Claude's known_marketplaces.json."""

    name = "path_drift"
    description = "Detects when marketplace paths in config differ from Claude's registered paths"

    async def validate(self, context: "ValidationContext") -> list[ValidationResult]:
        """Check for path drift between config and Claude's state.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        # Get Claude's known marketplaces
        known_marketplaces = context.known_marketplaces_json

        for target in context.config.targets:
            if target.type != "claude":
                continue

            for mp_name, mp_config in target.config.marketplaces.items():
                # Only check local marketplaces for path drift
                if mp_config.source != PluginSource.LOCAL:
                    continue

                config_path = Path(mp_config.path).resolve()

                # Check if marketplace is registered in Claude
                if mp_name not in known_marketplaces:
                    results.append(
                        ValidationResult(
                            check_name="marketplace_registered",
                            status="warn",
                            message=f"Marketplace '{mp_name}' is not registered in Claude",
                            details="Marketplace is in config but not in known_marketplaces.json",
                            fix_hint="Run: ai-config sync",
                        )
                    )
                    continue

                # Check for path drift
                claude_mp = known_marketplaces[mp_name]
                claude_path_str = claude_mp.get("path", "")
                if claude_path_str:
                    claude_path = Path(claude_path_str).resolve()

                    if config_path != claude_path:
                        results.append(
                            ValidationResult(
                                check_name="marketplace_path_drift",
                                status="fail",
                                message=f"Path drift detected for marketplace '{mp_name}'",
                                details=(f"Config path: {config_path}\nClaude path: {claude_path}"),
                                fix_hint=(
                                    f"Run: claude plugin marketplace remove {mp_name} && "
                                    f"claude plugin marketplace add {config_path}"
                                ),
                            )
                        )
                    else:
                        results.append(
                            ValidationResult(
                                check_name="marketplace_path_drift",
                                status="pass",
                                message=f"Marketplace '{mp_name}' path matches registration",
                            )
                        )

        return results
