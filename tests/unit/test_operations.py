"""Tests for ai_config.operations module."""

from unittest.mock import patch

import pytest
from ai_config.adapters.claude import CommandResult, InstalledMarketplace, InstalledPlugin
from ai_config.operations import (
    get_status,
    sync_config,
    sync_target,
    update_plugins,
    verify_sync,
)
from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    MarketplaceConfig,
    PluginConfig,
    PluginSource,
    TargetConfig,
)


@pytest.fixture
def sample_config() -> AIConfig:
    """Sample config with one marketplace and two plugins."""
    marketplace = MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
    plugin1 = PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True)
    plugin2 = PluginConfig(id="plugin2@my-marketplace", scope="project", enabled=False)
    target_config = ClaudeTargetConfig(
        marketplaces={"my-marketplace": marketplace},
        plugins=(plugin1, plugin2),
    )
    target = TargetConfig(type="claude", config=target_config)
    return AIConfig(version=1, targets=(target,))


@pytest.fixture
def mock_installed_plugins() -> list[InstalledPlugin]:
    """Mock installed plugins."""
    return [
        InstalledPlugin(
            id="plugin1@my-marketplace",
            version="1.0.0",
            scope="user",
            enabled=True,
            install_path="/path/to/plugin1",
        ),
    ]


@pytest.fixture
def mock_installed_marketplaces() -> list[InstalledMarketplace]:
    """Mock installed marketplaces."""
    return [
        InstalledMarketplace(
            name="my-marketplace",
            source=PluginSource.GITHUB,
            repo="owner/repo",
            install_location="/path/to/marketplace",
        ),
    ]


