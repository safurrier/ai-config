"""Interactive init wizard for ai-config.

This module provides the `ai-config init` command that creates a new
.ai-config/config.yaml file through an interactive wizard experience.
"""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import questionary
import requests
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ai_config.cli_theme import SYMBOLS

# Scope choices with descriptions for user selection
SCOPE_CHOICES: dict[str, str] = {
    "user": "Available in all projects (~/.claude/plugins/)",
    "project": "Only in this project (.claude/plugins/)",
}


def parse_github_repo(input_str: str) -> str | None:
    """Parse a GitHub repo from various input formats.

    Accepts:
    - owner/repo (simple slug)
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/tree/main/...
    - git@github.com:owner/repo.git

    Args:
        input_str: User input that might be a GitHub repo.

    Returns:
        Normalized owner/repo string, or None if invalid.
    """
    if not input_str:
        return None

    input_str = input_str.strip()

    # Handle simple owner/repo format
    if "/" in input_str and not input_str.startswith(("http", "git@")):
        parts = input_str.split("/")
        if len(parts) == 2 and parts[0] and parts[1]:
            return input_str
        return None

    # Handle HTTPS URLs: https://github.com/owner/repo[.git][/...]
    if input_str.startswith("https://github.com/"):
        path = input_str.replace("https://github.com/", "")
        path = path.rstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] and parts[1]:
            return f"{parts[0]}/{parts[1]}"
        return None

    # Handle SSH URLs: git@github.com:owner/repo.git
    if input_str.startswith("git@github.com:"):
        path = input_str.replace("git@github.com:", "")
        if path.endswith(".git"):
            path = path[:-4]
        parts = path.split("/")
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{parts[0]}/{parts[1]}"
        return None

    return None


@dataclass(frozen=True)
class PluginInfo:
    """Information about a discovered plugin."""

    id: str
    description: str = ""


@dataclass
class MarketplaceChoice:
    """A marketplace selection during init."""

    name: str
    source: Literal["github", "local"]
    repo: str = ""
    path: str = ""


@dataclass
class PluginChoice:
    """A plugin selection during init."""

    id: str
    marketplace: str
    enabled: bool = True
    scope: str = "user"


@dataclass
class ConversionChoice:
    """Conversion target selection during init."""

    enabled: bool = False
    targets: list[str] = field(default_factory=list)
    scope: str = "project"  # "user" or "project"
    custom_output_dir: Path | None = None  # Override canonical location if set

    def get_output_dir(self, target: str) -> Path:
        """Get the output directory for a specific target.

        Args:
            target: Target tool name (codex, cursor, opencode)

        Returns:
            Path to output directory for this target.
        """
        if self.custom_output_dir:
            return self.custom_output_dir

        # Canonical locations per target and scope
        if self.scope == "user":
            return Path.home()
        else:
            return Path.cwd()

    # For backwards compatibility
    @property
    def output_dir(self) -> Path | None:
        """Get the output directory (for backwards compatibility)."""
        return self.custom_output_dir


@dataclass
class InitConfig:
    """Collected user choices during init wizard."""

    config_path: Path
    marketplaces: list[MarketplaceChoice] = field(default_factory=list)
    plugins: list[PluginChoice] = field(default_factory=list)
    conversion: ConversionChoice | None = None


def check_claude_cli() -> tuple[bool, str]:
    """Check if Claude CLI is installed and get version.

    Returns:
        Tuple of (is_installed, version_or_error_message).
    """
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return True, version
        return False, result.stderr.strip() or "Unknown error"
    except FileNotFoundError:
        return False, "Claude CLI not found"
    except subprocess.TimeoutExpired:
        return False, "Claude CLI timed out"
    except OSError as e:
        return False, str(e)


def get_marketplace_name(path: Path) -> str | None:
    """Get the marketplace name from its marketplace.json file.

    Claude CLI uses the name from marketplace.json, not user-provided names.
    This function reads that name so we can use it correctly.

    Args:
        path: Path to the marketplace directory.

    Returns:
        The marketplace name, or None if it can't be read.
    """
    marketplace_json = path / ".claude-plugin" / "marketplace.json"

    if not marketplace_json.exists():
        return None

    try:
        data = json.loads(marketplace_json.read_text())
        return data.get("name")
    except (json.JSONDecodeError, OSError):
        return None


