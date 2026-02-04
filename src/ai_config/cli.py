"""CLI for ai-config."""

import json
import signal
import sys
from pathlib import Path
from threading import Event

import click
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ai_config.cli_theme import SYMBOLS, create_console
from ai_config.config import (
    ConfigError,
    find_config_file,
    load_config,
    validate_marketplace_references,
)
from ai_config.operations import (
    get_status,
    sync_config,
    update_plugins,
    verify_sync,
)
from ai_config.scaffold import create_plugin
from ai_config.validators import VALIDATORS, run_validators_sync

console = create_console()
error_console = create_console(stderr=True)

# Command order for --help display (logical workflow order)
COMMAND_ORDER = ["init", "sync", "status", "watch", "update", "doctor", "plugin", "cache"]


class OrderedGroup(click.Group):
    """Click group that displays commands in a defined order."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Return commands in logical workflow order."""
        commands = super().list_commands(ctx)
        # Sort by COMMAND_ORDER index, unknown commands go to end
        return sorted(commands, key=lambda x: COMMAND_ORDER.index(x) if x in COMMAND_ORDER else 999)


@click.group(cls=OrderedGroup)
@click.version_option(package_name="ai-config-cli")
def main() -> None:
    """ai-config: Declarative plugin manager for Claude Code."""
    pass


