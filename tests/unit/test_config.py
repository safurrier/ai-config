"""Tests for ai_config.config module."""

from pathlib import Path
from textwrap import dedent

import pytest
from ai_config.config import (
    ConfigNotFoundError,
    ConfigParseError,
    ConfigValidationError,
    find_config_file,
    load_config,
    validate_marketplace_references,
)


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_explicit_path_exists(self, tmp_path: Path) -> None:
        """Explicit path that exists should be returned."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("version: 1")
        result = find_config_file(config_file)
        assert result == config_file

    def test_explicit_path_not_found(self, tmp_path: Path) -> None:
        """Explicit path that doesn't exist should raise."""
        config_file = tmp_path / "missing.yaml"
        with pytest.raises(ConfigNotFoundError, match="not found"):
            find_config_file(config_file)

    def test_default_path_search(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should search default paths when no explicit path given."""
        # Change to tmp_path so relative paths work
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ai-config").mkdir()
        config_file = tmp_path / ".ai-config" / "config.yaml"
        config_file.write_text("version: 1")

        result = find_config_file()
        # Compare resolved paths since find_config_file returns relative path
        assert result.resolve() == config_file.resolve()

    def test_no_config_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should raise when no config found in default paths."""
        monkeypatch.chdir(tmp_path)
        # Patch home to tmp_path so it doesn't find user config
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fakehome")
        with pytest.raises(ConfigNotFoundError, match="No config file found"):
            find_config_file()


class TestLoadConfig:
    """Tests for load_config function."""

    def test_minimal_valid_config(self, tmp_path: Path) -> None:
        """Minimal valid config with just version."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("version: 1")
        config = load_config(config_file)
        assert config.version == 1
        assert config.targets == ()

    def test_full_valid_config(self, tmp_path: Path) -> None:
        """Full config with marketplaces and plugins."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: claude
                config:
                  marketplaces:
                    my-marketplace:
                      source: github
                      repo: owner/repo
                  plugins:
                    - id: my-plugin@my-marketplace
                      scope: user
                      enabled: true
                    - id: other-plugin@my-marketplace
                      scope: project
                      enabled: false
            """)
        )
        config = load_config(config_file)
        assert config.version == 1
        assert len(config.targets) == 1

        target = config.targets[0]
        assert target.type == "claude"
        assert "my-marketplace" in target.config.marketplaces
        assert len(target.config.plugins) == 2

        plugin = target.config.plugins[0]
        assert plugin.id == "my-plugin@my-marketplace"
        assert plugin.scope == "user"
        assert plugin.enabled is True

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        """Invalid YAML should raise ConfigParseError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("version: [\ninvalid")
        with pytest.raises(ConfigParseError, match="Failed to parse YAML"):
            load_config(config_file)

    def test_empty_file(self, tmp_path: Path) -> None:
        """Empty file should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        with pytest.raises(ConfigValidationError, match="empty"):
            load_config(config_file)

    def test_wrong_version(self, tmp_path: Path) -> None:
        """Wrong version should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("version: 2")
        with pytest.raises(ConfigValidationError, match="version must be 1"):
            load_config(config_file)

    def test_missing_version(self, tmp_path: Path) -> None:
        """Missing version should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("targets: []")
        with pytest.raises(ConfigValidationError, match="version must be 1"):
            load_config(config_file)

    def test_invalid_target_type(self, tmp_path: Path) -> None:
        """Invalid target type should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: codex
                config: {}
            """)
        )
        with pytest.raises(ConfigValidationError, match="type must be 'claude'"):
            load_config(config_file)

    def test_invalid_marketplace_source(self, tmp_path: Path) -> None:
        """Invalid marketplace source should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: claude
                config:
                  marketplaces:
                    my-mp:
                      source: gitlab
                      repo: owner/repo
            """)
        )
        with pytest.raises(ConfigValidationError, match="source must be one of"):
            load_config(config_file)

    def test_missing_marketplace_repo(self, tmp_path: Path) -> None:
        """Missing marketplace repo should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: claude
                config:
                  marketplaces:
                    my-mp:
                      source: github
            """)
        )
        with pytest.raises(ConfigValidationError, match="must have 'repo'"):
            load_config(config_file)

    def test_missing_plugin_id(self, tmp_path: Path) -> None:
        """Missing plugin id should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: claude
                config:
                  plugins:
                    - scope: user
            """)
        )
        with pytest.raises(ConfigValidationError, match="must have 'id'"):
            load_config(config_file)

    def test_invalid_plugin_scope(self, tmp_path: Path) -> None:
        """Invalid plugin scope should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: claude
                config:
                  plugins:
                    - id: my-plugin
                      scope: global
            """)
        )
        with pytest.raises(ConfigValidationError, match="scope must be"):
            load_config(config_file)

    def test_invalid_plugin_enabled_type(self, tmp_path: Path) -> None:
        """Invalid plugin enabled type should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: claude
                config:
                  plugins:
                    - id: my-plugin
                      enabled: "yes"
            """)
        )
        with pytest.raises(ConfigValidationError, match="enabled must be boolean"):
            load_config(config_file)

    def test_plugin_defaults(self, tmp_path: Path) -> None:
        """Plugin should have default scope and enabled values."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: claude
                config:
                  plugins:
                    - id: my-plugin
            """)
        )
        config = load_config(config_file)
        plugin = config.targets[0].config.plugins[0]
        assert plugin.scope == "user"
        assert plugin.enabled is True

    def test_targets_not_a_list(self, tmp_path: Path) -> None:
        """Targets not a list should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              type: claude
            """)
        )
        with pytest.raises(ConfigValidationError, match="Targets must be a list"):
            load_config(config_file)

    def test_config_not_a_dict(self, tmp_path: Path) -> None:
        """Config that's not a dict should raise ConfigValidationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("- item1\n- item2")
        with pytest.raises(ConfigValidationError, match="Config must be a dict"):
            load_config(config_file)


class TestValidateMarketplaceReferences:
    """Tests for validate_marketplace_references function."""

    def test_valid_references(self, tmp_path: Path) -> None:
        """All plugin marketplace references exist."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: claude
                config:
                  marketplaces:
                    my-marketplace:
                      source: github
                      repo: owner/repo
                  plugins:
                    - id: my-plugin@my-marketplace
            """)
        )
        config = load_config(config_file)
        errors = validate_marketplace_references(config)
        assert errors == []

    def test_undefined_marketplace(self, tmp_path: Path) -> None:
        """Plugin referencing undefined marketplace should produce error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: claude
                config:
                  marketplaces:
                    my-marketplace:
                      source: github
                      repo: owner/repo
                  plugins:
                    - id: my-plugin@other-marketplace
            """)
        )
        config = load_config(config_file)
        errors = validate_marketplace_references(config)
        assert len(errors) == 1
        assert "undefined marketplace" in errors[0]
        assert "other-marketplace" in errors[0]

    def test_plugin_without_marketplace(self, tmp_path: Path) -> None:
        """Plugin without marketplace reference is valid."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            dedent("""
            version: 1
            targets:
              - type: claude
                config:
                  plugins:
                    - id: plain-plugin
            """)
        )
        config = load_config(config_file)
        errors = validate_marketplace_references(config)
        assert errors == []