def discover_plugins_from_local(path: Path) -> list[PluginInfo]:
    """Discover plugins from a local marketplace directory.

    Reads the .claude-plugin/marketplace.json file to find available plugins.

    Args:
        path: Path to the marketplace directory.

    Returns:
        List of PluginInfo for each plugin found, empty list on error.
    """
    marketplace_json = path / ".claude-plugin" / "marketplace.json"

    if not marketplace_json.exists():
        return []

    try:
        data = json.loads(marketplace_json.read_text())
        plugins_data = data.get("plugins", [])

        return [
            PluginInfo(
                id=p.get("name", ""),
                description=p.get("description", ""),
            )
            for p in plugins_data
            if p.get("name")
        ]
    except (json.JSONDecodeError, OSError):
        return []


def discover_plugins_from_github(repo: str) -> list[PluginInfo]:
    """Discover plugins from a GitHub marketplace repository.

    Fetches the .claude-plugin/marketplace.json file from the repo.
    Tries 'main' branch first, then 'master'.

    Args:
        repo: GitHub repo in owner/repo format.

    Returns:
        List of PluginInfo for each plugin found, empty list on error.
    """
    branches = ["main", "master"]

    for branch in branches:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/.claude-plugin/marketplace.json"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                plugins_data = data.get("plugins", [])

                return [
                    PluginInfo(
                        id=p.get("name", ""),
                        description=p.get("description", ""),
                    )
                    for p in plugins_data
                    if p.get("name")
                ]
        except Exception:
            continue

    return []


def find_local_marketplaces(search_path: Path, max_depth: int = 4) -> list[Path]:
    """Search for local marketplace directories.

    Looks for directories containing .claude-plugin/marketplace.json.

    Args:
        search_path: Directory to search from.
        max_depth: Maximum directory depth to search.

    Returns:
        List of paths to marketplace directories (parent of .claude-plugin).
    """
    results: list[Path] = []

    def search_recursive(current: Path, depth: int) -> None:
        if depth > max_depth:
            return

        marketplace_json = current / ".claude-plugin" / "marketplace.json"
        if marketplace_json.exists():
            results.append(current)
            return  # Don't search inside a marketplace

        try:
            for child in current.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    search_recursive(child, depth + 1)
        except PermissionError:
            pass

    search_recursive(search_path, 0)
    return results


def fetch_marketplace_plugins(
    source: Literal["github", "local"],
    repo: str = "",
    path: str = "",
) -> list[PluginInfo]:
    """Fetch available plugins from a marketplace.

    Uses the new discovery functions to read marketplace.json directly.

    Args:
        source: Either 'github' or 'local'.
        repo: GitHub repo in owner/repo format (for github source).
        path: Local filesystem path (for local source).

    Returns:
        List of PluginInfo for each plugin found, empty if fetch fails.
    """
    if source == "github":
        return discover_plugins_from_github(repo)
    else:
        return discover_plugins_from_local(Path(path))


def prompt_select(message: str, choices: list[str], default: str | None = None) -> str | None:
    """Interactive select prompt using questionary.

    Args:
        message: The prompt message.
        choices: List of choices to display.
        default: Default selection.

    Returns:
        Selected choice string, or None if cancelled.
    """
    return questionary.select(
        message,
        choices=choices,
        default=default,
    ).ask()


def prompt_checkbox(
    message: str,
    choices: list[tuple[str, str]],
    checked_by_default: bool = True,
) -> list[str] | None:
    """Interactive checkbox prompt using questionary.

    Args:
        message: The prompt message.
        choices: List of (value, label) tuples.
        checked_by_default: Whether items are checked by default.

    Returns:
        List of selected values, or None if cancelled.
    """
    q_choices = [
        questionary.Choice(title=label, value=value, checked=checked_by_default)
        for value, label in choices
    ]
    return questionary.checkbox(message, choices=q_choices).ask()


def prompt_text(message: str, default: str = "") -> str | None:
    """Interactive text prompt using questionary.

    Args:
        message: The prompt message.
        default: Default value.

    Returns:
        Entered text, or None if cancelled.
    """
    return questionary.text(message, default=default).ask()


def prompt_confirm(message: str, default: bool = True) -> bool | None:
    """Interactive confirm prompt using questionary.

    Args:
        message: The prompt message.
        default: Default value.

    Returns:
        True/False, or None if cancelled.
    """
    return questionary.confirm(message, default=default).ask()


