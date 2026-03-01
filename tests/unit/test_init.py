"""Tests for ai_config.init module."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner
from rich.console import Console

from ai_config.cli import main
from ai_config.init import (
    GO_BACK,
    ConversionChoice,
    InitConfig,
    MarketplaceChoice,
    PluginChoice,
    Prompter,
    _ResolvedPath,
    _add_escape_binding,
    check_claude_cli,
    create_minimal_config,
    generate_config_yaml,
    prompt_path_with_search,
    run_init_wizard,
    write_config,
)


class ScriptedPrompter:
    """Fake prompter that returns pre-scripted answers and records prompts shown.

    Each call pops the next answer from the script. If the script runs out,
    the test fails with a clear message showing which prompt was unexpected.

    Usage::

        p = ScriptedPrompter([
            GO_BACK,                                    # first prompt → go back
            ".ai-config/config.yaml (this project)",    # second prompt → select
            "Skip (no more marketplaces)",              # third prompt → select
            True,                                       # fourth prompt → confirm
        ])
        result = run_init_wizard(console, prompter=p)
        assert p.prompts_shown[0] == "Where should the config be created?"
    """

    def __init__(self, script: list[object]) -> None:
        self._script: deque[object] = deque(script)
        self.prompts_shown: list[str] = []

    def _next(self, message: str) -> object:
        self.prompts_shown.append(message)
        if not self._script:
            raise AssertionError(
                f"ScriptedPrompter ran out of answers at prompt #{len(self.prompts_shown)}: "
                f"{message!r}"
            )
        return self._script.popleft()

    def select(
        self, message: str, choices: list[str], default: str | None = None
    ) -> str | None | object:
        return self._next(message)

    def checkbox(
        self,
        message: str,
        choices: list[tuple[str, str]],
        checked_by_default: bool = True,
    ) -> list[str] | None | object:
        return self._next(message)

    def text(self, message: str, default: str = "") -> str | None | object:
        return self._next(message)

    def confirm(self, message: str, default: bool = True) -> bool | None | object:
        return self._next(message)


@pytest.fixture
def runner() -> CliRunner:
    """Click test runner."""
    return CliRunner()


class TestCheckClaudeCli:
    """Tests for check_claude_cli function."""

    def test_cli_available(self) -> None:
        """Returns True and version when CLI is installed."""
        with patch("ai_config.init.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="claude 2.1.29\n",
                stderr="",
            )
            installed, version = check_claude_cli()

            assert installed is True
            assert "2.1.29" in version

    def test_cli_not_found(self) -> None:
        """Returns False when CLI is not installed."""
        with patch("ai_config.init.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            installed, message = check_claude_cli()

            assert installed is False
            assert "not found" in message.lower()

    def test_cli_error(self) -> None:
        """Returns False when CLI returns error."""
        with patch("ai_config.init.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Some error",
            )
            installed, message = check_claude_cli()

            assert installed is False
            assert "error" in message.lower() or "Some error" in message

    def test_cli_timeout(self) -> None:
        """Returns False when CLI times out."""
        import subprocess

        with patch("ai_config.init.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=10)
            installed, message = check_claude_cli()

            assert installed is False
            assert "timed out" in message.lower()


class TestGenerateConfigYaml:
    """Tests for generate_config_yaml function."""

    def test_empty_config(self, tmp_path: Path) -> None:
        """Generates valid YAML for empty config."""
        init_config = InitConfig(config_path=tmp_path / "config.yaml")
        yaml_str = generate_config_yaml(init_config)

        config = yaml.safe_load(yaml_str)
        assert config["version"] == 1
        assert len(config["targets"]) == 1
        assert config["targets"][0]["type"] == "claude"
        assert config["targets"][0]["config"]["marketplaces"] == {}
        assert config["targets"][0]["config"]["plugins"] == []

    def test_with_github_marketplace(self, tmp_path: Path) -> None:
        """Generates config with GitHub marketplace."""
        init_config = InitConfig(
            config_path=tmp_path / "config.yaml",
            marketplaces=[
                MarketplaceChoice(
                    name="my-mp",
                    source="github",
                    repo="owner/repo",
                )
            ],
        )
        yaml_str = generate_config_yaml(init_config)

        config = yaml.safe_load(yaml_str)
        mp = config["targets"][0]["config"]["marketplaces"]["my-mp"]
        assert mp["source"] == "github"
        assert mp["repo"] == "owner/repo"

    def test_with_local_marketplace(self, tmp_path: Path) -> None:
        """Generates config with local marketplace."""
        init_config = InitConfig(
            config_path=tmp_path / "config.yaml",
            marketplaces=[
                MarketplaceChoice(
                    name="local-mp",
                    source="local",
                    path="/path/to/plugins",
                )
            ],
        )
        yaml_str = generate_config_yaml(init_config)

        config = yaml.safe_load(yaml_str)
        mp = config["targets"][0]["config"]["marketplaces"]["local-mp"]
        assert mp["source"] == "local"
        assert mp["path"] == "/path/to/plugins"

    def test_with_plugins(self, tmp_path: Path) -> None:
        """Generates config with plugins."""
        init_config = InitConfig(
            config_path=tmp_path / "config.yaml",
            marketplaces=[MarketplaceChoice(name="mp1", source="github", repo="owner/repo")],
            plugins=[
                PluginChoice(id="plugin1", marketplace="mp1", enabled=True, scope="user"),
                PluginChoice(id="plugin2", marketplace="mp1", enabled=False, scope="project"),
            ],
        )
        yaml_str = generate_config_yaml(init_config)

        config = yaml.safe_load(yaml_str)
        plugins = config["targets"][0]["config"]["plugins"]
        assert len(plugins) == 2
        assert plugins[0]["id"] == "plugin1@mp1"
        assert plugins[0]["enabled"] is True
        assert plugins[0]["scope"] == "user"
        assert plugins[1]["id"] == "plugin2@mp1"
        assert plugins[1]["enabled"] is False
        assert plugins[1]["scope"] == "project"

    def test_with_conversion(self, tmp_path: Path) -> None:
        """Generates config with conversion settings."""
        init_config = InitConfig(
            config_path=tmp_path / "config.yaml",
            plugins=[PluginChoice(id="plugin1", marketplace="mp1")],
            conversion=ConversionChoice(
                enabled=True,
                targets=["codex", "cursor"],
                scope="user",
                custom_output_dir=Path("./converted"),
            ),
        )
        yaml_str = generate_config_yaml(init_config)

        config = yaml.safe_load(yaml_str)
        conversion = config["targets"][0]["config"]["conversion"]
        assert conversion["targets"] == ["codex", "cursor"]
        assert conversion["scope"] == "user"
        assert conversion["output_dir"] == "converted"


class TestWriteConfig:
    """Tests for write_config function."""

    def test_creates_directories(self, tmp_path: Path) -> None:
        """Creates parent directories if they don't exist."""
        config_path = tmp_path / "nested" / "dir" / "config.yaml"
        init_config = InitConfig(config_path=config_path)

        result = write_config(init_config)

        assert result == config_path
        assert config_path.exists()
        assert config_path.parent.exists()

    def test_writes_valid_yaml(self, tmp_path: Path) -> None:
        """Writes valid, loadable YAML."""
        config_path = tmp_path / "config.yaml"
        init_config = InitConfig(
            config_path=config_path,
            marketplaces=[MarketplaceChoice(name="test-mp", source="github", repo="test/repo")],
            plugins=[PluginChoice(id="test-plugin", marketplace="test-mp")],
        )

        write_config(init_config)

        # Verify file is valid YAML
        content = config_path.read_text()
        config = yaml.safe_load(content)
        assert config["version"] == 1
        assert "test-mp" in config["targets"][0]["config"]["marketplaces"]


