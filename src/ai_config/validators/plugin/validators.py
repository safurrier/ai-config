"""Plugin validators for ai-config.

Validates plugin.json manifests per the official Claude Code schema:
https://code.claude.com/docs/en/plugins-reference
"""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ai_config.validators.base import ValidationResult

if TYPE_CHECKING:
    from ai_config.validators.context import ValidationContext


# Pattern for valid kebab-case names (lowercase letters, numbers, hyphens)
KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def is_kebab_case(name: str) -> bool:
    """Check if a name is valid kebab-case.

    Valid kebab-case:
    - Lowercase letters and numbers only
    - Words separated by single hyphens
    - No spaces, underscores, or other special characters

    Args:
        name: The name to validate.

    Returns:
        True if valid kebab-case, False otherwise.
    """
    if not name:
        return False
    return bool(KEBAB_CASE_PATTERN.match(name))


class PluginInstalledValidator:
    """Validates that configured plugins are installed in Claude."""

    name = "plugin_installed"
    description = "Validates that plugins in config are installed"

    async def validate(self, context: "ValidationContext") -> list[ValidationResult]:
        """Validate plugin installation status.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        # Get installed plugin IDs
        installed_ids = {p.id for p in context.installed_plugins}

        for target in context.config.targets:
            if target.type != "claude":
                continue

            for plugin in target.config.plugins:
                if plugin.id in installed_ids:
                    results.append(
                        ValidationResult(
                            check_name="plugin_installed",
                            status="pass",
                            message=f"Plugin '{plugin.id}' is installed",
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            check_name="plugin_installed",
                            status="fail",
                            message=f"Plugin '{plugin.id}' is not installed",
                            fix_hint="Run: ai-config sync",
                        )
                    )

        return results


class PluginStateValidator:
    """Validates that plugin enabled/disabled state matches config."""

    name = "plugin_state"
    description = "Validates plugin enabled/disabled state matches configuration"

    async def validate(self, context: "ValidationContext") -> list[ValidationResult]:
        """Validate plugin state.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        # Create lookup map for installed plugins
        installed_map = {p.id: p for p in context.installed_plugins}

        for target in context.config.targets:
            if target.type != "claude":
                continue

            for plugin in target.config.plugins:
                installed = installed_map.get(plugin.id)
                if not installed:
                    # Plugin not installed, skip state check
                    continue

                if plugin.enabled and not installed.enabled:
                    results.append(
                        ValidationResult(
                            check_name="plugin_enabled_state",
                            status="fail",
                            message=f"Plugin '{plugin.id}' should be enabled but is disabled",
                            fix_hint=f"Run: claude plugin enable {plugin.id}",
                        )
                    )
                elif not plugin.enabled and installed.enabled:
                    results.append(
                        ValidationResult(
                            check_name="plugin_enabled_state",
                            status="fail",
                            message=f"Plugin '{plugin.id}' should be disabled but is enabled",
                            fix_hint=f"Run: claude plugin disable {plugin.id}",
                        )
                    )
                else:
                    results.append(
                        ValidationResult(
                            check_name="plugin_enabled_state",
                            status="pass",
                            message=f"Plugin '{plugin.id}' state matches config",
                        )
                    )

        return results