def prompt_path_with_search(
    console: Console,
    search_from: Path | None = None,
) -> Path | None:
    """Prompt for a local path with optional marketplace search.

    Offers to search for existing marketplace.json files.

    Args:
        console: Rich console for output.
        search_from: Directory to search from (defaults to cwd).

    Returns:
        Selected path, or None if cancelled.
    """
    search_path = search_from or Path.cwd()

    # First, offer to search for existing marketplaces
    should_search = prompt_confirm(
        f"Search for marketplaces in {search_path}?",
        default=True,
    )

    if should_search is None:
        return None

    if should_search:
        console.print()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Searching for marketplaces...", total=None)
            found = find_local_marketplaces(search_path)

        if found:
            console.print(f"  Found {len(found)} marketplace(s)")
            console.print()

            # Build choices from found marketplaces
            choices = [str(p) for p in found]
            choices.append("Enter path manually")

            selected = prompt_select("Select a marketplace:", choices)

            if selected is None:
                return None

            if selected != "Enter path manually":
                return Path(selected)

    # Manual path entry
    console.print()
    path_str = prompt_text("Enter local path:")

    if path_str is None:
        return None

    return Path(path_str).expanduser().resolve()


def generate_config_yaml(init_config: InitConfig) -> str:
    """Generate YAML string from InitConfig.

    Args:
        init_config: The collected configuration choices.

    Returns:
        YAML string ready to write to file.
    """
    # Build marketplaces dict
    marketplaces: dict[str, dict[str, str]] = {}
    for mp in init_config.marketplaces:
        if mp.source == "github":
            marketplaces[mp.name] = {
                "source": "github",
                "repo": mp.repo,
            }
        else:
            marketplaces[mp.name] = {
                "source": "local",
                "path": mp.path,
            }

    # Build plugins list
    plugins: list[dict[str, str | bool]] = []
    for plugin in init_config.plugins:
        plugins.append(
            {
                "id": f"{plugin.id}@{plugin.marketplace}",
                "scope": plugin.scope,
                "enabled": plugin.enabled,
            }
        )

    # Build config structure
    config = {
        "version": 1,
        "targets": [
            {
                "type": "claude",
                "config": {
                    "marketplaces": marketplaces,
                    "plugins": plugins,
                },
            }
        ],
    }

    # Generate YAML with nice formatting
    return yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)


def write_config(init_config: InitConfig) -> Path:
    """Write config file, creating directories as needed.

    Args:
        init_config: The configuration to write.

    Returns:
        Path to the written config file.
    """
    config_path = init_config.config_path

    # Create parent directories
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate and write YAML
    yaml_content = generate_config_yaml(init_config)
    config_path.write_text(yaml_content)

    return config_path


def prompt_conversion_targets(
    console: Console, default_scope: str = "user"
) -> ConversionChoice | None:
    """Prompt user for conversion target selection.

    Args:
        console: Rich console for output.
        default_scope: Default scope from plugin selection ("user" or "project").

    Returns:
        ConversionChoice with user selections, or None if cancelled.
    """
    console.print()
    console.print("[subheader]Plugin Conversion[/subheader]")
    console.print("You can convert your Claude plugins to work with other AI coding tools.")
    console.print()

    # Ask if user wants to convert
    wants_conversion = prompt_confirm(
        "Convert plugins to other tools (Codex, Cursor, OpenCode)?",
        default=False,
    )

    if wants_conversion is None:
        return None  # Cancelled

    if not wants_conversion:
        return ConversionChoice(enabled=False)

    # Select targets
    target_choices = [
        ("codex", "Codex (OpenAI) - .codex/ directory"),
        ("cursor", "Cursor - .cursor/ directory"),
        ("opencode", "OpenCode - .opencode/ directory"),
    ]

    selected_targets = prompt_checkbox(
        "Select target tools:",
        target_choices,
        checked_by_default=True,
    )

    if selected_targets is None:
        return None  # Cancelled

    if not selected_targets:
        return ConversionChoice(enabled=False)

    # Use the same scope as the plugins
    scope = default_scope

    # Show where files will be written
    console.print()
    if scope == "user":
        console.print("[info]Converted files will be written to:[/info]")
        for target in selected_targets:
            console.print(f"  {SYMBOLS['bullet']} ~/.{target}/")
    else:
        console.print("[info]Converted files will be written to:[/info]")
        for target in selected_targets:
            console.print(f"  {SYMBOLS['bullet']} .{target}/")

    # Ask if they want to customize location
    use_custom = prompt_confirm(
        "Use custom output directory instead?",
        default=False,
    )

    if use_custom is None:
        return None  # Cancelled

    custom_output_dir = None
    if use_custom:
        output_dir_str = prompt_text(
            "Output directory for all converted files:",
            default=".",
        )
        if output_dir_str is None:
            return None  # Cancelled
        custom_output_dir = Path(output_dir_str)

    return ConversionChoice(
        enabled=True,
        targets=selected_targets,
        scope=scope,
        custom_output_dir=custom_output_dir,
    )


