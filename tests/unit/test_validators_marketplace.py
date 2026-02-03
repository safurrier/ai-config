"""Tests for ai_config.validators.marketplace module.

Tests marketplace manifest validation per the official Claude Code schema:
https://code.claude.com/docs/en/plugin-marketplaces
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    MarketplaceConfig,
    PluginSource,
    TargetConfig,
)
from ai_config.validators.marketplace.validators import (
    RESERVED_MARKETPLACE_NAMES,
    MarketplaceManifestValidator,
    MarketplacePathValidator,
    PathDriftValidator,
)


@pytest.fixture
def mock_context(tmp_path: Path) -> MagicMock:
    """Create a mock validation context."""
    context = MagicMock()
    context.config_path = tmp_path / ".ai-config" / "config.yaml"
    return context


@pytest.fixture
def local_marketplace_config(tmp_path: Path) -> AIConfig:
    """Create a config with a local marketplace."""
    mp_path = tmp_path / "plugins"
    mp_path.mkdir()
    return AIConfig(
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
                    }
                ),
            ),
        ),
    )


class TestMarketplacePathValidator:
    """Tests for MarketplacePathValidator."""

    @pytest.fixture
    def validator(self) -> MarketplacePathValidator:
        return MarketplacePathValidator()

    @pytest.mark.asyncio
    async def test_local_path_exists(
        self,
        validator: MarketplacePathValidator,
        mock_context: MagicMock,
        local_marketplace_config: AIConfig,
    ) -> None:
        """Local marketplace path that exists should pass."""
        mock_context.config = local_marketplace_config
        results = await validator.validate(mock_context)
        passed = [r for r in results if r.status == "pass"]
        assert len(passed) >= 1

    @pytest.mark.asyncio
    async def test_local_path_missing(
        self,
        validator: MarketplacePathValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Local marketplace path that doesn't exist should fail."""
        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        marketplaces={
                            "missing-marketplace": MarketplaceConfig(
                                source=PluginSource.LOCAL,
                                path=str(tmp_path / "nonexistent"),
                            )
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "does not exist" in failures[0].message.lower()

    @pytest.mark.asyncio
    async def test_github_marketplace_skipped(
        self,
        validator: MarketplacePathValidator,
        mock_context: MagicMock,
    ) -> None:
        """GitHub marketplaces should be skipped (no local path to validate)."""
        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        marketplaces={
                            "github-marketplace": MarketplaceConfig(
                                source=PluginSource.GITHUB,
                                repo="owner/repo",
                            )
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        # GitHub marketplaces don't need local path validation
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 0


class TestMarketplaceManifestValidator:
    """Tests for MarketplaceManifestValidator."""

    @pytest.fixture
    def validator(self) -> MarketplaceManifestValidator:
        return MarketplaceManifestValidator()

    @pytest.mark.asyncio
    async def test_manifest_exists_and_valid(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Marketplace with valid manifest should pass."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        # Include all required fields per official schema
        manifest_file.write_text(
            json.dumps(
                {
                    "name": "test-marketplace",
                    "owner": {"name": "Test Owner"},
                    "plugins": [],
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        passed = [r for r in results if r.status == "pass"]
        assert len(passed) >= 1

    @pytest.mark.asyncio
    async def test_manifest_missing(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Marketplace without manifest should fail."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "marketplace.json" in failures[0].message.lower()

    @pytest.mark.asyncio
    async def test_manifest_invalid_json(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Marketplace with invalid JSON manifest should fail."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text("{ invalid json }")

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "invalid" in failures[0].message.lower() or "json" in failures[0].message.lower()


class TestPathDriftValidator:
    """Tests for PathDriftValidator (config vs Claude's known_marketplaces.json)."""

    @pytest.fixture
    def validator(self) -> PathDriftValidator:
        return PathDriftValidator()

    @pytest.mark.asyncio
    async def test_no_drift_detected(
        self,
        validator: PathDriftValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When paths match, no drift should be detected."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        # Simulate Claude's known_marketplaces.json having the same path
        mock_context.known_marketplaces_json = {"test-marketplace": {"path": str(mp_path)}}

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 0

    @pytest.mark.asyncio
    async def test_drift_detected(
        self,
        validator: PathDriftValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When paths differ, drift should be detected."""
        config_path = tmp_path / "config" / "plugins"
        claude_path = tmp_path / "claude" / "plugins"

        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        marketplaces={
                            "test-marketplace": MarketplaceConfig(
                                source=PluginSource.LOCAL,
                                path=str(config_path),
                            )
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        # Simulate Claude's known_marketplaces.json having a different path
        mock_context.known_marketplaces_json = {"test-marketplace": {"path": str(claude_path)}}

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "drift" in failures[0].message.lower() or "path" in failures[0].message.lower()
        assert failures[0].fix_hint is not None

    @pytest.mark.asyncio
    async def test_marketplace_not_in_claude(
        self,
        validator: PathDriftValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Marketplace in config but not in Claude should warn."""
        mp_path = tmp_path / "plugins"

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        # Claude has no marketplaces registered
        mock_context.known_marketplaces_json = {}

        results = await validator.validate(mock_context)
        # This is a warning (marketplace needs to be registered) not a failure
        warnings = [r for r in results if r.status == "warn"]
        assert len(warnings) == 1
        assert "not registered" in warnings[0].message.lower()

    @pytest.mark.asyncio
    async def test_github_marketplace_skipped(
        self,
        validator: PathDriftValidator,
        mock_context: MagicMock,
    ) -> None:
        """GitHub marketplaces should not check for path drift."""
        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        marketplaces={
                            "github-marketplace": MarketplaceConfig(
                                source=PluginSource.GITHUB,
                                repo="owner/repo",
                            )
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        mock_context.known_marketplaces_json = {}

        results = await validator.validate(mock_context)
        # GitHub marketplaces don't have path drift validation
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 0


class TestMarketplaceManifestRequiredFields:
    """Tests for required fields in marketplace manifest."""

    @pytest.fixture
    def validator(self) -> MarketplaceManifestValidator:
        return MarketplaceManifestValidator()

    @pytest.mark.asyncio
    async def test_valid_manifest_with_required_fields(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Marketplace with all required fields should pass."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "name": "my-marketplace",
                    "owner": {"name": "Test Owner"},
                    "plugins": [],
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_missing_name_fails(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Marketplace without name should fail."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "owner": {"name": "Test Owner"},
                    "plugins": [],
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("name" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_missing_owner_fails(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Marketplace without owner should fail."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "name": "my-marketplace",
                    "plugins": [],
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("owner" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_missing_owner_name_fails(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Marketplace with owner but no owner.name should fail."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "name": "my-marketplace",
                    "owner": {"email": "test@example.com"},  # name missing
                    "plugins": [],
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("owner" in f.message.lower() and "name" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_missing_plugins_fails(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Marketplace without plugins array should fail."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "name": "my-marketplace",
                    "owner": {"name": "Test Owner"},
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("plugins" in f.message.lower() for f in failures)


class TestMarketplaceManifestReservedNames:
    """Tests for reserved marketplace names."""

    @pytest.fixture
    def validator(self) -> MarketplaceManifestValidator:
        return MarketplaceManifestValidator()

    # Use a fixed list to avoid non-deterministic test collection with pytest-xdist
    @pytest.mark.parametrize(
        "reserved_name",
        [
            "claude-code-marketplace",
            "claude-plugins-official",
            "anthropic-marketplace",
            "anthropic-plugins",
        ],
    )
    @pytest.mark.asyncio
    async def test_reserved_name_fails(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
        reserved_name: str,
    ) -> None:
        """Reserved marketplace names should fail."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "name": reserved_name,
                    "owner": {"name": "Test Owner"},
                    "plugins": [],
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("reserved" in f.message.lower() for f in failures)


class TestMarketplaceManifestPluginEntries:
    """Tests for plugin entries in marketplace manifest."""

    @pytest.fixture
    def validator(self) -> MarketplaceManifestValidator:
        return MarketplaceManifestValidator()

    @pytest.mark.asyncio
    async def test_valid_plugin_entry(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin entry with name and source should pass."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "name": "my-marketplace",
                    "owner": {"name": "Test Owner"},
                    "plugins": [{"name": "my-plugin", "source": "./plugins/my-plugin"}],
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_plugin_entry_missing_name_fails(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin entry without name should fail."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "name": "my-marketplace",
                    "owner": {"name": "Test Owner"},
                    "plugins": [{"source": "./plugins/my-plugin"}],
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("name" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_plugin_entry_missing_source_fails(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin entry without source should fail."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "name": "my-marketplace",
                    "owner": {"name": "Test Owner"},
                    "plugins": [{"name": "my-plugin"}],
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("source" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_plugins_must_be_array(
        self,
        validator: MarketplaceManifestValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """plugins field must be an array."""
        mp_path = tmp_path / "plugins"
        mp_path.mkdir()
        manifest_dir = mp_path / ".claude-plugin"
        manifest_dir.mkdir()
        manifest_file = manifest_dir / "marketplace.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "name": "my-marketplace",
                    "owner": {"name": "Test Owner"},
                    "plugins": {"my-plugin": "./plugins/my-plugin"},  # Should be array
                }
            )
        )

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
                        }
                    ),
                ),
            ),
        )
        mock_context.config = config
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("array" in f.message.lower() or "list" in f.message.lower() for f in failures)