class PluginManifestValidator:
    """Validates that plugins have valid plugin.json manifests.

    Per the official Claude Code plugin schema:
    - name: Required, must be kebab-case (no spaces, no uppercase)
    - version: Optional (semantic version)
    - All paths must start with ./ if specified
    """

    name = "plugin_manifest"
    description = "Validates plugin.json manifest files"

    async def validate(self, context: "ValidationContext") -> list[ValidationResult]:
        """Validate plugin manifest files.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        # Create lookup map for installed plugins
        installed_map = {p.id: p for p in context.installed_plugins}

        for target in context.config.targets:
            if target.type != "claude":
                continue

            for plugin in target.config.plugins:
                installed = installed_map.get(plugin.id)
                if not installed:
                    # Plugin not installed, skip manifest check
                    continue

                install_path = Path(installed.install_path)
                if not install_path.exists():
                    results.append(
                        ValidationResult(
                            check_name="plugin_install_path_exists",
                            status="fail",
                            message=f"Plugin '{plugin.id}' install path missing",
                            details=f"Path: {install_path}",
                        )
                    )
                    continue

                manifest_path = install_path / ".claude-plugin" / "plugin.json"
                if not manifest_path.exists():
                    results.append(
                        ValidationResult(
                            check_name="plugin_manifest_exists",
                            status="fail",
                            message=f"Plugin '{plugin.id}' is missing plugin.json",
                            details=f"Expected at: {manifest_path}",
                            fix_hint="Create a plugin.json manifest file",
                        )
                    )
                    continue

                # Validate manifest JSON
                try:
                    with open(manifest_path) as f:
                        manifest = json.load(f)

                    manifest_results = self._validate_manifest(plugin.id, manifest)
                    results.extend(manifest_results)

                    if not any(r.status == "fail" for r in manifest_results):
                        results.append(
                            ValidationResult(
                                check_name="plugin_manifest_valid",
                                status="pass",
                                message=f"Plugin '{plugin.id}' manifest is valid",
                            )
                        )

                except json.JSONDecodeError as e:
                    results.append(
                        ValidationResult(
                            check_name="plugin_manifest_valid",
                            status="fail",
                            message=f"Plugin '{plugin.id}' has invalid JSON in plugin.json",
                            details=str(e),
                            fix_hint="Fix the JSON syntax in plugin.json",
                        )
                    )
                except OSError as e:
                    results.append(
                        ValidationResult(
                            check_name="plugin_manifest_readable",
                            status="fail",
                            message=f"Failed to read plugin.json for '{plugin.id}'",
                            details=str(e),
                        )
                    )

        return results

    def _validate_manifest(self, plugin_id: str, manifest: dict) -> list[ValidationResult]:
        """Validate plugin manifest content.

        Args:
            plugin_id: The plugin identifier.
            manifest: The parsed plugin.json content.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        if not isinstance(manifest, dict):
            results.append(
                ValidationResult(
                    check_name="plugin_manifest_valid",
                    status="fail",
                    message=f"Plugin '{plugin_id}' manifest is not a JSON object",
                )
            )
            return results

        # Check required name field
        name = manifest.get("name")
        if not name:
            results.append(
                ValidationResult(
                    check_name="plugin_manifest_name_required",
                    status="fail",
                    message=f"Plugin '{plugin_id}' manifest is missing required 'name' field",
                    fix_hint="Add 'name' field to plugin.json",
                )
            )
        elif not isinstance(name, str):
            results.append(
                ValidationResult(
                    check_name="plugin_manifest_name_type",
                    status="fail",
                    message=f"Plugin '{plugin_id}' manifest 'name' must be a string",
                )
            )
        elif not is_kebab_case(name):
            results.append(
                ValidationResult(
                    check_name="plugin_manifest_name_format",
                    status="fail",
                    message=f"Plugin '{plugin_id}' manifest 'name' must be kebab-case",
                    details=f"Got: '{name}'. Use lowercase letters, numbers, and hyphens only.",
                    fix_hint="Rename to use kebab-case (e.g., 'my-plugin' not 'My-Plugin')",
                )
            )

        # Note: version is optional per official schema, so we don't require it

        # Validate component paths if present (should start with ./)
        path_fields = [
            "commands",
            "agents",
            "skills",
            "hooks",
            "mcpServers",
            "outputStyles",
            "lspServers",
        ]
        for field in path_fields:
            value = manifest.get(field)
            if value is not None:
                if isinstance(value, str):
                    paths = [value]
                elif isinstance(value, list):
                    paths = value
                else:
                    paths = []
                for path in paths:
                    is_relative = path.startswith("./")
                    is_variable = path.startswith("${")
                    if isinstance(path, str) and not is_relative and not is_variable:
                        results.append(
                            ValidationResult(
                                check_name="plugin_manifest_path_format",
                                status="warn",
                                message=(
                                    f"Plugin '{plugin_id}' manifest '{field}' "
                                    "paths should start with './'"
                                ),
                                details=f"Got: '{path}'",
                            )
                        )

        return results
