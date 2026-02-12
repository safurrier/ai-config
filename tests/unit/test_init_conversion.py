"""Tests for init wizard conversion integration.

These tests verify that the init wizard can prompt for conversion targets
and trigger conversion after plugin selection.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_config.init import (
    ConversionChoice,
    InitConfig,
    MarketplaceChoice,
    PluginChoice,
    prompt_conversion_targets,
)


class TestConversionChoice:
    """Test ConversionChoice dataclass."""

    def test_conversion_choice_enabled_with_scope(self) -> None:
        """ConversionChoice with targets enabled and scope."""
        choice = ConversionChoice(
            enabled=True,
            targets=["codex", "cursor"],
            scope="user",
        )
        assert choice.enabled is True
        assert "codex" in choice.targets
        assert "cursor" in choice.targets
        assert choice.scope == "user"

    def test_conversion_choice_enabled_with_custom_dir(self) -> None:
        """ConversionChoice with custom output directory."""
        choice = ConversionChoice(
            enabled=True,
            targets=["codex"],
            scope="project",
            custom_output_dir=Path("/tmp/output"),
        )
        assert choice.enabled is True
        assert choice.custom_output_dir == Path("/tmp/output")
        # Backwards compat: output_dir property
        assert choice.output_dir == Path("/tmp/output")

    def test_conversion_choice_disabled(self) -> None:
        """ConversionChoice when user skips conversion."""
        choice = ConversionChoice(enabled=False)
        assert choice.enabled is False
        assert choice.targets == []
        assert choice.output_dir is None

    def test_get_output_dir_user_scope(self) -> None:
        """get_output_dir returns home directory for user scope."""
        choice = ConversionChoice(
            enabled=True,
            targets=["codex"],
            scope="user",
        )
        output = choice.get_output_dir("codex")
        assert output == Path.home()

    def test_get_output_dir_project_scope(self) -> None:
        """get_output_dir returns cwd for project scope."""
        choice = ConversionChoice(
            enabled=True,
            targets=["codex"],
            scope="project",
        )
        output = choice.get_output_dir("codex")
        assert output == Path.cwd()

    def test_get_output_dir_custom_overrides(self) -> None:
        """get_output_dir returns custom dir when set."""
        choice = ConversionChoice(
            enabled=True,
            targets=["codex"],
            scope="user",
            custom_output_dir=Path("/custom/path"),
        )
        output = choice.get_output_dir("codex")
        assert output == Path("/custom/path")


class TestInitConfigWithConversion:
    """Test InitConfig with conversion field."""

    def test_init_config_has_conversion_field(self) -> None:
        """InitConfig should have optional conversion field."""
        config = InitConfig(
            config_path=Path("/tmp/config.yaml"),
            marketplaces=[
                MarketplaceChoice(name="my-mp", source="github", repo="owner/repo")
            ],
            plugins=[PluginChoice(id="my-plugin", marketplace="my-mp")],
        )
        # Conversion should be None by default
        assert config.conversion is None

    def test_init_config_with_conversion(self) -> None:
        """InitConfig can store conversion choices."""
        config = InitConfig(
            config_path=Path("/tmp/config.yaml"),
            conversion=ConversionChoice(
                enabled=True,
                targets=["codex"],
                scope="user",
            ),
        )
        assert config.conversion is not None
        assert config.conversion.enabled is True
        assert config.conversion.targets == ["codex"]


class TestPromptConversionTargets:
    """Test prompt_conversion_targets function."""

    @patch("ai_config.init.prompt_confirm")
    def test_prompt_conversion_declined(self, mock_confirm: MagicMock) -> None:
        """User declines conversion prompt."""
        mock_confirm.return_value = False

        result = prompt_conversion_targets(MagicMock())

        assert result is not None
        assert result.enabled is False

    @patch("ai_config.init.prompt_checkbox")
    @patch("ai_config.init.prompt_confirm")
    def test_prompt_conversion_accepted_with_targets(
        self,
        mock_confirm: MagicMock,
        mock_checkbox: MagicMock,
    ) -> None:
        """User accepts conversion and selects targets with default scope."""
        # First confirm: wants conversion, second confirm: use custom dir (no)
        mock_confirm.side_effect = [True, False]
        mock_checkbox.return_value = ["codex", "cursor"]

        result = prompt_conversion_targets(MagicMock(), default_scope="user")

        assert result is not None
        assert result.enabled is True
        assert "codex" in result.targets
        assert "cursor" in result.targets
        assert result.scope == "user"
        assert result.custom_output_dir is None

    @patch("ai_config.init.prompt_text")
    @patch("ai_config.init.prompt_checkbox")
    @patch("ai_config.init.prompt_confirm")
    def test_prompt_conversion_with_custom_dir(
        self,
        mock_confirm: MagicMock,
        mock_checkbox: MagicMock,
        mock_text: MagicMock,
    ) -> None:
        """User accepts conversion with custom output directory."""
        # First confirm: wants conversion, second confirm: use custom dir (yes)
        mock_confirm.side_effect = [True, True]
        mock_checkbox.return_value = ["codex", "cursor", "opencode"]
        mock_text.return_value = "./converted"

        result = prompt_conversion_targets(MagicMock())

        assert result is not None
        assert result.enabled is True
        assert len(result.targets) == 3
        assert result.custom_output_dir == Path("./converted")

    @patch("ai_config.init.prompt_checkbox")
    @patch("ai_config.init.prompt_confirm")
    def test_prompt_conversion_no_targets_selected(
        self,
        mock_confirm: MagicMock,
        mock_checkbox: MagicMock,
    ) -> None:
        """User accepts but selects no targets."""
        mock_confirm.return_value = True
        mock_checkbox.return_value = []  # No targets selected

        result = prompt_conversion_targets(MagicMock())

        # Should treat as disabled
        assert result is not None
        assert result.enabled is False

    @patch("ai_config.init.prompt_confirm")
    def test_prompt_conversion_cancelled(self, mock_confirm: MagicMock) -> None:
        """User cancels conversion prompt."""
        mock_confirm.return_value = None  # Ctrl+C

        result = prompt_conversion_targets(MagicMock())

        # Should return None on cancel
        assert result is None

    @patch("ai_config.init.prompt_checkbox")
    @patch("ai_config.init.prompt_confirm")
    def test_prompt_uses_default_scope(
        self,
        mock_confirm: MagicMock,
        mock_checkbox: MagicMock,
    ) -> None:
        """Conversion uses the scope passed from plugin selection."""
        mock_confirm.side_effect = [True, False]  # Yes convert, No custom dir
        mock_checkbox.return_value = ["codex"]

        result = prompt_conversion_targets(MagicMock(), default_scope="project")

        assert result is not None
        assert result.scope == "project"