class TestCreateMinimalConfig:
    """Tests for create_minimal_config function."""

    def test_default_path(self) -> None:
        """Uses current directory by default."""
        init_config = create_minimal_config()

        assert init_config.config_path == Path.cwd() / ".ai-config" / "config.yaml"
        assert init_config.marketplaces == []
        assert init_config.plugins == []

    def test_custom_path(self, tmp_path: Path) -> None:
        """Uses provided output path."""
        custom_path = tmp_path / "custom" / "config.yaml"
        init_config = create_minimal_config(custom_path)

        assert init_config.config_path == custom_path


class TestInitCommand:
    """Tests for the init CLI command."""

    def test_init_non_interactive(self, runner: CliRunner, tmp_path: Path) -> None:
        """Non-interactive mode creates minimal config."""
        output_path = tmp_path / "config.yaml"

        result = runner.invoke(main, ["init", "--non-interactive", "-o", str(output_path)])

        assert result.exit_code == 0
        assert "Created minimal config" in result.output
        assert output_path.exists()

        # Verify config structure
        config = yaml.safe_load(output_path.read_text())
        assert config["version"] == 1

    def test_init_cancelled(self, runner: CliRunner) -> None:
        """Shows cancelled message when wizard returns None."""
        with patch("ai_config.init.run_init_wizard", return_value=None):
            result = runner.invoke(main, ["init"])

            assert result.exit_code == 1
            assert "Cancelled" in result.output

    def test_init_success(self, runner: CliRunner, tmp_path: Path) -> None:
        """Successful init creates config and shows next steps."""
        output_path = tmp_path / "config.yaml"
        mock_config = InitConfig(
            config_path=output_path,
            marketplaces=[MarketplaceChoice(name="test", source="github", repo="test/repo")],
        )

        with patch("ai_config.init.run_init_wizard", return_value=mock_config):
            result = runner.invoke(main, ["init"])

            assert result.exit_code == 0
            assert "Config created" in result.output
            assert "ai-config sync" in result.output
            assert "ai-config doctor" in result.output

    def test_init_help(self, runner: CliRunner) -> None:
        """Shows help text for init command."""
        result = runner.invoke(main, ["init", "--help"])

        assert result.exit_code == 0
        assert "Set up a new ai-config configuration" in result.output
        assert "--non-interactive" in result.output
        assert "--output" in result.output


class TestInitConfigDataclass:
    """Tests for InitConfig dataclass."""

    def test_defaults(self, tmp_path: Path) -> None:
        """Dataclass has sensible defaults."""
        config = InitConfig(config_path=tmp_path / "config.yaml")

        assert config.marketplaces == []
        assert config.plugins == []


