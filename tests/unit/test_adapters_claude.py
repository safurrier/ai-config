"""Tests for ai_config.adapters.claude module."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ai_config.adapters.claude import (
    add_marketplace,
    clear_cache,
    disable_plugin,
    enable_plugin,
    get_marketplace_by_name,
    get_plugin_by_id,
    install_plugin,
    list_installed_marketplaces,
    list_installed_plugins,
    remove_marketplace,
    uninstall_plugin,
    update_marketplace,
    update_plugin,
)


@pytest.fixture
def mock_plugin_list_json() -> str:
    """Sample JSON output from claude plugin list."""
    return json.dumps(
        [
            {
                "id": "plugin1@marketplace1",
                "version": "1.0.0",
                "scope": "user",
                "enabled": True,
                "installPath": "/path/to/plugin1",
            },
            {
                "id": "plugin2@marketplace1",
                "version": "2.0.0",
                "scope": "project",
                "enabled": False,
                "installPath": "/path/to/plugin2",
            },
        ]
    )


@pytest.fixture
def mock_marketplace_list_json() -> str:
    """Sample JSON output from claude plugin marketplace list."""
    return json.dumps(
        [
            {
                "name": "marketplace1",
                "source": "github",
                "repo": "owner/repo1",
                "installLocation": "/path/to/marketplace1",
            },
            {
                "name": "marketplace2",
                "source": "github",
                "repo": "owner/repo2",
                "installLocation": "/path/to/marketplace2",
            },
        ]
    )


class TestListInstalledPlugins:
    """Tests for list_installed_plugins function."""

    def test_successful_list(self, mock_plugin_list_json: str) -> None:
        """Successfully lists plugins from CLI output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_plugin_list_json
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            plugins, errors = list_installed_plugins()

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["claude", "plugin", "list", "--json"]

            assert len(plugins) == 2
            assert len(errors) == 0

            assert plugins[0].id == "plugin1@marketplace1"
            assert plugins[0].version == "1.0.0"
            assert plugins[0].scope == "user"
            assert plugins[0].enabled is True

            assert plugins[1].id == "plugin2@marketplace1"
            assert plugins[1].enabled is False

    def test_cli_failure(self) -> None:
        """Handles CLI failure gracefully."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "some error"

        with patch("subprocess.run", return_value=mock_result):
            plugins, errors = list_installed_plugins()

            assert plugins == []
            assert len(errors) == 1
            assert "some error" in errors[0]

    def test_invalid_json(self) -> None:
        """Handles invalid JSON gracefully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not json"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            plugins, errors = list_installed_plugins()

            assert plugins == []
            assert len(errors) == 1
            assert "parse" in errors[0].lower()

    def test_timeout(self) -> None:
        """Handles timeout gracefully."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 60)):
            plugins, errors = list_installed_plugins()

            assert plugins == []
            assert len(errors) == 1
            assert "timed out" in errors[0].lower()

    def test_cli_not_found(self) -> None:
        """Handles missing claude CLI gracefully."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            plugins, errors = list_installed_plugins()

            assert plugins == []
            assert len(errors) == 1
            assert "not found" in errors[0].lower()


class TestListInstalledMarketplaces:
    """Tests for list_installed_marketplaces function."""

    def test_successful_list(self, mock_marketplace_list_json: str) -> None:
        """Successfully lists marketplaces from CLI output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_marketplace_list_json
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            marketplaces, errors = list_installed_marketplaces()

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["claude", "plugin", "marketplace", "list", "--json"]

            assert len(marketplaces) == 2
            assert len(errors) == 0

            assert marketplaces[0].name == "marketplace1"
            assert marketplaces[0].repo == "owner/repo1"


class TestInstallPlugin:
    """Tests for install_plugin function."""

    def test_install_with_default_scope(self) -> None:
        """Installs plugin with default user scope."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Installed"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = install_plugin("my-plugin@marketplace")

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == [
                "claude",
                "plugin",
                "install",
                "my-plugin@marketplace",
                "--scope",
                "user",
            ]
            assert result.success is True

    def test_install_with_project_scope(self) -> None:
        """Installs plugin with project scope."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Installed"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            install_plugin("my-plugin", scope="project")

            args = mock_run.call_args[0][0]
            assert "--scope" in args
            assert "project" in args


class TestUninstallPlugin:
    """Tests for uninstall_plugin function."""

    def test_uninstall(self) -> None:
        """Uninstalls plugin successfully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Uninstalled"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = uninstall_plugin("my-plugin")

            args = mock_run.call_args[0][0]
            assert args == ["claude", "plugin", "uninstall", "my-plugin"]
            assert result.success is True