def run_init_wizard(console: Console, output_path: Path | None = None) -> InitConfig | None:
    """Run the interactive init wizard.

    Args:
        console: Rich console for output.
        output_path: Optional explicit output path.

    Returns:
        InitConfig with collected choices, or None if cancelled.
    """
    # Header
    console.print()
    console.print(Panel.fit("[header]ai-config init[/header]", border_style="cyan"))
    console.print()

    # Check prerequisites
    console.print("Checking prerequisites...")
    cli_installed, cli_version = check_claude_cli()

    if cli_installed:
        console.print(
            f"  [success]{SYMBOLS['pass']}[/success] Claude CLI installed ({cli_version})"
        )
    else:
        console.print(f"  [error]{SYMBOLS['fail']}[/error] Claude CLI not found")
        console.print()
        console.print("[hint]Install Claude Code: npm install -g @anthropic-ai/claude-code[/hint]")
        return None

    console.print()

    # Choose config location
    if output_path:
        config_path = output_path
        console.print(f"Config will be created at: {config_path}")
    else:
        location = prompt_select(
            "Where should the config be created?",
            choices=[
                ".ai-config/config.yaml (this project)",
                "~/.ai-config/config.yaml (global)",
            ],
            default=".ai-config/config.yaml (this project)",
        )

        if location is None:
            return None

        if "this project" in location:
            config_path = Path.cwd() / ".ai-config" / "config.yaml"
        else:
            config_path = Path.home() / ".ai-config" / "config.yaml"

    # Check for existing config
    if config_path.exists():
        console.print()
        console.print(f"[warning]Config already exists at {config_path}[/warning]")
        overwrite = prompt_confirm("Overwrite existing config?", default=False)
        if not overwrite:
            return None

    console.print()
    console.print("━" * 40)
    console.print()

    # Collect marketplaces and plugins
    init_config = InitConfig(config_path=config_path)

    while True:
        mp_source = prompt_select(
            "Add a marketplace? (marketplaces contain plugins you can install)",
            choices=[
                "GitHub repository",
                "Local directory",
                "Skip (no more marketplaces)",
            ],
            default="GitHub repository",
        )

        if mp_source is None or mp_source == "Skip (no more marketplaces)":
            break

        console.print()

        if mp_source == "GitHub repository":
            repo_input = prompt_text(
                "GitHub repo (owner/repo or full URL):",
            )

            if repo_input is None:
                return None

            repo = parse_github_repo(repo_input)
            if repo is None:
                console.print("[warning]Invalid format. Examples:[/warning]")
                console.print("  - owner/repo")
                console.print("  - https://github.com/owner/repo")
                continue

            # Suggest marketplace name from repo
            suggested_name = repo.replace("/", "-")
            name = prompt_text("Marketplace name:", default=suggested_name)

            if name is None:
                return None

            marketplace = MarketplaceChoice(
                name=name,
                source="github",
                repo=repo,
            )

        else:  # Local directory
            path = prompt_path_with_search(console)

            if path is None:
                return None

            if not path.exists():
                console.print(f"[warning]Path does not exist: {path}[/warning]")
                add_anyway = prompt_confirm("Add anyway?", default=True)
                if not add_anyway:
                    continue

            # Read the actual marketplace name from marketplace.json
            # Claude CLI uses this name, not user-provided names
            actual_name = get_marketplace_name(path)

            if actual_name:
                console.print(
                    f"  [info]Found marketplace name in manifest:[/info] [key]{actual_name}[/key]"
                )
                name = actual_name
            else:
                # Fallback to directory name if we can't read marketplace.json
                console.print("  [warning]Could not read marketplace name from manifest[/warning]")
                suggested_name = path.name
                name = prompt_text("Marketplace name:", default=suggested_name)

                if name is None:
                    return None

            marketplace = MarketplaceChoice(
                name=name,
                source="local",
                path=str(path),
            )

        init_config.marketplaces.append(marketplace)

        # Show marketplace added confirmation
        console.print()
        console.print(
            f"[success]{SYMBOLS['pass']}[/success] Added marketplace: [key]{marketplace.name}[/key]"
        )
        if marketplace.source == "github":
            console.print(f"    Source: github ({marketplace.repo})")
        else:
            console.print(f"    Source: local ({marketplace.path})")

        # Fetch and select plugins from this marketplace
        console.print()
        console.print("Discovering plugins...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(f"Fetching plugins from {marketplace.name}...", total=None)
            plugins = fetch_marketplace_plugins(
                marketplace.source,
                marketplace.repo,
                marketplace.path,
            )

        if plugins:
            console.print(f"  [success]{SYMBOLS['pass']}[/success] Found {len(plugins)} plugin(s):")
            for p in plugins:
                desc = f" - {p.description}" if p.description else ""
                console.print(f"    {SYMBOLS['bullet']} {p.id}{desc}")
            console.print()

            # Build checkbox choices
            choices = [
                (p.id, f"{p.id} - {p.description}" if p.description else p.id) for p in plugins
            ]

            selected = prompt_checkbox(
                "Select plugins to enable:",
                choices,
                checked_by_default=True,
            )

            if selected is None:
                return None

            if selected:
                # Ask for scope with explanation
                console.print()
                scope_choices = [f"{scope} - {desc}" for scope, desc in SCOPE_CHOICES.items()]
                scope_selection = prompt_select(
                    "Where should plugins be installed?",
                    choices=scope_choices,
                    default=scope_choices[0],  # user is first/default
                )

                if scope_selection is None:
                    return None

                # Extract scope from selection (first word)
                selected_scope = scope_selection.split(" - ")[0]

                for plugin_id in selected:
                    init_config.plugins.append(
                        PluginChoice(
                            id=plugin_id,
                            marketplace=marketplace.name,
                            enabled=True,
                            scope=selected_scope,
                        )
                    )
        else:
            console.print(
                f"  [warning]{SYMBOLS['warn']}[/warning] No plugins found in marketplace.json"
            )
            console.print("    (The marketplace was added but contains no plugins yet)")

        console.print()

        add_another = prompt_confirm("Add another marketplace?", default=False)
        if not add_another:
            break

        console.print()

    # Ask about conversion if plugins were selected
    if init_config.plugins:
        console.print()
        console.print("━" * 40)

        # Use the scope from the first plugin (they should all be the same)
        default_scope = init_config.plugins[0].scope if init_config.plugins else "user"

        conversion_choice = prompt_conversion_targets(console, default_scope)
        if conversion_choice is None:
            return None

        init_config.conversion = conversion_choice

    console.print()
    console.print("━" * 40)
    console.print()

    # Show preview
    console.print("[subheader]Config preview:[/subheader]")
    console.print()
    yaml_preview = generate_config_yaml(init_config)
    console.print(yaml_preview)

    # Show conversion preview if enabled
    if init_config.conversion and init_config.conversion.enabled:
        console.print()
        console.print("[subheader]Conversion preview:[/subheader]")
        console.print(f"  Targets: {', '.join(init_config.conversion.targets)}")
        console.print(f"  Scope: {init_config.conversion.scope}")
        if init_config.conversion.custom_output_dir:
            console.print(f"  Output: {init_config.conversion.custom_output_dir}")
        else:
            for target in init_config.conversion.targets:
                output_path = init_config.conversion.get_output_dir(target) / f".{target}"
                console.print(f"  {SYMBOLS['bullet']} {target}: {output_path}")

    # Confirm write
    write_ok = prompt_confirm(f"Write config to {config_path}?", default=True)
    if not write_ok:
        return None

    return init_config


def create_minimal_config(output_path: Path | None = None) -> InitConfig:
    """Create a minimal config without prompts.

    Args:
        output_path: Optional explicit output path.

    Returns:
        InitConfig with minimal/empty configuration.
    """
    if output_path:
        config_path = output_path
    else:
        config_path = Path.cwd() / ".ai-config" / "config.yaml"

    return InitConfig(config_path=config_path)