class TestMarketplaceChoice:
    """Tests for MarketplaceChoice dataclass."""

    def test_github_marketplace(self) -> None:
        """GitHub marketplace stores repo."""
        mp = MarketplaceChoice(name="test", source="github", repo="owner/repo")

        assert mp.name == "test"
        assert mp.source == "github"
        assert mp.repo == "owner/repo"
        assert mp.path == ""

    def test_local_marketplace(self) -> None:
        """Local marketplace stores path."""
        mp = MarketplaceChoice(name="local", source="local", path="/path/to/plugins")

        assert mp.name == "local"
        assert mp.source == "local"
        assert mp.path == "/path/to/plugins"
        assert mp.repo == ""


class TestPluginChoice:
    """Tests for PluginChoice dataclass."""

    def test_defaults(self) -> None:
        """Plugin has sensible defaults."""
        plugin = PluginChoice(id="test", marketplace="mp")

        assert plugin.id == "test"
        assert plugin.marketplace == "mp"
        assert plugin.enabled is True
        assert plugin.scope == "user"

    def test_custom_values(self) -> None:
        """Plugin accepts custom values."""
        plugin = PluginChoice(
            id="custom",
            marketplace="custom-mp",
            enabled=False,
            scope="project",
        )

        assert plugin.enabled is False
        assert plugin.scope == "project"


class TestDiscoverPluginsFromLocal:
    """Tests for discover_plugins_from_local function."""

    def test_reads_marketplace_json(self, tmp_path: Path) -> None:
        """Reads plugins from .claude-plugin/marketplace.json."""
        from ai_config.init import PluginInfo, discover_plugins_from_local

        # Create marketplace structure
        mp_dir = tmp_path / ".claude-plugin"
        mp_dir.mkdir()
        marketplace_json = mp_dir / "marketplace.json"
        marketplace_json.write_text(
            """
            {
                "name": "test-marketplace",
                "plugins": [
                    {"name": "plugin-a", "description": "First plugin"},
                    {"name": "plugin-b", "description": "Second plugin"}
                ]
            }
            """
        )

        plugins = discover_plugins_from_local(tmp_path)

        assert len(plugins) == 2
        assert plugins[0] == PluginInfo(id="plugin-a", description="First plugin")
        assert plugins[1] == PluginInfo(id="plugin-b", description="Second plugin")

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        """Returns empty list when marketplace.json doesn't exist."""
        from ai_config.init import discover_plugins_from_local

        plugins = discover_plugins_from_local(tmp_path)

        assert plugins == []

    def test_returns_empty_for_invalid_json(self, tmp_path: Path) -> None:
        """Returns empty list when marketplace.json is invalid."""
        from ai_config.init import discover_plugins_from_local

        mp_dir = tmp_path / ".claude-plugin"
        mp_dir.mkdir()
        (mp_dir / "marketplace.json").write_text("not valid json {")

        plugins = discover_plugins_from_local(tmp_path)

        assert plugins == []

    def test_returns_empty_for_missing_plugins_key(self, tmp_path: Path) -> None:
        """Returns empty list when plugins key is missing."""
        from ai_config.init import discover_plugins_from_local

        mp_dir = tmp_path / ".claude-plugin"
        mp_dir.mkdir()
        (mp_dir / "marketplace.json").write_text('{"name": "test"}')

        plugins = discover_plugins_from_local(tmp_path)

        assert plugins == []

    def test_handles_plugin_without_description(self, tmp_path: Path) -> None:
        """Handles plugins that don't have a description field."""
        from ai_config.init import PluginInfo, discover_plugins_from_local

        mp_dir = tmp_path / ".claude-plugin"
        mp_dir.mkdir()
        (mp_dir / "marketplace.json").write_text('{"plugins": [{"name": "no-desc-plugin"}]}')

        plugins = discover_plugins_from_local(tmp_path)

        assert len(plugins) == 1
        assert plugins[0] == PluginInfo(id="no-desc-plugin", description="")


class TestDiscoverPluginsFromGithub:
    """Tests for discover_plugins_from_github function."""

    def test_fetches_from_github(self) -> None:
        """Fetches marketplace.json from GitHub raw URL."""
        from ai_config.init import PluginInfo, discover_plugins_from_github

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "github-marketplace",
            "plugins": [{"name": "gh-plugin", "description": "GitHub hosted plugin"}],
        }

        with patch("ai_config.init.requests.get", return_value=mock_response) as mock_get:
            plugins = discover_plugins_from_github("owner/repo")

            mock_get.assert_called_once()
            call_url = mock_get.call_args[0][0]
            assert "raw.githubusercontent.com" in call_url
            assert "owner/repo" in call_url
            assert "marketplace.json" in call_url

        assert len(plugins) == 1
        assert plugins[0] == PluginInfo(id="gh-plugin", description="GitHub hosted plugin")

    def test_returns_empty_on_http_error(self) -> None:
        """Returns empty list on HTTP error."""
        from ai_config.init import discover_plugins_from_github

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("ai_config.init.requests.get", return_value=mock_response):
            plugins = discover_plugins_from_github("owner/nonexistent")

        assert plugins == []

    def test_returns_empty_on_network_error(self) -> None:
        """Returns empty list on network error."""
        from ai_config.init import discover_plugins_from_github

        with patch("ai_config.init.requests.get") as mock_get:
            mock_get.side_effect = Exception("Network error")
            plugins = discover_plugins_from_github("owner/repo")

        assert plugins == []

    def test_tries_multiple_branches(self) -> None:
        """Tries main, then master branch."""
        from ai_config.init import discover_plugins_from_github

        call_count = 0

        def mock_get(url: str, timeout: int) -> MagicMock:
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            if "main" in url:
                response.status_code = 404
            else:  # master
                response.status_code = 200
                response.json.return_value = {"plugins": [{"name": "p1"}]}
            return response

        with patch("ai_config.init.requests.get", side_effect=mock_get):
            plugins = discover_plugins_from_github("owner/repo")

        assert call_count == 2
        assert len(plugins) == 1


