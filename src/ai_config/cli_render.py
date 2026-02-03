"""Rendering helpers for ai-config doctor output.

This module groups validation results by entity (plugin, marketplace, skill, etc.)
and renders them in a human-friendly format for the CLI.
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from rich.table import Table

from ai_config.cli_theme import SYMBOLS
from ai_config.types import AIConfig, PluginSource
from ai_config.validators.base import ValidationReport, ValidationResult

if TYPE_CHECKING:
    from rich.console import Console

EntityType = Literal["target", "marketplace", "plugin", "skill", "hook", "mcp"]


@dataclass
class EntityResult:
    """Grouped validation results for a single entity."""

    entity_type: EntityType
    entity_name: str
    passed: list[ValidationResult] = field(default_factory=list)
    warnings: list[ValidationResult] = field(default_factory=list)
    failures: list[ValidationResult] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """Return True if there are warnings or failures."""
        return bool(self.warnings or self.failures)

    @property
    def status_symbol(self) -> str:
        """Return status symbol for display."""
        if self.failures:
            return f"[red]{SYMBOLS['fail']}[/red]"
        if self.warnings:
            return f"[yellow]{SYMBOLS['warn']}[/yellow]"
        return f"[green]{SYMBOLS['pass']}[/green]"


def extract_entity_from_result(result: ValidationResult) -> tuple[EntityType, str] | None:
    """Extract entity type and name from a ValidationResult message.

    Parses patterns like:
    - "Plugin 'alex-ai@dots-plugins' is installed"
    - "Marketplace 'dots-plugins' path exists"
    - "Skill name 'python-core' is valid"
    - "Claude CLI available (claude 2.1.29)"

    Args:
        result: The validation result to parse.

    Returns:
        Tuple of (entity_type, entity_name) or None if not extractable.
    """
    message = result.message
    check_name = result.check_name

    # Target/Claude CLI checks
    if check_name.startswith("claude_cli"):
        # Extract version if present: "Claude CLI available (claude 2.1.29)"
        version_match = re.search(r"\((.*?)\)", message)
        version = version_match.group(1) if version_match else "claude"
        return ("target", version)

    # Hook checks - check before plugin since hooks also reference plugins
    # Check check_name first to properly categorize
    if "hook" in check_name.lower():
        plugin_match = re.search(r"Plugin '([^']+)'", message)
        if plugin_match:
            return ("hook", plugin_match.group(1))

    # MCP checks - check before plugin since MCPs also reference plugins
    if "mcp" in check_name.lower():
        # Try server name first: "MCP server 'server-name'"
        server_match = re.search(r"MCP server '([^']+)'", message)
        if server_match:
            return ("mcp", server_match.group(1))
        # Fall back to plugin ID
        plugin_match = re.search(r"Plugin '([^']+)'", message)
        if plugin_match:
            return ("mcp", plugin_match.group(1))

    # Plugin checks - look for plugin ID in quotes
    if "plugin" in check_name.lower() or "Plugin '" in message:
        plugin_match = re.search(r"Plugin '([^']+)'", message)
        if plugin_match:
            return ("plugin", plugin_match.group(1))

    # Marketplace checks - look for marketplace name in quotes
    if "marketplace" in check_name.lower() or "Marketplace '" in message:
        mp_match = re.search(r"Marketplace '([^']+)'", message)
        if mp_match:
            return ("marketplace", mp_match.group(1))

    # Skill checks - look for skill name
    if "skill" in check_name.lower() or "Skill" in message:
        # Patterns: "Skill name 'foo'", "SKILL.md not found in /path/skills/foo"
        skill_match = re.search(r"Skill name '([^']+)'", message)
        if skill_match:
            return ("skill", skill_match.group(1))
        # Fallback: extract from path like "/path/skills/skill-name"
        path_match = re.search(r"/skills/([^/]+)", message)
        if path_match:
            return ("skill", path_match.group(1))

    return None


def group_results_by_entity(
    results: list[ValidationResult],
) -> dict[EntityType, dict[str, EntityResult]]:
    """Group validation results by entity type and name.

    Args:
        results: List of validation results to group.

    Returns:
        Nested dict: entity_type -> entity_name -> EntityResult
    """
    grouped: dict[EntityType, dict[str, EntityResult]] = {}

    for result in results:
        entity_info = extract_entity_from_result(result)
        if entity_info is None:
            # Skip results we can't categorize
            continue

        entity_type, entity_name = entity_info

        if entity_type not in grouped:
            grouped[entity_type] = {}

        if entity_name not in grouped[entity_type]:
            grouped[entity_type][entity_name] = EntityResult(
                entity_type=entity_type,
                entity_name=entity_name,
            )

        entity_result = grouped[entity_type][entity_name]
        if result.status == "pass":
            entity_result.passed.append(result)
        elif result.status == "warn":
            entity_result.warnings.append(result)
        else:  # fail
            entity_result.failures.append(result)

    return grouped


def extract_claude_version(reports: dict[str, ValidationReport]) -> str | None:
    """Extract Claude CLI version from target validation results.

    Args:
        reports: Dict of category -> ValidationReport.

    Returns:
        Version string like "2.1.29 (Claude Code)" or None if not found.
    """
    target_report = reports.get("target")
    if not target_report:
        return None

    for result in target_report.results:
        if result.check_name == "claude_cli_available" and result.status == "pass":
            # Parse "Claude CLI available (2.1.29 (Claude Code))"
            # Use greedy match to handle nested parentheses
            match = re.search(r"\((.+)\)", result.message)
            if match:
                return match.group(1)
    return None


def count_by_status(
    results: list[ValidationResult],
) -> tuple[int, int, int]:
    """Count results by status.

    Args:
        results: List of validation results.

    Returns:
        Tuple of (pass_count, warn_count, fail_count).
    """
    pass_count = sum(1 for r in results if r.status == "pass")
    warn_count = sum(1 for r in results if r.status == "warn")
    fail_count = sum(1 for r in results if r.status == "fail")
    return pass_count, warn_count, fail_count


def render_doctor_output(
    reports: dict[str, ValidationReport],
    config: AIConfig,
    console: "Console",
    verbose: bool = False,
) -> tuple[int, int, int]:
    """Render the improved doctor output.

    Args:
        reports: Dict of category -> ValidationReport from validators.
        config: The loaded AIConfig.
        console: Rich Console instance for output.
        verbose: If True, show all individual checks.

    Returns:
        Tuple of (pass_count, warn_count, fail_count).
    """

    total_pass = 0
    total_warn = 0
    total_fail = 0

    # Collect all results for grouping
    all_results: list[ValidationResult] = []
    for report in reports.values():
        all_results.extend(report.results)

    # Count totals
    total_pass, total_warn, total_fail = count_by_status(all_results)

    # Group results by entity
    grouped = group_results_by_entity(all_results)

    # === Target Section ===
    console.print("[bold]Target:[/bold] claude")
    claude_version = extract_claude_version(reports)
    if claude_version:
        console.print(f"  Claude CLI {claude_version}")
    else:
        # Check for failure
        target_entities = grouped.get("target", {})
        for _entity_name, entity_result in target_entities.items():
            if entity_result.failures:
                for failure in entity_result.failures:
                    console.print(f"  [red]{SYMBOLS['fail']}[/red] {failure.message}")
                    if failure.fix_hint:
                        console.print(f"    [hint]Fix:[/hint] {failure.fix_hint}")
    console.print()

    # === Marketplaces Section ===
    _render_marketplaces_section(console, config, grouped, verbose)

    # === Plugins Section ===
    _render_plugins_section(console, config, grouped, verbose)

    # === Components Section ===
    _render_components_section(console, grouped, verbose)

    # === Summary ===
    console.print("[bold]Summary:[/bold]", end=" ")
    parts = []
    if total_fail > 0:
        parts.append(f"[red]{total_fail} error{'s' if total_fail != 1 else ''}[/red]")
    if total_warn > 0:
        parts.append(f"[yellow]{total_warn} warning{'s' if total_warn != 1 else ''}[/yellow]")
    if total_pass > 0:
        parts.append(f"[green]{total_pass} passed[/green]")

    if parts:
        console.print(", ".join(parts))
    else:
        console.print(f"[green]{SYMBOLS['pass']} All checks passed[/green]")

    return total_pass, total_warn, total_fail


def _render_marketplaces_section(
    console: "Console",
    config: AIConfig,
    grouped: dict[EntityType, dict[str, EntityResult]],
    verbose: bool,
) -> None:
    """Render the marketplaces section."""
    # Get configured marketplaces
    marketplaces_config: dict[str, tuple[str, str]] = {}  # name -> (source, path/repo)
    for target in config.targets:
        if target.type == "claude":
            for mp_name, mp_config in target.config.marketplaces.items():
                if mp_config.source == PluginSource.LOCAL:
                    marketplaces_config[mp_name] = ("local", mp_config.path)
                else:
                    marketplaces_config[mp_name] = ("github", mp_config.repo)

    mp_count = len(marketplaces_config)
    if mp_count == 0:
        console.print("[bold]Marketplaces:[/bold] None configured")
        console.print()
        return

    console.print(f"[bold]Marketplaces ({mp_count}):[/bold]")

    marketplace_entities = grouped.get("marketplace", {})

    # Build table for marketplaces
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("", width=1)  # Status column - no header needed
    table.add_column("Name", style="cyan")
    table.add_column("Source")
    table.add_column("Location", style="dim")

    issues_to_show: list[tuple[str, EntityResult]] = []

    for mp_name, (source, location) in marketplaces_config.items():
        entity_result = marketplace_entities.get(mp_name)

        # Truncate long paths
        display_location = _truncate_path(location, max_len=40)

        if entity_result and entity_result.has_issues:
            status = f"[red]{SYMBOLS['fail']}[/red]"
            issues_to_show.append((mp_name, entity_result))
        else:
            status = f"[green]{SYMBOLS['pass']}[/green]"

        table.add_row(status, mp_name, source, display_location)

    console.print(table)

    # Show issues below the table
    for mp_name, entity_result in issues_to_show:
        for failure in entity_result.failures:
            console.print(f"    {SYMBOLS['arrow']} [red]{mp_name}:[/red] {failure.message}")
            if failure.fix_hint:
                console.print(f"      [hint]Fix:[/hint] {failure.fix_hint}")
        for warning in entity_result.warnings:
            console.print(f"    {SYMBOLS['arrow']} [yellow]{mp_name}:[/yellow] {warning.message}")
            if warning.fix_hint:
                console.print(f"      [hint]Fix:[/hint] {warning.fix_hint}")

    if verbose:
        for mp_name in marketplaces_config:
            entity_result = marketplace_entities.get(mp_name)
            if entity_result:
                for passed in entity_result.passed:
                    console.print(f"    [green]{SYMBOLS['pass']}[/green] {passed.message}")

    console.print()


def _render_plugins_section(
    console: "Console",
    config: AIConfig,
    grouped: dict[EntityType, dict[str, EntityResult]],
    verbose: bool,
) -> None:
    """Render the plugins section."""
    # Get configured plugins
    plugins_config: list[tuple[str, bool]] = []  # (id, enabled)
    for target in config.targets:
        if target.type == "claude":
            for plugin in target.config.plugins:
                plugins_config.append((plugin.id, plugin.enabled))

    plugin_count = len(plugins_config)
    if plugin_count == 0:
        console.print("[bold]Plugins:[/bold] None configured")
        console.print()
        return

    console.print(f"[bold]Plugins ({plugin_count}):[/bold]")

    plugin_entities = grouped.get("plugin", {})

    # Build table for plugins
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("", width=1)  # Status column - no header needed
    table.add_column("Plugin ID", style="cyan")
    table.add_column("State")

    issues_to_show: list[tuple[str, EntityResult]] = []

    for plugin_id, enabled in plugins_config:
        entity_result = plugin_entities.get(plugin_id)

        # Truncate long plugin IDs
        display_id = _truncate_string(plugin_id, max_len=45)
        enabled_str = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"

        if entity_result and entity_result.has_issues:
            status = f"[red]{SYMBOLS['fail']}[/red]"
            issues_to_show.append((plugin_id, entity_result))
        else:
            status = f"[green]{SYMBOLS['pass']}[/green]"

        table.add_row(status, display_id, enabled_str)

    console.print(table)

    # Show issues below the table
    for plugin_id, entity_result in issues_to_show:
        for failure in entity_result.failures:
            console.print(f"    {SYMBOLS['arrow']} [red]{plugin_id}:[/red] {failure.message}")
            if failure.fix_hint:
                console.print(f"      [hint]Fix:[/hint] {failure.fix_hint}")
        for warning in entity_result.warnings:
            console.print(f"    {SYMBOLS['arrow']} [yellow]{plugin_id}:[/yellow] {warning.message}")

    if verbose:
        for plugin_id, _ in plugins_config:
            entity_result = plugin_entities.get(plugin_id)
            if entity_result:
                for passed in entity_result.passed:
                    console.print(f"    [green]{SYMBOLS['pass']}[/green] {passed.message}")

    console.print()


def _render_components_section(
    console: "Console",
    grouped: dict[EntityType, dict[str, EntityResult]],
    verbose: bool,
) -> None:
    """Render the components section (skills, hooks, MCPs)."""
    # Aggregate component counts
    component_types: list[tuple[EntityType, str]] = [
        ("skill", "Skills"),
        ("hook", "Hooks"),
        ("mcp", "MCPs"),
    ]

    has_any_components = any(entity_type in grouped for entity_type, _ in component_types)

    if not has_any_components:
        # No component validation results at all
        return

    console.print("[bold]Components:[/bold]")

    # Build summary table
    summary_table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    summary_table.add_column("Type")
    summary_table.add_column("Valid", justify="right", style="green")
    summary_table.add_column("Warnings", justify="right", style="yellow")
    summary_table.add_column("Errors", justify="right", style="red")

    # Collect issues for display after table
    all_issues: list[tuple[str, str, EntityResult]] = []  # (type_name, entity_name, result)

    for entity_type, display_name in component_types:
        entities = grouped.get(entity_type, {})
        if not entities:
            continue

        # Count valid vs errors
        valid_count = sum(1 for e in entities.values() if not e.has_issues)
        error_count = sum(1 for e in entities.values() if e.failures)
        warn_count = sum(1 for e in entities.values() if e.warnings and not e.failures)

        summary_table.add_row(
            display_name,
            str(valid_count) if valid_count else "-",
            str(warn_count) if warn_count else "-",
            str(error_count) if error_count else "-",
        )

        # Collect entities with issues
        for entity_name, entity_result in entities.items():
            if entity_result.has_issues:
                all_issues.append((display_name, entity_name, entity_result))

    console.print(summary_table)

    # Show issues below the summary table
    if all_issues:
        console.print()
        for type_name, entity_name, entity_result in all_issues:
            console.print(f"  [dim]{type_name}:[/dim] {entity_name}")
            for failure in entity_result.failures:
                console.print(f"    [red]{SYMBOLS['fail']}[/red] {failure.message}")
                if failure.fix_hint:
                    console.print(f"      [hint]Fix:[/hint] {failure.fix_hint}")
            for warning in entity_result.warnings:
                console.print(f"    [yellow]{SYMBOLS['warn']}[/yellow] {warning.message}")

    # In verbose mode, show all individual components
    if verbose:
        console.print()
        detail_table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        detail_table.add_column("", width=1)
        detail_table.add_column("Type", style="dim")
        detail_table.add_column("Name", style="cyan")

        for entity_type, display_name in component_types:
            entities = grouped.get(entity_type, {})
            for entity_name, entity_result in entities.items():
                if entity_result.failures:
                    status = f"[red]{SYMBOLS['fail']}[/red]"
                elif entity_result.warnings:
                    status = f"[yellow]{SYMBOLS['warn']}[/yellow]"
                else:
                    status = f"[green]{SYMBOLS['pass']}[/green]"
                detail_table.add_row(status, display_name, entity_name)

        console.print(detail_table)

    console.print()


def _truncate_path(path: str, max_len: int = 40) -> str:
    """Truncate a path for display, replacing home directory with ~."""
    import os

    home = os.path.expanduser("~")
    if path.startswith(home):
        path = "~" + path[len(home) :]

    if len(path) <= max_len:
        return path

    # Keep the last portion
    return "..." + path[-(max_len - 3) :]


def _truncate_string(s: str, max_len: int = 45) -> str:
    """Truncate a string with ellipsis if too long."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."