@main.command()
@click.option("--config", "-c", "config_path", type=click.Path(exists=True, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
@click.option("--fresh", is_flag=True, help="Clear cache before syncing")
@click.option("--verify", is_flag=True, help="Verify sync after completion")
def sync(
    config_path: Path | None,
    dry_run: bool,
    fresh: bool,
    verify: bool,
) -> None:
    """Sync plugins and marketplaces to match config.

    \b
    When to use:
      - After editing .ai-config/config.yaml to add/remove plugins
      - After cloning a repo with an existing ai-config setup
      - To fix drift between config and installed state

    \b
    What you'll see:
      - Table of actions taken (install/enable/disable)
      - "No changes needed" means config already matches reality
      - Errors show which plugins/marketplaces failed

    \b
    Typical workflow:
      1. Edit config.yaml
      2. Run: ai-config sync --dry-run  (preview changes)
      3. Run: ai-config sync            (apply changes)
      4. Verify: ai-config doctor       (check health)
    """
    try:
        config = load_config(config_path)
    except ConfigError as e:
        error_console.print(f"[error]Error loading config:[/error] {e}")
        sys.exit(1)

    # Validate marketplace references
    ref_errors = validate_marketplace_references(config)
    if ref_errors:
        error_console.print("[error]Config validation errors:[/error]")
        for error in ref_errors:
            error_console.print(f"  {SYMBOLS['bullet']} {error}")
        sys.exit(1)

    if dry_run:
        console.print("[warning]Dry run mode - no changes will be made[/warning]")
        results = sync_config(config, dry_run=dry_run, fresh=fresh)
    else:
        # Use spinner for actual sync operations
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Syncing plugins...", total=None)
            results = sync_config(config, dry_run=dry_run, fresh=fresh)

    for target_type, result in results.items():
        console.print(f"\n[subheader]Target: {target_type}[/subheader]")

        if result.actions_taken:
            # Use a table for actions
            table = Table(show_header=True, header_style="bold", box=None)
            table.add_column("Action", style="key")
            table.add_column("Target")
            table.add_column("Scope", style="info")

            for action in result.actions_taken:
                table.add_row(
                    action.action,
                    action.target,
                    action.scope or "-",
                )
            console.print(table)
        else:
            console.print(f"  [success]{SYMBOLS['pass']}[/success] No changes needed")

        if result.errors:
            console.print("[error]Errors:[/error]")
            for error in result.errors:
                console.print(f"  {SYMBOLS['fail']} {error}")

    # Verify if requested
    if verify and not dry_run:
        console.print("\n[subheader]Verification:[/subheader]")
        discrepancies = verify_sync(config)
        if discrepancies:
            console.print("[error]Out of sync:[/error]")
            for d in discrepancies:
                console.print(f"  {SYMBOLS['fail']} {d}")
            sys.exit(1)
        else:
            console.print(f"[success]{SYMBOLS['pass']} All in sync![/success]")


@main.command()
@click.option("--config", "-c", "config_path", type=click.Path(exists=True, path_type=Path))
@click.option("--verify", is_flag=True, help="Verify current state matches config")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def status(
    config_path: Path | None,
    verify: bool,
    as_json: bool,
) -> None:
    """Show current plugin and marketplace status.

    \b
    When to use:
      - See what plugins are currently installed in Claude Code
      - Check if plugins are enabled or disabled
      - Compare actual state with config using --verify

    \b
    What you'll see:
      - Table of installed plugins with ID, version, scope, and enabled status
      - List of registered marketplaces
      - Use --json for machine-readable output

    \b
    Typical workflow:
      1. Run: ai-config status          (see current state)
      2. Run: ai-config status --verify (compare with config)
      3. Run: ai-config sync            (if out of sync)
    """
    result = get_status()

    if as_json:
        output = {
            "target": result.target_type,
            "plugins": [
                {
                    "id": p.id,
                    "installed": p.installed,
                    "enabled": p.enabled,
                    "scope": p.scope,
                    "version": p.version,
                }
                for p in result.plugins
            ],
            "marketplaces": result.marketplaces,
            "errors": result.errors,
        }
        console.print_json(json.dumps(output))
        return

    # Display plugins table
    console.print("\n[subheader]Installed Plugins:[/subheader]")
    if result.plugins:
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("ID", style="key")
        table.add_column("Version")
        table.add_column("Scope")
        table.add_column("Enabled")

        for plugin in result.plugins:
            if plugin.enabled:
                enabled_str = f"[success]{SYMBOLS['pass']}[/success]"
            else:
                enabled_str = f"[error]{SYMBOLS['fail']}[/error]"
            table.add_row(
                plugin.id,
                plugin.version or "-",
                plugin.scope or "-",
                enabled_str,
            )
        console.print(table)
    else:
        console.print("  No plugins installed")

    # Display marketplaces
    console.print("\n[subheader]Registered Marketplaces:[/subheader]")
    if result.marketplaces:
        for mp in result.marketplaces:
            console.print(f"  {SYMBOLS['bullet']} {mp}")
    else:
        console.print("  No marketplaces registered")

    # Show errors if any
    if result.errors:
        console.print("\n[error]Errors:[/error]")
        for error in result.errors:
            console.print(f"  {SYMBOLS['fail']} {error}")

    # Verify against config if requested
    if verify:
        console.print("\n[subheader]Verification:[/subheader]")
        try:
            config = load_config(config_path)
            discrepancies = verify_sync(config)
            if discrepancies:
                console.print("[error]Out of sync:[/error]")
                for d in discrepancies:
                    console.print(f"  {SYMBOLS['fail']} {d}")
                sys.exit(1)
            else:
                console.print(f"[success]{SYMBOLS['pass']} All in sync![/success]")
        except ConfigError as e:
            error_console.print(f"[error]Cannot verify - config error:[/error] {e}")
            sys.exit(1)


@main.command()
@click.option("--all", "update_all", is_flag=True, help="Update all plugins")
@click.option("--fresh", is_flag=True, help="Clear cache before updating")
@click.argument("plugins", nargs=-1)
def update(
    update_all: bool,
    fresh: bool,
    plugins: tuple[str, ...],
) -> None:
    """Update plugins to latest versions.

    \b
    When to use:
      - Get latest plugin versions from marketplaces
      - Update a specific plugin after upstream changes
      - Refresh all plugins with --all

    \b
    What you'll see:
      - Lists plugins that were updated
      - Shows errors for failed updates

    \b
    Typical workflow:
      1. Run: ai-config update --all    (update everything)
      2. Run: ai-config update plugin1  (update specific plugin)
      3. Run: ai-config doctor          (verify health after update)
    """
    if not update_all and not plugins:
        error_console.print("[error]Specify plugins to update or use --all[/error]")
        sys.exit(1)

    plugin_ids = None if update_all else list(plugins)

    # Use spinner for update operation
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Updating plugins...", total=None)
        result = update_plugins(plugin_ids=plugin_ids, fresh=fresh)

    if result.actions_taken:
        console.print(f"[success]{SYMBOLS['pass']} Updated plugins:[/success]")
        for action in result.actions_taken:
            console.print(f"  {SYMBOLS['arrow']} {action.target}")

    if result.errors:
        console.print("[error]Errors:[/error]")
        for error in result.errors:
            console.print(f"  {SYMBOLS['fail']} {error}")

    if not result.success:
        sys.exit(1)


@main.group()
def cache() -> None:
    """Manage plugin cache.

    USE CASES:
      - Clear stale plugin data with 'cache clear'
      - Force re-download of plugins on next sync
    """
    pass


@cache.command(name="clear")
def cache_clear() -> None:
    """Clear the plugin cache.

    \b
    When to use:
      - When plugins seem stale or out of date
      - After changing marketplace URLs
      - When sync doesn't pick up expected changes

    \b
    What you'll see:
      - Success message when cache is cleared
      - Error message if clearing fails

    \b
    Typical workflow:
      1. Run: ai-config cache clear
      2. Run: ai-config sync --fresh  (re-fetch everything)
    """
    from ai_config.adapters import claude

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Clearing cache...", total=None)
        result = claude.clear_cache()

    if result.success:
        console.print(f"[success]{SYMBOLS['pass']} Cache cleared successfully[/success]")
    else:
        error_console.print(f"[error]Failed to clear cache:[/error] {result.stderr}")
        sys.exit(1)


@main.group()
def plugin() -> None:
    """Plugin management commands.

    Subcommands:
      create - Scaffold a new plugin
    """
    pass


@plugin.command(name="create")
@click.argument("name")
@click.option(
    "--path",
    type=click.Path(path_type=Path),
    help="Base path for plugin directory",
)
def plugin_create(name: str, path: Path | None) -> None:
    """Create a new plugin scaffold.

    \b
    When to use:
      - Start a new plugin project from scratch
      - Create a local plugin for testing skills/hooks

    \b
    What you'll see:
      - Creates directory with manifest.yaml, skills/, and hooks/
      - Shows next steps for plugin development

    \b
    Typical workflow:
      1. Run: ai-config plugin create my-plugin
      2. Edit my-plugin/manifest.yaml
      3. Add skills to my-plugin/skills/
      4. Add to config.yaml as local marketplace
      5. Run: ai-config sync
    """
    plugin_dir = create_plugin(name, path)
    console.print(f"[success]{SYMBOLS['pass']} Created plugin scaffold at:[/success] {plugin_dir}")
    console.print("\n[subheader]Next steps:[/subheader]")
    console.print(f"  1. Edit {plugin_dir}/manifest.yaml")
    console.print(f"  2. Add skills to {plugin_dir}/skills/")
    console.print(f"  3. Add hooks to {plugin_dir}/hooks/")


@main.command()
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output path for config file")
@click.option("--non-interactive", is_flag=True, help="Create minimal config without prompts")
def init(output: Path | None, non_interactive: bool) -> None:
    """Create a new ai-config configuration file interactively.

    \b
    When to use:
      - First-time setup of ai-config in a new project
      - Starting fresh with a new plugin configuration
      - Creating config without writing YAML manually

    \b
    What you'll see:
      - Interactive wizard walks through marketplace/plugin selection
      - Creates .ai-config/config.yaml (or custom path with -o)
      - Use --non-interactive for minimal empty config

    \b
    Typical workflow:
      1. Run: ai-config init           (interactive wizard)
      2. Follow prompts to add marketplaces and plugins
      3. Run: ai-config sync           (install plugins)
      4. Run: ai-config doctor         (verify setup)
    """
    from ai_config.init import create_minimal_config, run_init_wizard, write_config

    if non_interactive:
        # Generate minimal config without prompts
        init_config = create_minimal_config(output)
        path = write_config(init_config)
        console.print(f"[success]{SYMBOLS['pass']} Created minimal config at {path}[/success]")
        console.print("\n[subheader]Next steps:[/subheader]")
        console.print("  1. Edit the config file to add marketplaces and plugins")
        console.print("  2. Run: ai-config sync")
        return

    result = run_init_wizard(console, output)
    if result is None:
        console.print("[warning]Cancelled[/warning]")
        sys.exit(1)

    assert result is not None  # Type narrowing for type checker
    path = write_config(result)
    console.print()
    console.print(f"[success]{SYMBOLS['pass']} Config created at {path}[/success]")
    console.print("\n[subheader]Next steps:[/subheader]")
    console.print("  ai-config sync      # Install plugins")
    console.print("  ai-config doctor    # Verify setup")


@main.command()
@click.option("--config", "-c", "config_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--category",
    type=click.Choice(list(VALIDATORS.keys())),
    multiple=True,
    help="Run only specific validation categories",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Show all checks including passed")
def doctor(
    config_path: Path | None,
    category: tuple[str, ...],
    as_json: bool,
    verbose: bool,
) -> None:
    """Diagnose plugin, marketplace, and component issues.

    \b
    When to use:
      - Verify setup after sync or update
      - Debug why a plugin or skill isn't working
      - Check for configuration drift or missing dependencies

    \b
    What you'll see:
      - Shows pass/fail/warn status for each check
      - Failed checks include fix_hint with remediation steps
      - Use --verbose to see all checks (including passed)
      - Use --json for machine-readable output

    \b
    Checks performed:
      - Marketplace registration and accessibility
      - Plugin installation and enabled state
      - Skill file validity and frontmatter
      - Hook configuration and script existence
      - MCP server configuration

    \b
    Typical workflow:
      1. Run: ai-config doctor          (check health)
      2. Read fix_hint for any failures
      3. Run suggested commands to fix issues
      4. Re-run: ai-config doctor       (verify fixes)
    """
    from ai_config.cli_render import render_doctor_output

    try:
        actual_config_path = find_config_file(config_path)
        config = load_config(config_path)
    except ConfigError as e:
        error_console.print(f"[error]Error loading config:[/error] {e}")
        sys.exit(1)

    # Run validators
    categories_to_run = list(category) if category else None
    reports = run_validators_sync(config, actual_config_path, categories_to_run)

    if as_json:
        output = {
            "reports": {
                cat: {
                    "target": report.target,
                    "passed": report.passed,
                    "has_warnings": report.has_warnings,
                    "results": [
                        {
                            "check_name": r.check_name,
                            "status": r.status,
                            "message": r.message,
                            "details": r.details,
                            "fix_hint": r.fix_hint,
                        }
                        for r in report.results
                    ],
                }
                for cat, report in reports.items()
            }
        }
        console.print_json(json.dumps(output))
        return

    console.print()
    console.print(Panel.fit("[header]ai-config doctor[/header]", border_style="cyan"))
    console.print()

    _total_pass, _total_warn, total_fail = render_doctor_output(reports, config, console, verbose)

    if total_fail > 0:
        sys.exit(1)


@main.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@click.option(
    "--debounce",
    type=float,
    default=1.5,
    help="Seconds to wait after changes before syncing",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show changes without syncing",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show all file events",
)
def watch(
    config_path: Path | None,
    debounce: float,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Watch config and plugin directories, auto-sync on changes.

    \b
    When to use:
      - During plugin development to auto-sync on skill/hook edits
      - When iterating on config to see changes applied immediately
      - Keeping plugins in sync while editing across multiple files

    \b
    What you'll see:
      - Which paths are being watched (config + plugin directories)
      - Detected changes grouped by type (config vs plugin)
      - Sync results after each batch of changes

    \b
    How it works:
      1. Start: ai-config watch
      2. Edit your plugin files or config
      3. Changes are batched (1.5s debounce)
      4. Sync runs automatically
      5. Press Ctrl+C to stop

    \b
    Important limitation:
      Claude Code only loads plugins at session start. After syncing,
      you must restart Claude Code for changes to take effect.
      Use: claude --resume to continue your previous session.
    """
    from ai_config.watch import FileChange, collect_watch_paths, run_watch_loop

    try:
        actual_config_path = find_config_file(config_path)
        config = load_config(config_path)
    except ConfigError as e:
        error_console.print(f"[error]Error loading config:[/error] {e}")
        sys.exit(1)

    watch_config = collect_watch_paths(config, actual_config_path)

    # Display watch info
    console.print()
    console.print(Panel.fit("[header]ai-config watch[/header]", border_style="cyan"))
    console.print()

    console.print("[subheader]Watching:[/subheader]")
    console.print(f"  {SYMBOLS['bullet']} Config: {watch_config.config_path}")
    for plugin_dir in watch_config.plugin_directories:
        console.print(f"  {SYMBOLS['bullet']} Plugin: {plugin_dir}")

    if not watch_config.plugin_directories:
        console.print("  [info](no local plugin directories)[/info]")

    console.print()
    if dry_run:
        console.print("[warning]Dry run: true[/warning]")
    console.print("[info]Press Ctrl+C to stop[/info]")
    console.print()
    console.print(
        "[dim]Note: Claude Code loads plugins at session start. "
        "After changes sync, restart Claude Code to apply them.[/dim]"
    )
    console.print("[dim]Tip: Use 'claude --resume' to continue your previous session.[/dim]")
    console.print()

    # Track sync count
    sync_count = 0

    def on_changes(changes: list[FileChange]) -> None:
        """Handle detected changes."""
        nonlocal sync_count
        sync_count += 1

        config_changes = [c for c in changes if c.change_type == "config"]
        plugin_changes = [c for c in changes if c.change_type == "plugin_directory"]

        console.print(f"[subheader]Changes detected (batch #{sync_count}):[/subheader]")
        if config_changes:
            console.print(f"  Config: {len(config_changes)} change(s)")
            if verbose:
                for c in config_changes:
                    console.print(f"    {SYMBOLS['arrow']} {c.event_type}: {c.path}")
        if plugin_changes:
            console.print(f"  Plugins: {len(plugin_changes)} change(s)")
            if verbose:
                for c in plugin_changes:
                    console.print(f"    {SYMBOLS['arrow']} {c.event_type}: {c.path}")

        # Reload config if it changed
        try:
            current_config = load_config(config_path)
        except ConfigError as e:
            error_console.print(f"[error]Config error:[/error] {e}")
            return

        if dry_run:
            console.print("[warning]Dry run - no sync performed[/warning]")
            return

        # Sync
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Syncing...", total=None)
            results = sync_config(current_config, dry_run=False, fresh=False)

        total_actions = sum(len(r.actions_taken) for r in results.values())
        if total_actions > 0:
            console.print(f"[success]{SYMBOLS['pass']} Synced {total_actions} action(s)[/success]")
        else:
            console.print(f"[info]{SYMBOLS['pass']} No sync needed[/info]")

        for result in results.values():
            if result.errors:
                for error in result.errors:
                    error_console.print(f"  [error]{SYMBOLS['fail']}[/error] {error}")

        console.print()

    # Setup signal handler for graceful shutdown
    stop_event = Event()

    def signal_handler(signum: int, frame: object) -> None:
        console.print("\n[info]Stopping...[/info]")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the watch loop
    run_watch_loop(
        watch_config=watch_config,
        on_changes=on_changes,
        stop_event=stop_event,
        debounce_seconds=debounce,
    )

    console.print(f"[success]{SYMBOLS['pass']} Watch stopped[/success]")


if __name__ == "__main__":
    main()
