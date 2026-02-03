"""Tests for ai_config.validators.plugin module.

Tests plugin manifest validation per the official Claude Code schema:
https://code.claude.com/docs/en/plugins-reference
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_config.adapters.claude import InstalledPlugin
from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    MarketplaceConfig,
    PluginConfig,
    PluginSource,
    TargetConfig,
)
from ai_config.validators.plugin.validators import (
    PluginInstalledValidator,
    PluginManifestValidator,
    PluginStateValidator,
    is_kebab_case,
)


@pytest.fixture
def mock_context(tmp_path: Path) -> MagicMock:
    """Create a mock validation context."""
    context = MagicMock()
    context.config_path = tmp_path / ".ai-config" / "config.yaml"
    return context


class TestPluginInstalledValidator:
    """Tests for PluginInstalledValidator."""

    @pytest.fixture
    def validator(self) -> PluginInstalledValidator:
        return PluginInstalledValidator()

    @pytest.mark.asyncio
    async def test_plugin_installed_passes(
        self,
        validator: PluginInstalledValidator,
        mock_context: MagicMock,
    ) -> None:
        """Plugin that is installed should pass."""
        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin@test-marketplace"),)
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin@test-marketplace",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path="/path/to/plugin",
            )
        ]

        results = await validator.validate(mock_context)
        passed = [r for r in results if r.status == "pass"]
        assert len(passed) >= 1

    @pytest.mark.asyncio
    async def test_plugin_not_installed_fails(
        self,
        validator: PluginInstalledValidator,
        mock_context: MagicMock,
    ) -> None:
        """Plugin that is not installed should fail."""
        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="missing-plugin@test-marketplace"),)
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = []

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "not installed" in failures[0].message.lower()


class TestPluginStateValidator:
    """Tests for PluginStateValidator."""

    @pytest.fixture
    def validator(self) -> PluginStateValidator:
        return PluginStateValidator()

    @pytest.mark.asyncio
    async def test_enabled_state_matches(
        self,
        validator: PluginStateValidator,
        mock_context: MagicMock,
    ) -> None:
        """Plugin enabled state matches config should pass."""
        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin", enabled=True),)
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path="/path",
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 0

    @pytest.mark.asyncio
    async def test_enabled_state_mismatch_should_be_enabled(
        self,
        validator: PluginStateValidator,
        mock_context: MagicMock,
    ) -> None:
        """Plugin should be enabled but is disabled should fail."""
        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin", enabled=True),)
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=False,  # Config says enabled, but it's disabled
                install_path="/path",
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "enabled" in failures[0].message.lower()

    @pytest.mark.asyncio
    async def test_enabled_state_mismatch_should_be_disabled(
        self,
        validator: PluginStateValidator,
        mock_context: MagicMock,
    ) -> None:
        """Plugin should be disabled but is enabled should fail."""
        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin", enabled=False),)
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,  # Config says disabled, but it's enabled
                install_path="/path",
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "disabled" in failures[0].message.lower()

    @pytest.mark.asyncio
    async def test_plugin_not_installed_skipped(
        self,
        validator: PluginStateValidator,
        mock_context: MagicMock,
    ) -> None:
        """Plugin not installed should be skipped (installation validator handles this)."""
        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(plugins=(PluginConfig(id="missing-plugin"),)),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = []

        results = await validator.validate(mock_context)
        # No results for plugins that aren't installed
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 0


class TestPluginManifestValidator:
    """Tests for PluginManifestValidator."""

    @pytest.fixture
    def validator(self) -> PluginManifestValidator:
        return PluginManifestValidator()

    @pytest.mark.asyncio
    async def test_valid_manifest(
        self,
        validator: PluginManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin with valid manifest should pass."""
        # Create plugin directory with manifest
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"})
        )

        mp_path = tmp_path / "marketplace"
        mp_path.mkdir()
        (mp_path / "test-plugin").symlink_to(plugin_dir)

        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        marketplaces={
                            "test-marketplace": MarketplaceConfig(
                                source=PluginSource.LOCAL,
                                path=str(mp_path),
                            )
                        },
                        plugins=(PluginConfig(id="test-plugin@test-marketplace"),),
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin@test-marketplace",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        passed = [r for r in results if r.status == "pass"]
        assert len(passed) >= 1

    @pytest.mark.asyncio
    async def test_missing_manifest(
        self,
        validator: PluginManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin without manifest should fail."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        # No .claude-plugin/plugin.json

        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin"),),
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "plugin.json" in failures[0].message.lower()

    @pytest.mark.asyncio
    async def test_invalid_manifest_json(
        self,
        validator: PluginManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin with invalid JSON manifest should fail."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text("{ invalid json }")

        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin"),),
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "invalid" in failures[0].message.lower() or "json" in failures[0].message.lower()

    @pytest.mark.asyncio
    async def test_missing_required_fields(
        self,
        validator: PluginManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin manifest missing required fields should warn."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(json.dumps({}))  # Empty manifest

        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin"),),
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        # Missing name should be a failure (name is required)
        assert any("name" in f.message.lower() for f in failures)


class TestKebabCaseValidation:
    """Tests for kebab-case name validation."""

    @pytest.mark.parametrize(
        "name,valid",
        [
            # Valid kebab-case names
            ("my-plugin", True),
            ("plugin", True),
            ("my-cool-plugin", True),
            ("plugin-v2", True),
            ("a", True),
            ("a-b-c", True),
            ("plugin123", True),
            ("my-plugin-123", True),
            # Invalid names - uppercase
            ("My-Plugin", False),
            ("MY-PLUGIN", False),
            ("myPlugin", False),  # camelCase
            # Invalid names - spaces
            ("my plugin", False),
            ("my  plugin", False),
            # Invalid names - underscores
            ("my_plugin", False),
            # Invalid names - special characters
            ("my.plugin", False),
            ("my@plugin", False),
            # Invalid names - empty
            ("", False),
        ],
    )
    def test_kebab_case_validation(self, name: str, valid: bool) -> None:
        """Test kebab-case name validation."""
        result = is_kebab_case(name)
        if valid:
            assert result, f"Expected '{name}' to be valid kebab-case"
        else:
            assert not result, f"Expected '{name}' to be invalid kebab-case"


class TestPluginManifestNameValidation:
    """Tests for plugin manifest name field validation."""

    @pytest.fixture
    def validator(self) -> PluginManifestValidator:
        return PluginManifestValidator()

    @pytest.mark.asyncio
    async def test_valid_kebab_case_name(
        self,
        validator: PluginManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin with valid kebab-case name should pass."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(json.dumps({"name": "my-cool-plugin"}))

        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin"),),
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        name_errors = [
            f for f in failures if "kebab" in f.message.lower() or "name" in f.message.lower()
        ]
        assert name_errors == []

    @pytest.mark.asyncio
    async def test_uppercase_name_fails(
        self,
        validator: PluginManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin with uppercase name should fail."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(json.dumps({"name": "My-Plugin"}))

        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin"),),
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("kebab" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_name_with_spaces_fails(
        self,
        validator: PluginManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin with spaces in name should fail."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(json.dumps({"name": "my plugin"}))

        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin"),),
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("kebab" in f.message.lower() or "space" in f.message.lower() for f in failures)


class TestPluginManifestVersionOptional:
    """Tests that version is optional (only name is required)."""

    @pytest.fixture
    def validator(self) -> PluginManifestValidator:
        return PluginManifestValidator()

    @pytest.mark.asyncio
    async def test_manifest_without_version_passes(
        self,
        validator: PluginManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin manifest without version should pass (version is optional)."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest_dir = plugin_dir / ".claude-plugin"
        manifest_dir.mkdir()
        # Only name, no version
        (manifest_dir / "plugin.json").write_text(json.dumps({"name": "my-plugin"}))

        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin"),),
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        # No failures for missing version
        version_errors = [f for f in failures if "version" in f.message.lower()]
        assert version_errors == []
