"""Tests for ai_config.init module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from ai_config.cli import main
from ai_config.init import (
    InitConfig,
    MarketplaceChoice,
    PluginChoice,
    check_claude_cli,
    create_minimal_config,
    generate_config_yaml,
    write_config,
)
from click.testing import CliRunner


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
        assert "Create a new ai-config configuration file" in result.output
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

        for scope, description in SCOPE_CHOICES.items():
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