class TestEnableDisablePlugin:
    """Tests for enable_plugin and disable_plugin functions."""

    def test_enable(self) -> None:
        """Enables plugin successfully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Enabled"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = enable_plugin("my-plugin")

            args = mock_run.call_args[0][0]
            assert args == ["claude", "plugin", "enable", "my-plugin"]
            assert result.success is True

    def test_disable(self) -> None:
        """Disables plugin successfully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Disabled"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = disable_plugin("my-plugin")

            args = mock_run.call_args[0][0]
            assert args == ["claude", "plugin", "disable", "my-plugin"]
            assert result.success is True


class TestUpdatePlugin:
    """Tests for update_plugin function."""

    def test_update(self) -> None:
        """Updates plugin successfully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Updated"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = update_plugin("my-plugin")

            args = mock_run.call_args[0][0]
            assert args == ["claude", "plugin", "update", "my-plugin"]
            assert result.success is True


class TestMarketplaceCommands:
    """Tests for marketplace management commands."""

    def test_add_marketplace(self) -> None:
        """Adds marketplace successfully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Added"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = add_marketplace("owner/repo")

            args = mock_run.call_args[0][0]
            assert args == ["claude", "plugin", "marketplace", "add", "owner/repo"]
            assert result.success is True

    def test_add_marketplace_with_name_ignored(self) -> None:
        """Name parameter is accepted but ignored (CLI doesn't support it)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Added"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            add_marketplace("owner/repo", name="custom-name")

            args = mock_run.call_args[0][0]
            # Name is accepted but NOT passed to CLI (not supported)
            assert args == ["claude", "plugin", "marketplace", "add", "owner/repo"]
            assert "--name" not in args

    def test_remove_marketplace(self) -> None:
        """Removes marketplace successfully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Removed"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = remove_marketplace("my-marketplace")

            args = mock_run.call_args[0][0]
            assert args == ["claude", "plugin", "marketplace", "remove", "my-marketplace"]
            assert result.success is True

    def test_update_all_marketplaces(self) -> None:
        """Updates all marketplaces."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Updated"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = update_marketplace()

            args = mock_run.call_args[0][0]
            assert args == ["claude", "plugin", "marketplace", "update"]
            assert result.success is True

    def test_update_specific_marketplace(self) -> None:
        """Updates specific marketplace."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Updated"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = update_marketplace("my-marketplace")

            args = mock_run.call_args[0][0]
            assert args == ["claude", "plugin", "marketplace", "update", "my-marketplace"]
            assert result.success is True


class TestClearCache:
    """Tests for clear_cache function."""

    def test_cache_not_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Handles non-existent cache gracefully."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = clear_cache()

        assert result.success is True
        assert "does not exist" in result.stdout

    def test_cache_removed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Removes existing cache directory."""
        cache_dir = tmp_path / ".claude" / "plugins" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "some_file").write_text("content")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = clear_cache()

        assert result.success is True
        assert not cache_dir.exists()


class TestGetByHelpers:
    """Tests for get_plugin_by_id and get_marketplace_by_name."""

    def test_get_plugin_found(self, mock_plugin_list_json: str) -> None:
        """Finds plugin by ID."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_plugin_list_json
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            plugin, errors = get_plugin_by_id("plugin1@marketplace1")

            assert plugin is not None
            assert plugin.id == "plugin1@marketplace1"
            assert errors == []

    def test_get_plugin_not_found(self, mock_plugin_list_json: str) -> None:
        """Returns None when plugin not found."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_plugin_list_json
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            plugin, errors = get_plugin_by_id("nonexistent")

            assert plugin is None
            assert errors == []

    def test_get_marketplace_found(self, mock_marketplace_list_json: str) -> None:
        """Finds marketplace by name."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_marketplace_list_json
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            marketplace, errors = get_marketplace_by_name("marketplace1")

            assert marketplace is not None
            assert marketplace.name == "marketplace1"
            assert errors == []

    def test_get_marketplace_not_found(self, mock_marketplace_list_json: str) -> None:
        """Returns None when marketplace not found."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_marketplace_list_json
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            marketplace, errors = get_marketplace_by_name("nonexistent")

            assert marketplace is None
            assert errors == []