class TestSyncTarget:
    """Tests for sync_target function."""

    def test_unsupported_target_type(self) -> None:
        """Unsupported target type returns error."""
        # Create a target with invalid type by bypassing validation
        target = TargetConfig.__new__(TargetConfig)
        object.__setattr__(target, "type", "codex")
        object.__setattr__(target, "config", ClaudeTargetConfig())

        result = sync_target(target)

        assert result.success is False
        assert any("only supports 'claude'" in e for e in result.errors)

    def test_dry_run_no_changes(
        self,
        sample_config: AIConfig,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
    ) -> None:
        """Dry run with everything in sync makes no changes."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
        ):
            result = sync_target(sample_config.targets[0], dry_run=True)

            # plugin1 is installed and enabled (matches config)
            # plugin2 is not installed but should be disabled (no action needed)
            # marketplace is installed (no action needed)
            assert result.success is True
            assert len(result.errors) == 0

    def test_install_missing_plugin(self, sample_config: AIConfig) -> None:
        """Missing plugin is installed."""
        # No plugins installed
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.add_marketplace",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
            patch(
                "ai_config.operations.claude.install_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_install,
        ):
            result = sync_target(sample_config.targets[0])

            # Should install plugin1 (enabled) but not plugin2 (disabled)
            mock_install.assert_called_once_with("plugin1@my-marketplace", "user")
            assert result.success is True
            assert any(a.action == "install" for a in result.actions_taken)

    def test_enable_disabled_plugin(self, sample_config: AIConfig) -> None:
        """Disabled plugin that should be enabled is enabled."""
        # plugin1 is installed but disabled
        installed_plugins = [
            InstalledPlugin(
                id="plugin1@my-marketplace",
                version="1.0.0",
                scope="user",
                enabled=False,  # Currently disabled
                install_path="/path",
            ),
        ]
        installed_mps = [
            InstalledMarketplace(
                name="my-marketplace",
                source=PluginSource.GITHUB,
                repo="owner/repo",
                install_location="/path",
            ),
        ]

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(installed_mps, []),
            ),
            patch(
                "ai_config.operations.claude.enable_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_enable,
        ):
            result = sync_target(sample_config.targets[0])

            mock_enable.assert_called_once_with("plugin1@my-marketplace")
            assert result.success is True
            assert any(a.action == "enable" for a in result.actions_taken)

    def test_disable_enabled_plugin(self) -> None:
        """Enabled plugin that should be disabled is disabled."""
        # Config wants plugin disabled
        plugin = PluginConfig(id="plugin1@mp", scope="user", enabled=False)
        target_config = ClaudeTargetConfig(plugins=(plugin,))
        target = TargetConfig(type="claude", config=target_config)

        # But plugin is installed and enabled
        installed_plugins = [
            InstalledPlugin(
                id="plugin1@mp",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path="/path",
            ),
        ]

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.disable_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_disable,
        ):
            result = sync_target(target)

            mock_disable.assert_called_once_with("plugin1@mp")
            assert result.success is True
            assert any(a.action == "disable" for a in result.actions_taken)

    def test_add_missing_marketplace(self, sample_config: AIConfig) -> None:
        """Missing marketplace is added."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),  # No marketplaces
            ),
            patch(
                "ai_config.operations.claude.add_marketplace",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_add,
            patch(
                "ai_config.operations.claude.install_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
        ):
            result = sync_target(sample_config.targets[0])

            mock_add.assert_called_once_with(repo="owner/repo", name="my-marketplace", path=None)
            assert any(a.action == "register_marketplace" for a in result.actions_taken)

    def test_fresh_clears_cache(self, sample_config: AIConfig) -> None:
        """Fresh mode clears cache before sync."""
        with (
            patch(
                "ai_config.operations.claude.clear_cache",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_clear,
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.add_marketplace",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
            patch(
                "ai_config.operations.claude.install_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
        ):
            sync_target(sample_config.targets[0], fresh=True)

            mock_clear.assert_called_once()

    def test_dry_run_skips_cache_clear(self, sample_config: AIConfig) -> None:
        """Dry run does not clear cache."""
        with (
            patch(
                "ai_config.operations.claude.clear_cache",
            ) as mock_clear,
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
        ):
            sync_target(sample_config.targets[0], dry_run=True, fresh=True)

            mock_clear.assert_not_called()


class TestSyncConfig:
    """Tests for sync_config function."""

    def test_sync_all_targets(self, sample_config: AIConfig) -> None:
        """Syncs all targets in config."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.add_marketplace",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
            patch(
                "ai_config.operations.claude.install_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
        ):
            results = sync_config(sample_config)

            assert "claude" in results
            assert results["claude"].success is True


class TestGetStatus:
    """Tests for get_status function."""

    def test_returns_plugins_and_marketplaces(
        self,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
    ) -> None:
        """Returns status of installed plugins and marketplaces."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
        ):
            result = get_status()

            assert result.target_type == "claude"
            assert len(result.plugins) == 1
            assert result.plugins[0].id == "plugin1@my-marketplace"
            assert result.plugins[0].installed is True
            assert "my-marketplace" in result.marketplaces

    def test_unsupported_target(self) -> None:
        """Unsupported target returns error."""
        result = get_status(target_type="codex")

        assert any("only supports 'claude'" in e for e in result.errors)


class TestUpdatePlugins:
    """Tests for update_plugins function."""

    def test_update_all_plugins(
        self,
        mock_installed_plugins: list[InstalledPlugin],
    ) -> None:
        """Updates all installed plugins when no IDs specified."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.update_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_update,
        ):
            result = update_plugins()

            mock_update.assert_called_once_with("plugin1@my-marketplace")
            assert result.success is True

    def test_update_specific_plugins(
        self,
        mock_installed_plugins: list[InstalledPlugin],
    ) -> None:
        """Updates only specified plugins."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.update_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_update,
        ):
            result = update_plugins(plugin_ids=["plugin1@my-marketplace"])

            mock_update.assert_called_once_with("plugin1@my-marketplace")
            assert result.success is True

    def test_warns_about_missing_plugins(
        self,
        mock_installed_plugins: list[InstalledPlugin],
    ) -> None:
        """Warns when specified plugin is not installed."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.update_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
        ):
            result = update_plugins(plugin_ids=["nonexistent-plugin"])

            assert any("not installed" in e for e in result.errors)

    def test_fresh_clears_cache(
        self,
        mock_installed_plugins: list[InstalledPlugin],
    ) -> None:
        """Fresh mode clears cache before updating."""
        with (
            patch(
                "ai_config.operations.claude.clear_cache",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_clear,
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.update_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
        ):
            update_plugins(fresh=True)

            mock_clear.assert_called_once()


class TestVerifySync:
    """Tests for verify_sync function."""

    def test_in_sync(
        self,
        sample_config: AIConfig,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
    ) -> None:
        """No discrepancies when in sync."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
        ):
            discrepancies = verify_sync(sample_config)

            # plugin1 is installed and enabled (matches)
            # plugin2 is not installed but disabled (ok)
            assert discrepancies == []

    def test_missing_marketplace(self, sample_config: AIConfig) -> None:
        """Detects missing marketplace."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),  # No marketplaces
            ),
        ):
            discrepancies = verify_sync(sample_config)

            assert any("not registered" in d for d in discrepancies)

    def test_missing_enabled_plugin(self, sample_config: AIConfig) -> None:
        """Detects missing enabled plugin."""
        installed_mps = [
            InstalledMarketplace(
                name="my-marketplace",
                source=PluginSource.GITHUB,
                repo="owner/repo",
                install_location="/path",
            ),
        ]

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),  # No plugins
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(installed_mps, []),
            ),
        ):
            discrepancies = verify_sync(sample_config)

            assert any("not installed" in d for d in discrepancies)

    def test_wrong_enabled_state(self, sample_config: AIConfig) -> None:
        """Detects plugin with wrong enabled state."""
        # plugin1 should be enabled but is disabled
        installed_plugins = [
            InstalledPlugin(
                id="plugin1@my-marketplace",
                version="1.0.0",
                scope="user",
                enabled=False,
                install_path="/path",
            ),
        ]
        installed_mps = [
            InstalledMarketplace(
                name="my-marketplace",
                source=PluginSource.GITHUB,
                repo="owner/repo",
                install_location="/path",
            ),
        ]

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(installed_mps, []),
            ),
        ):
            discrepancies = verify_sync(sample_config)

            assert any("should be enabled" in d for d in discrepancies)