class TestFindLocalMarketplaces:
    """Tests for find_local_marketplaces function."""

    def test_finds_marketplace_in_current_dir(self, tmp_path: Path) -> None:
        """Finds marketplace.json in current directory."""
        from ai_config.init import find_local_marketplaces

        mp_dir = tmp_path / ".claude-plugin"
        mp_dir.mkdir()
        (mp_dir / "marketplace.json").write_text('{"name": "root-mp"}')

        results = find_local_marketplaces(tmp_path)

        assert len(results) == 1
        assert results[0] == tmp_path

    def test_finds_nested_marketplaces(self, tmp_path: Path) -> None:
        """Finds marketplace.json files in subdirectories."""
        from ai_config.init import find_local_marketplaces

        # Create nested structure
        plugins_dir = tmp_path / "config" / "plugins"
        plugins_dir.mkdir(parents=True)
        mp_dir = plugins_dir / ".claude-plugin"
        mp_dir.mkdir()
        (mp_dir / "marketplace.json").write_text('{"name": "nested-mp"}')

        results = find_local_marketplaces(tmp_path)

        assert len(results) == 1
        assert results[0] == plugins_dir

    def test_finds_multiple_marketplaces(self, tmp_path: Path) -> None:
        """Finds multiple marketplace.json files."""
        from ai_config.init import find_local_marketplaces

        # Create two marketplaces
        for name in ["mp1", "mp2"]:
            mp_path = tmp_path / name / ".claude-plugin"
            mp_path.mkdir(parents=True)
            (mp_path / "marketplace.json").write_text(f'{{"name": "{name}"}}')

        results = find_local_marketplaces(tmp_path)

        assert len(results) == 2

    def test_returns_empty_when_none_found(self, tmp_path: Path) -> None:
        """Returns empty list when no marketplaces found."""
        from ai_config.init import find_local_marketplaces

        results = find_local_marketplaces(tmp_path)

        assert results == []

    def test_respects_max_depth(self, tmp_path: Path) -> None:
        """Doesn't search too deep."""
        from ai_config.init import find_local_marketplaces

        # Create deeply nested marketplace
        deep_path = tmp_path / "a" / "b" / "c" / "d" / "e" / ".claude-plugin"
        deep_path.mkdir(parents=True)
        (deep_path / "marketplace.json").write_text('{"name": "deep"}')

        # Default max_depth should limit this
        results = find_local_marketplaces(tmp_path, max_depth=3)

        assert len(results) == 0


class TestPluginInfo:
    """Tests for PluginInfo dataclass."""

    def test_equality(self) -> None:
        """PluginInfo instances are equal when id and description match."""
        from ai_config.init import PluginInfo

        p1 = PluginInfo(id="test", description="Test plugin")
        p2 = PluginInfo(id="test", description="Test plugin")

        assert p1 == p2

    def test_to_dict(self) -> None:
        """Converts to dict format used by wizard."""
        from ai_config.init import PluginInfo

        plugin = PluginInfo(id="my-plugin", description="My description")

        assert plugin.id == "my-plugin"
        assert plugin.description == "My description"


class TestParseGithubRepo:
    """Tests for parse_github_repo function."""

    def test_simple_slug(self) -> None:
        """Parses owner/repo format."""
        from ai_config.init import parse_github_repo

        result = parse_github_repo("owner/repo")
        assert result == "owner/repo"

    def test_full_https_url(self) -> None:
        """Parses full GitHub HTTPS URL."""
        from ai_config.init import parse_github_repo

        result = parse_github_repo("https://github.com/owner/repo")
        assert result == "owner/repo"

    def test_https_url_with_trailing_slash(self) -> None:
        """Parses GitHub URL with trailing slash."""
        from ai_config.init import parse_github_repo

        result = parse_github_repo("https://github.com/owner/repo/")
        assert result == "owner/repo"

    def test_https_url_with_git_suffix(self) -> None:
        """Parses GitHub URL with .git suffix."""
        from ai_config.init import parse_github_repo

        result = parse_github_repo("https://github.com/owner/repo.git")
        assert result == "owner/repo"

    def test_ssh_url(self) -> None:
        """Parses SSH git URL."""
        from ai_config.init import parse_github_repo

        result = parse_github_repo("git@github.com:owner/repo.git")
        assert result == "owner/repo"

    def test_invalid_format_returns_none(self) -> None:
        """Returns None for invalid formats."""
        from ai_config.init import parse_github_repo

        assert parse_github_repo("invalid") is None
        assert parse_github_repo("") is None
        assert parse_github_repo("just-one-part") is None

    def test_preserves_nested_paths(self) -> None:
        """Handles repos with extra path components."""
        from ai_config.init import parse_github_repo

        # Should just get owner/repo, not deeper paths
        result = parse_github_repo("https://github.com/owner/repo/tree/main")
        assert result == "owner/repo"


