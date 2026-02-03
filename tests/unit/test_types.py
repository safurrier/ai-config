"""Tests for ai_config.types module."""

import pytest
from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    MarketplaceConfig,
    PluginConfig,
    PluginSource,
    PluginStatus,
    StatusResult,
    SyncAction,
    SyncResult,
    TargetConfig,
)


class TestMarketplaceConfig:
    """Tests for MarketplaceConfig dataclass."""

    def test_valid_github_marketplace(self) -> None:
        """Valid github marketplace config should be created successfully."""
        config = MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
        assert config.source == PluginSource.GITHUB
        assert config.repo == "owner/repo"

    def test_valid_local_marketplace(self) -> None:
        """Valid local marketplace config should be created successfully."""
        config = MarketplaceConfig(source=PluginSource.LOCAL, path="/path/to/plugins")
        assert config.source == PluginSource.LOCAL
        assert config.path == "/path/to/plugins"

    def test_empty_repo_raises(self) -> None:
        """Empty repo should raise ValueError for github source."""
        with pytest.raises(ValueError, match="cannot be empty"):
            MarketplaceConfig(source=PluginSource.GITHUB, repo="")

    def test_empty_path_raises(self) -> None:
        """Empty path should raise ValueError for local source."""
        with pytest.raises(ValueError, match="cannot be empty"):
            MarketplaceConfig(source=PluginSource.LOCAL, path="")

    def test_invalid_repo_format_raises(self) -> None:
        """Repo without slash should raise ValueError."""
        with pytest.raises(ValueError, match="owner/repo"):
            MarketplaceConfig(source=PluginSource.GITHUB, repo="invalid-repo")

    def test_frozen(self) -> None:
        """Marketplace config should be immutable."""
        config = MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
        with pytest.raises(AttributeError):
            config.repo = "other/repo"  # type: ignore[misc]


class TestPluginConfig:
    """Tests for PluginConfig dataclass."""

    def test_minimal_config(self) -> None:
        """Plugin config with only id should use defaults."""
        config = PluginConfig(id="my-plugin")
        assert config.id == "my-plugin"
        assert config.scope == "user"
        assert config.enabled is True

    def test_full_config(self) -> None:
        """Plugin config with all fields."""
        config = PluginConfig(id="my-plugin@marketplace", scope="project", enabled=False)
        assert config.id == "my-plugin@marketplace"
        assert config.scope == "project"
        assert config.enabled is False

    def test_empty_id_raises(self) -> None:
        """Empty id should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            PluginConfig(id="")

    def test_marketplace_property_with_at(self) -> None:
        """Marketplace property should extract marketplace from id."""
        config = PluginConfig(id="plugin@my-marketplace")
        assert config.marketplace == "my-marketplace"
        assert config.plugin_name == "plugin"

    def test_marketplace_property_without_at(self) -> None:
        """Marketplace property should return None when no @ in id."""
        config = PluginConfig(id="plain-plugin")
        assert config.marketplace is None
        assert config.plugin_name == "plain-plugin"

    def test_frozen(self) -> None:
        """Plugin config should be immutable."""
        config = PluginConfig(id="my-plugin")
        with pytest.raises(AttributeError):
            config.enabled = False  # type: ignore[misc]


class TestClaudeTargetConfig:
    """Tests for ClaudeTargetConfig dataclass."""

    def test_empty_config(self) -> None:
        """Empty config should use default empty collections."""
        config = ClaudeTargetConfig()
        assert config.marketplaces == {}
        assert config.plugins == ()

    def test_with_marketplace_and_plugins(self) -> None:
        """Config with marketplaces and plugins."""
        marketplace = MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
        plugin = PluginConfig(id="my-plugin@my-marketplace")
        config = ClaudeTargetConfig(
            marketplaces={"my-marketplace": marketplace},
            plugins=(plugin,),
        )
        assert "my-marketplace" in config.marketplaces
        assert len(config.plugins) == 1


class TestTargetConfig:
    """Tests for TargetConfig dataclass."""

    def test_valid_claude_target(self) -> None:
        """Valid claude target should be created."""
        config = TargetConfig(type="claude", config=ClaudeTargetConfig())
        assert config.type == "claude"

    def test_unsupported_target_raises(self) -> None:
        """Unsupported target type should raise ValueError."""
        with pytest.raises(ValueError, match="v1 only supports 'claude'"):
            TargetConfig(type="codex", config=ClaudeTargetConfig())  # type: ignore[arg-type]


class TestAIConfig:
    """Tests for AIConfig dataclass."""

    def test_valid_config(self) -> None:
        """Valid config with version 1."""
        config = AIConfig(version=1)
        assert config.version == 1
        assert config.targets == ()

    def test_with_targets(self) -> None:
        """Config with targets."""
        target = TargetConfig(type="claude", config=ClaudeTargetConfig())
        config = AIConfig(version=1, targets=(target,))
        assert len(config.targets) == 1

    def test_invalid_version_raises(self) -> None:
        """Invalid version should raise ValueError."""
        with pytest.raises(ValueError, match="Only version 1"):
            AIConfig(version=2)


class TestPluginStatus:
    """Tests for PluginStatus dataclass."""

    def test_defaults(self) -> None:
        """Plugin status should have sensible defaults."""
        status = PluginStatus(id="my-plugin")
        assert status.id == "my-plugin"
        assert status.installed is False
        assert status.enabled is False
        assert status.scope is None
        assert status.version is None

    def test_full_status(self) -> None:
        """Plugin status with all fields."""
        status = PluginStatus(
            id="my-plugin",
            installed=True,
            enabled=True,
            scope="user",
            version="1.0.0",
        )
        assert status.installed is True
        assert status.enabled is True
        assert status.scope == "user"
        assert status.version == "1.0.0"


class TestSyncAction:
    """Tests for SyncAction dataclass."""

    def test_install_action(self) -> None:
        """Install action creation."""
        action = SyncAction(action="install", target="my-plugin", scope="user")
        assert action.action == "install"
        assert action.target == "my-plugin"
        assert action.scope == "user"

    def test_marketplace_registration_action(self) -> None:
        """Marketplace registration action."""
        action = SyncAction(
            action="register_marketplace",
            target="my-marketplace",
            reason="Required by plugin",
        )
        assert action.action == "register_marketplace"
        assert action.target == "my-marketplace"
        assert action.reason == "Required by plugin"


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_default_success(self) -> None:
        """Default result should be success."""
        result = SyncResult()
        assert result.success is True
        assert result.actions_taken == []
        assert result.actions_failed == []
        assert result.errors == []

    def test_add_success(self) -> None:
        """Adding successful action."""
        result = SyncResult()
        action = SyncAction(action="install", target="my-plugin")
        result.add_success(action)
        assert action in result.actions_taken
        assert result.success is True

    def test_add_failure(self) -> None:
        """Adding failed action marks result as failed."""
        result = SyncResult()
        action = SyncAction(action="install", target="my-plugin")
        result.add_failure(action, "Installation failed")
        assert action in result.actions_failed
        assert "Installation failed" in result.errors
        assert result.success is False


class TestStatusResult:
    """Tests for StatusResult dataclass."""

    def test_defaults(self) -> None:
        """Status result should have sensible defaults."""
        result = StatusResult(target_type="claude")
        assert result.target_type == "claude"
        assert result.plugins == []
        assert result.marketplaces == []
        assert result.errors == []
