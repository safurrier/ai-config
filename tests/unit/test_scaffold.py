"""Tests for ai_config.scaffold module."""

from pathlib import Path

from ai_config.scaffold import create_plugin


class TestCreatePlugin:
    """Tests for create_plugin function."""

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        """Creates all expected directories and files."""
        plugin_dir = create_plugin("my-plugin", tmp_path)

        assert plugin_dir.exists()
        assert (plugin_dir / "manifest.yaml").exists()
        assert (plugin_dir / "skills").is_dir()
        assert (plugin_dir / "hooks").is_dir()
        assert (plugin_dir / "skills" / "example" / "SKILL.md").exists()

    def test_manifest_contains_name(self, tmp_path: Path) -> None:
        """Manifest contains the plugin name."""
        plugin_dir = create_plugin("test-plugin", tmp_path)
        manifest = (plugin_dir / "manifest.yaml").read_text()

        assert "name: test-plugin" in manifest

    def test_skill_template(self, tmp_path: Path) -> None:
        """Skill template is created."""
        plugin_dir = create_plugin("my-plugin", tmp_path)
        skill = (plugin_dir / "skills" / "example" / "SKILL.md").read_text()

        assert "name: example" in skill
        assert "## Quickstart" in skill

    def test_default_path(self, tmp_path: Path, monkeypatch) -> None:
        """Uses ~/.claude-plugins/ by default."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        plugin_dir = create_plugin("default-test")

        expected = tmp_path / ".claude-plugins" / "default-test"
        assert plugin_dir == expected
        assert plugin_dir.exists()

    def test_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        """Does not overwrite existing files."""
        plugin_dir = tmp_path / "existing-plugin"
        plugin_dir.mkdir(parents=True)

        # Create custom manifest
        custom_manifest = plugin_dir / "manifest.yaml"
        custom_manifest.write_text("custom: content")

        # Run create
        create_plugin("existing-plugin", tmp_path)

        # Custom content should be preserved
        assert custom_manifest.read_text() == "custom: content"

    def test_returns_plugin_path(self, tmp_path: Path) -> None:
        """Returns the path to the created plugin."""
        result = create_plugin("my-plugin", tmp_path)

        assert result == tmp_path / "my-plugin"