class TestScopeChoices:
    """Tests for scope selection constants."""

    def test_scope_descriptions_exist(self) -> None:
        """Scope descriptions are defined."""
        from ai_config.init import SCOPE_CHOICES

        assert "user" in SCOPE_CHOICES
        assert "project" in SCOPE_CHOICES
        assert len(SCOPE_CHOICES) >= 2

    def test_scope_has_description(self) -> None:
        """Each scope has a description."""
        from ai_config.init import SCOPE_CHOICES

        for _scope, description in SCOPE_CHOICES.items():
            assert isinstance(description, str)
            assert len(description) > 0


class TestGetMarketplaceName:
    """Tests for get_marketplace_name function."""

    def test_reads_name_from_marketplace_json(self, tmp_path: Path) -> None:
        """Reads the name field from marketplace.json."""
        from ai_config.init import get_marketplace_name

        mp_dir = tmp_path / ".claude-plugin"
        mp_dir.mkdir()
        (mp_dir / "marketplace.json").write_text('{"name": "my-marketplace"}')

        name = get_marketplace_name(tmp_path)
        assert name == "my-marketplace"

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """Returns None when marketplace.json doesn't exist."""
        from ai_config.init import get_marketplace_name

        name = get_marketplace_name(tmp_path)
        assert name is None

    def test_returns_none_for_invalid_json(self, tmp_path: Path) -> None:
        """Returns None for invalid JSON."""
        from ai_config.init import get_marketplace_name

        mp_dir = tmp_path / ".claude-plugin"
        mp_dir.mkdir()
        (mp_dir / "marketplace.json").write_text("not valid json")

        name = get_marketplace_name(tmp_path)
        assert name is None

    def test_returns_none_for_missing_name_field(self, tmp_path: Path) -> None:
        """Returns None when name field is missing."""
        from ai_config.init import get_marketplace_name

        mp_dir = tmp_path / ".claude-plugin"
        mp_dir.mkdir()
        (mp_dir / "marketplace.json").write_text('{"plugins": []}')

        name = get_marketplace_name(tmp_path)
        assert name is None


class TestGetMarketplaceNameFromGithub:
    """Tests for get_marketplace_name_from_github function."""

    def test_success(self) -> None:
        """Reads name from GitHub marketplace.json."""
        from ai_config.init import get_marketplace_name_from_github

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "my-marketplace", "plugins": []}

        with patch("ai_config.init.requests.get", return_value=mock_response):
            name = get_marketplace_name_from_github("owner/repo")

        assert name == "my-marketplace"

    def test_fallback_to_master(self) -> None:
        """Falls back to master branch when main returns 404."""
        from ai_config.init import get_marketplace_name_from_github

        def mock_get(url: str, timeout: int) -> MagicMock:
            response = MagicMock()
            if "main" in url:
                response.status_code = 404
            else:  # master
                response.status_code = 200
                response.json.return_value = {"name": "master-marketplace"}
            return response

        with patch("ai_config.init.requests.get", side_effect=mock_get):
            name = get_marketplace_name_from_github("owner/repo")

        assert name == "master-marketplace"

    def test_network_error_returns_none(self) -> None:
        """Returns None on network error."""
        from ai_config.init import get_marketplace_name_from_github

        with patch("ai_config.init.requests.get") as mock_get:
            mock_get.side_effect = Exception("Network error")
            name = get_marketplace_name_from_github("owner/repo")

        assert name is None

    def test_missing_name_field_returns_none(self) -> None:
        """Returns None when name field is missing."""
        from ai_config.init import get_marketplace_name_from_github

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"plugins": []}

        with patch("ai_config.init.requests.get", return_value=mock_response):
            name = get_marketplace_name_from_github("owner/repo")

        assert name is None


class TestAddEscapeBinding:
    """Tests for _add_escape_binding helper."""

    def test_adds_escape_key_binding(self):
        """ESC key binding is added to question's key bindings."""
        import questionary

        question = questionary.text("test")
        original_bindings = question.application.key_bindings
        _add_escape_binding(question)
        # After adding, the key bindings should be a merged set
        # (different object from original since merge creates new)
        assert question.application.key_bindings is not original_bindings

    def test_escape_binding_preserves_original(self):
        """Original key bindings are preserved after adding ESC."""
        import questionary

        question = questionary.text("test")
        _add_escape_binding(question)
        # The merged bindings should still work (not None, not empty)
        assert question.application.key_bindings is not None


