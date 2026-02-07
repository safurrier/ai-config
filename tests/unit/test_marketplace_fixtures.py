"""Tests that marketplace test fixtures match Claude CLI's expected schema.

Validates fixture files without needing Docker, catching schema drift early.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Path to the test-marketplace fixture
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TEST_MARKETPLACE_DIR = FIXTURES_DIR / "test-marketplace"


class TestMarketplaceFixtureSchema:
    """Validate test-marketplace fixture matches Claude CLI expectations."""

    @pytest.fixture(params=[
        ".claude-plugin/marketplace.json",
        "marketplace.json",
    ])
    def manifest_path(self, request: pytest.FixtureRequest) -> Path:
        """Both marketplace manifest locations."""
        return TEST_MARKETPLACE_DIR / request.param

    def test_manifest_exists(self, manifest_path: Path) -> None:
        """Marketplace manifest file must exist."""
        assert manifest_path.exists(), f"Missing fixture: {manifest_path}"

    def test_manifest_is_valid_json(self, manifest_path: Path) -> None:
        """Marketplace manifest must be valid JSON."""
        text = manifest_path.read_text()
        manifest = json.loads(text)
        assert isinstance(manifest, dict)

    def test_manifest_has_required_fields(self, manifest_path: Path) -> None:
        """Marketplace manifest must have name, owner, and plugins."""
        manifest = json.loads(manifest_path.read_text())
        assert "name" in manifest, "Missing required 'name' field"
        assert "owner" in manifest, "Missing required 'owner' field"
        assert "plugins" in manifest, "Missing required 'plugins' field"
        assert isinstance(manifest["name"], str)
        assert isinstance(manifest["owner"], dict)
        assert "name" in manifest["owner"], "owner must have 'name' field"
        assert isinstance(manifest["plugins"], list)

    def test_plugin_source_is_string(self, manifest_path: Path) -> None:
        """Plugin 'source' must be a string path, not an object.

        Claude CLI expects: "source": "./test-plugin"
        Not: "source": {"type": "local", "path": "test-plugin"}
        """
        manifest = json.loads(manifest_path.read_text())
        for i, plugin in enumerate(manifest.get("plugins", [])):
            source = plugin.get("source")
            assert source is not None, f"plugins[{i}] missing 'source'"
            assert isinstance(source, str), (
                f"plugins[{i}] 'source' must be a string path, "
                f"got {type(source).__name__}: {source}"
            )

    def test_plugin_entries_have_name(self, manifest_path: Path) -> None:
        """Each plugin entry must have a 'name' field."""
        manifest = json.loads(manifest_path.read_text())
        for i, plugin in enumerate(manifest.get("plugins", [])):
            assert "name" in plugin, f"plugins[{i}] missing 'name'"
            assert isinstance(plugin["name"], str)

    def test_manifests_are_consistent(self) -> None:
        """Both marketplace manifest copies must have identical content."""
        root = TEST_MARKETPLACE_DIR / "marketplace.json"
        nested = TEST_MARKETPLACE_DIR / ".claude-plugin" / "marketplace.json"
        assert root.exists() and nested.exists()
        root_data = json.loads(root.read_text())
        nested_data = json.loads(nested.read_text())
        assert root_data == nested_data, (
            "marketplace.json and .claude-plugin/marketplace.json are out of sync"
        )


try:
    from ai_config.validators.marketplace.validators import MarketplaceManifestValidator

    _HAS_VALIDATORS = True
except TypeError:
    # Python 3.9 without PEP 604 support in dataclasses at runtime
    _HAS_VALIDATORS = False


@pytest.mark.skipif(not _HAS_VALIDATORS, reason="Requires Python 3.10+ for str | None syntax")
class TestMarketplaceValidatorRejectsObjectSource:
    """Ensure the validator catches the old object-format source."""

    @pytest.fixture
    def validator(self) -> MarketplaceManifestValidator:  # type: ignore[name-defined]
        return MarketplaceManifestValidator()  # type: ignore[name-defined]

    def test_object_source_fails_validation(
        self, validator: MarketplaceManifestValidator,  # type: ignore[name-defined]
    ) -> None:
        """Object-format source should be rejected by _validate_plugin_entry."""
        results = validator._validate_plugin_entry(
            "test-mp",
            0,
            {"name": "test-plugin", "source": {"type": "local", "path": "test-plugin"}},
        )
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) == 1
        assert "source" in failures[0].message.lower()
        assert "string" in failures[0].message.lower()

    def test_string_source_passes_validation(
        self, validator: MarketplaceManifestValidator,  # type: ignore[name-defined]
    ) -> None:
        """String-format source should pass validation."""
        results = validator._validate_plugin_entry(
            "test-mp",
            0,
            {"name": "test-plugin", "source": "./test-plugin"},
        )
        failures = [r for r in results if r.status == "fail"]
        assert failures == []