class TestGoBack:
    """Tests for Escape-to-go-back behavior in the init wizard.

    Uses ScriptedPrompter (injected fake) instead of patching module-level functions.
    Tests verify observable behavior: what the wizard returns, what prompts are shown,
    and what state is accumulated — not internal call order.
    """

    def _console(self) -> Console:
        """Real console with output suppressed."""
        return Console(quiet=True)

    def test_go_back_from_config_location_cancels(self) -> None:
        """Escape at the first prompt (config location) cancels the wizard."""
        p = ScriptedPrompter([GO_BACK])
        with patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")):
            result = run_init_wizard(self._console(), prompter=p)
        assert result is None
        assert "config be created" in p.prompts_shown[0]

    def test_go_back_from_overwrite_returns_to_config_location(self) -> None:
        """Escape at overwrite → re-prompts config location."""
        p = ScriptedPrompter([
            ".ai-config/config.yaml (this project)",  # config location
            GO_BACK,  # overwrite confirm → go back
            GO_BACK,  # config location again → cancel
        ])
        with (
            patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")),
            patch("pathlib.Path.exists", return_value=True),
        ):
            result = run_init_wizard(self._console(), prompter=p)
        assert result is None
        # Config location was asked twice
        assert p.prompts_shown.count("Where should the config be created?") == 2

    def test_go_back_from_marketplace_no_marketplaces_returns_to_config(self) -> None:
        """Escape at marketplace source (empty) goes back to config location."""
        p = ScriptedPrompter([
            "~/.ai-config/config.yaml (global)",  # config location (non-existent path)
            GO_BACK,  # marketplace source → go back to step 0
            GO_BACK,  # config location → cancel
        ])
        with patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")):
            result = run_init_wizard(self._console(), prompter=p)
        assert result is None

    def test_go_back_from_repo_entry_returns_to_marketplace_source(self, tmp_path: Path) -> None:
        """Escape at repo entry → re-prompts marketplace source, then skip finishes."""
        output = tmp_path / ".ai-config" / "config.yaml"
        p = ScriptedPrompter([
            "GitHub repository",  # marketplace source
            GO_BACK,  # repo entry → back to source
            "Skip (no more marketplaces)",  # skip
            True,  # confirm write
        ])
        with patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")):
            result = run_init_wizard(self._console(), output_path=output, prompter=p)
        assert result is not None
        assert result.marketplaces == []

    def test_go_back_from_plugin_selection_removes_marketplace(self, tmp_path: Path) -> None:
        """Escape at plugin checkbox removes marketplace and goes back to source."""
        output = tmp_path / ".ai-config" / "config.yaml"
        p = ScriptedPrompter([
            "GitHub repository",  # marketplace source
            "owner/repo",  # repo text
            GO_BACK,  # plugin checkbox → go back (removes marketplace)
            "Skip (no more marketplaces)",  # skip
            True,  # confirm write
        ])
        with (
            patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")),
            patch("ai_config.init.parse_github_repo", return_value="owner/repo"),
            patch("ai_config.init.get_marketplace_name_from_github", return_value="test-mp"),
            patch(
                "ai_config.init.fetch_marketplace_plugins",
                return_value=[MagicMock(id="p1", description="d1")],
            ),
        ):
            result = run_init_wizard(self._console(), output_path=output, prompter=p)
        assert result is not None
        assert result.marketplaces == []
        assert result.plugins == []

    def test_go_back_from_scope_returns_to_plugin_selection(self, tmp_path: Path) -> None:
        """Escape at scope selection → re-shows plugin checkbox."""
        output = tmp_path / ".ai-config" / "config.yaml"
        p = ScriptedPrompter([
            "GitHub repository",  # marketplace source
            "owner/repo",  # repo text
            ["p1"],  # plugin checkbox (1st)
            GO_BACK,  # scope select → back to plugins
            ["p1"],  # plugin checkbox (2nd — re-shown)
            "user - Available in all projects (~/.claude/plugins/)",  # scope
            False,  # add another? no
            False,  # conversion? no
            True,  # confirm write
        ])
        with (
            patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")),
            patch("ai_config.init.parse_github_repo", return_value="owner/repo"),
            patch("ai_config.init.get_marketplace_name_from_github", return_value="test-mp"),
            patch(
                "ai_config.init.fetch_marketplace_plugins",
                return_value=[MagicMock(id="p1", description="d1")],
            ),
        ):
            result = run_init_wizard(self._console(), output_path=output, prompter=p)
        assert result is not None
        assert len(result.plugins) == 1
        # Plugin selection prompt was shown twice
        plugin_prompts = [m for m in p.prompts_shown if "plugins to enable" in m.lower()]
        assert len(plugin_prompts) == 2

    def test_go_back_from_add_another_removes_marketplace_and_plugins(self, tmp_path: Path) -> None:
        """Escape at 'add another?' undoes the marketplace and its plugins."""
        output = tmp_path / ".ai-config" / "config.yaml"
        p = ScriptedPrompter([
            "GitHub repository",  # marketplace source
            "owner/repo",  # repo text
            ["p1"],  # plugin checkbox
            "user - Available in all projects (~/.claude/plugins/)",  # scope
            GO_BACK,  # add another? → undo marketplace+plugins
            "Skip (no more marketplaces)",  # now skip
            True,  # confirm write
        ])
        with (
            patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")),
            patch("ai_config.init.parse_github_repo", return_value="owner/repo"),
            patch("ai_config.init.get_marketplace_name_from_github", return_value="test-mp"),
            patch(
                "ai_config.init.fetch_marketplace_plugins",
                return_value=[MagicMock(id="p1", description="d1")],
            ),
        ):
            result = run_init_wizard(self._console(), output_path=output, prompter=p)
        assert result is not None
        assert result.marketplaces == []
        assert result.plugins == []

    def test_go_back_from_conversion_re_prompts_conversion(self, tmp_path: Path) -> None:
        """Escape at conversion → re-prompts conversion (preserves marketplaces)."""
        output = tmp_path / ".ai-config" / "config.yaml"
        p = ScriptedPrompter([
            "GitHub repository",
            "owner/repo",
            ["p1"],
            "user - Available in all projects (~/.claude/plugins/)",
            False,  # add another? no
            GO_BACK,  # conversion prompt → re-prompt conversion
            False,  # conversion? no (second time)
            True,  # confirm write
        ])
        with (
            patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")),
            patch("ai_config.init.parse_github_repo", return_value="owner/repo"),
            patch("ai_config.init.get_marketplace_name_from_github", return_value="test-mp"),
            patch(
                "ai_config.init.fetch_marketplace_plugins",
                return_value=[MagicMock(id="p1", description="d1")],
            ),
        ):
            result = run_init_wizard(self._console(), output_path=output, prompter=p)
        assert result is not None
        assert len(result.marketplaces) == 1
        assert len(result.plugins) == 1

    def test_go_back_from_confirm_write_returns_to_conversion(self, tmp_path: Path) -> None:
        """Escape at confirm-write goes back to conversion step."""
        output = tmp_path / ".ai-config" / "config.yaml"
        p = ScriptedPrompter([
            "GitHub repository",
            "owner/repo",
            ["p1"],
            "user - Available in all projects (~/.claude/plugins/)",
            False,  # add another? no
            False,  # conversion? no
            GO_BACK,  # confirm write → back to conversion
            False,  # conversion? no (second time)
            True,  # confirm write
        ])
        with (
            patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")),
            patch("ai_config.init.parse_github_repo", return_value="owner/repo"),
            patch("ai_config.init.get_marketplace_name_from_github", return_value="test-mp"),
            patch(
                "ai_config.init.fetch_marketplace_plugins",
                return_value=[MagicMock(id="p1", description="d1")],
            ),
        ):
            result = run_init_wizard(self._console(), output_path=output, prompter=p)
        assert result is not None
        assert len(result.plugins) == 1

    def test_go_back_from_confirm_write_no_plugins_returns_to_marketplace(
        self, tmp_path: Path
    ) -> None:
        """Escape at confirm-write (no plugins) goes back to marketplace loop."""
        output = tmp_path / ".ai-config" / "config.yaml"
        p = ScriptedPrompter([
            "Skip (no more marketplaces)",  # first pass
            GO_BACK,  # confirm write → back to marketplace
            "Skip (no more marketplaces)",  # second pass
            True,  # confirm write
        ])
        with patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")):
            result = run_init_wizard(self._console(), output_path=output, prompter=p)
        assert result is not None
        assert result.plugins == []

    def test_ctrl_c_still_cancels(self, tmp_path: Path) -> None:
        """None return (Ctrl+C) cancels the wizard at any point."""
        output = tmp_path / ".ai-config" / "config.yaml"
        p = ScriptedPrompter([
            "GitHub repository",
            None,  # Ctrl+C at repo entry
        ])
        with patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")):
            result = run_init_wizard(self._console(), output_path=output, prompter=p)
        assert result is None

    def test_go_back_from_sync_returns_to_confirm(self, tmp_path: Path) -> None:
        """Escape at run-sync → re-prompts confirm-write."""
        output = tmp_path / ".ai-config" / "config.yaml"
        p = ScriptedPrompter([
            "GitHub repository",
            "owner/repo",
            ["p1"],
            "user - Available in all projects (~/.claude/plugins/)",
            False,  # add another? no
            True,  # conversion? yes
            ["codex"],  # target checkbox
            False,  # custom dir? no
            True,  # confirm write
            GO_BACK,  # run sync? → back to confirm write
            True,  # confirm write (again)
            True,  # run sync? yes
        ])
        with (
            patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")),
            patch("ai_config.init.parse_github_repo", return_value="owner/repo"),
            patch("ai_config.init.get_marketplace_name_from_github", return_value="test-mp"),
            patch(
                "ai_config.init.fetch_marketplace_plugins",
                return_value=[MagicMock(id="p1", description="d1")],
            ),
        ):
            result = run_init_wizard(self._console(), output_path=output, prompter=p)
        assert result is not None
        assert result.run_sync is True


class TestPromptPathWithSearch:
    """Tests for prompt_path_with_search environment variable handling."""

    def test_expands_env_vars_in_manual_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment variables in manually entered path are expanded."""
        monkeypatch.setenv("DOTS_REPO", str(tmp_path / "dots"))
        console = Console(quiet=True)
        p = ScriptedPrompter([
            "Enter a different path (local path, env var like $MY_REPO, etc.)",
            "$DOTS_REPO/plugins",  # manual path text
        ])
        result = prompt_path_with_search(console, p)
        assert isinstance(result, _ResolvedPath)
        assert "$" not in str(result.resolved)
        expected = (tmp_path / "dots" / "plugins").resolve()
        assert result.resolved == expected
        assert result.raw == "$DOTS_REPO/plugins"

    def test_expands_tilde_in_manual_path(self) -> None:
        """Tilde in manually entered path is expanded."""
        console = Console(quiet=True)
        p = ScriptedPrompter([
            "Enter a different path (local path, env var like $MY_REPO, etc.)",
            "~/my-plugins",  # manual path text
        ])
        result = prompt_path_with_search(console, p)
        assert isinstance(result, _ResolvedPath)
        assert "~" not in str(result.resolved)
        assert result.resolved == (Path.home() / "my-plugins").resolve()
        assert result.raw == "~/my-plugins"


class TestMarketplaceAutoDiscovery:
    """Tests for automatic marketplace discovery from repo root."""

    def _console(self) -> Console:
        return Console(quiet=True)

    def _make_marketplace(self, path: Path, name: str, plugins: list[str]) -> None:
        """Create a minimal marketplace structure at the given path."""
        cp_dir = path / ".claude-plugin"
        cp_dir.mkdir(parents=True)
        import json

        manifest = {
            "name": name,
            "owner": {"name": "test"},
            "plugins": [{"name": p, "description": f"Plugin {p}"} for p in plugins],
        }
        (cp_dir / "marketplace.json").write_text(json.dumps(manifest))

    def test_auto_discovers_single_nested_marketplace(self, tmp_path: Path) -> None:
        """When path is a repo root with one nested marketplace, auto-selects it."""
        mp_dir = tmp_path / "config" / "plugins"
        self._make_marketplace(mp_dir, "my-plugins", ["p1"])

        p = ScriptedPrompter([
            ".ai-config/config.yaml (this project)",  # config location
            "Local directory",  # marketplace source
            "Enter a different path (local path, env var like $MY_REPO, etc.)",
            str(tmp_path),  # enter repo root path
            ["p1"],  # plugin checkbox
            "user - Available in all projects (~/.claude/plugins/)",  # scope
            False,  # add another marketplace? no
            False,  # conversion? no
            True,  # confirm write
        ])
        with patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")):
            result = run_init_wizard(self._console(), prompter=p)
        assert result is not None
        assert len(result.marketplaces) == 1
        assert result.marketplaces[0].name == "my-plugins"
        # Raw input is preserved with discovered sub-path appended
        assert result.marketplaces[0].path == str(Path(str(tmp_path)) / "config" / "plugins")
        assert len(result.plugins) == 1

    def test_env_var_preserved_with_auto_discovery(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env var in path is preserved in config even after auto-discovery."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        monkeypatch.setenv("MY_REPO", str(repo_dir))
        mp_dir = repo_dir / "config" / "plugins"
        self._make_marketplace(mp_dir, "my-plugins", ["p1"])

        # Use a tmp output path to avoid overwrite prompt for existing config
        output_path = tmp_path / "output" / ".ai-config" / "config.yaml"
        p = ScriptedPrompter([
            "Local directory",
            "Enter a different path (local path, env var like $MY_REPO, etc.)",
            "$MY_REPO",  # env var as path
            ["p1"],
            "user - Available in all projects (~/.claude/plugins/)",
            False,
            False,
            True,
        ])
        with patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")):
            result = run_init_wizard(self._console(), output_path=output_path, prompter=p)
        assert result is not None
        # Config path should use the env var, not the resolved absolute path
        assert result.marketplaces[0].path == "$MY_REPO/config/plugins"

    def test_multiple_nested_marketplaces_presents_choice(self, tmp_path: Path) -> None:
        """When multiple nested marketplaces found, user selects one."""
        mp1_dir = tmp_path / "mp1"
        mp2_dir = tmp_path / "mp2"
        self._make_marketplace(mp1_dir, "first-mp", ["p1"])
        self._make_marketplace(mp2_dir, "second-mp", ["p2"])

        p = ScriptedPrompter([
            ".ai-config/config.yaml (this project)",  # config location
            "Local directory",  # marketplace source
            "Enter a different path (local path, env var like $MY_REPO, etc.)",
            str(tmp_path),  # enter repo root path
            str(mp1_dir),  # select first marketplace from auto-discovery
            ["p1"],  # plugin checkbox
            "user - Available in all projects (~/.claude/plugins/)",  # scope
            False,  # add another marketplace? no
            False,  # conversion? no
            True,  # confirm write
        ])
        with patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")):
            result = run_init_wizard(self._console(), prompter=p)
        assert result is not None
        assert result.marketplaces[0].name == "first-mp"
        assert result.marketplaces[0].path == str(mp1_dir)

    def test_direct_marketplace_path_skips_discovery(self, tmp_path: Path) -> None:
        """When user provides exact marketplace path, no search is needed."""
        self._make_marketplace(tmp_path, "direct-mp", ["p1"])

        p = ScriptedPrompter([
            ".ai-config/config.yaml (this project)",  # config location
            "Local directory",  # marketplace source
            "Enter a different path (local path, env var like $MY_REPO, etc.)",
            str(tmp_path),  # this IS the marketplace dir
            ["p1"],  # plugin checkbox
            "user - Available in all projects (~/.claude/plugins/)",  # scope
            False,  # add another marketplace? no
            False,  # conversion? no
            True,  # confirm write
        ])
        with patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")):
            result = run_init_wizard(self._console(), prompter=p)
        assert result is not None
        assert result.marketplaces[0].name == "direct-mp"
        assert result.marketplaces[0].path == str(tmp_path)

    def test_no_nested_marketplaces_continues(self, tmp_path: Path) -> None:
        """When no marketplaces found in subdirs, proceeds with original path."""
        (tmp_path / "some-dir").mkdir()  # no marketplace.json anywhere

        p = ScriptedPrompter([
            ".ai-config/config.yaml (this project)",  # config location
            "Local directory",  # marketplace source
            "Enter a different path (local path, env var like $MY_REPO, etc.)",
            str(tmp_path),  # repo root with no marketplaces
            "empty-mp",  # marketplace name (prompted because no manifest found)
            False,  # add another marketplace? no (no plugins found, but still asked)
            True,  # confirm write (no conversion prompt — skipped since no plugins)
        ])
        with patch("ai_config.init.check_claude_cli", return_value=(True, "1.0.0")):
            result = run_init_wizard(self._console(), prompter=p)
        assert result is not None
        assert result.marketplaces[0].name == "empty-mp"
        assert result.marketplaces[0].path == str(tmp_path)
