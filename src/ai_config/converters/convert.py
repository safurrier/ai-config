"""High-level conversion functions.

Provides the main API for converting plugins between AI coding tools.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ai_config.converters.claude_parser import parse_claude_plugin
from ai_config.converters.emitters import EmitResult, get_emitter
from ai_config.converters.ir import InstallScope, PluginIR, Severity, TargetTool
from ai_config.converters.report import ConversionReport


def convert_plugin(
    plugin_path: Path,
    targets: list[TargetTool],
    output_dir: Path | None = None,
    scope: InstallScope = InstallScope.PROJECT,
    dry_run: bool = False,
    best_effort: bool = False,
    commands_as_skills: bool = False,
) -> dict[TargetTool, ConversionReport]:
    """Convert a Claude Code plugin to one or more target tool formats.

    Args:
        plugin_path: Path to the Claude plugin directory
        targets: List of target tools to convert to
        output_dir: Base output directory. If None, no files are written.
        scope: Installation scope (user or project)
        dry_run: If True, don't write files, just generate report
        best_effort: If True, continue conversion even on errors
        commands_as_skills: If True, convert commands to skills (Codex only).
            Default False emits commands as prompts for 1:1 behavior with Claude.

    Returns:
        Dictionary mapping target tools to their conversion reports
    """
    # Parse source plugin
    ir = parse_claude_plugin(plugin_path)

    # Check for parse errors
    if ir.has_errors() and not best_effort:
        # Return error reports for all targets
        reports = {}
        for target in targets:
            report = ConversionReport(
                source_plugin=ir.identity,
                target_tool=target,
                dry_run=dry_run,
                best_effort=best_effort,
            )
            for diag in ir.diagnostics:
                report.add_diagnostic(diag)
            reports[target] = report
        return reports

    # Convert to each target
    reports = {}
    for target in targets:
        report = _convert_to_target(
            ir=ir,
            target=target,
            output_dir=output_dir,
            scope=scope,
            dry_run=dry_run,
            best_effort=best_effort,
            commands_as_skills=commands_as_skills,
        )
        reports[target] = report

    return reports


def _convert_to_target(
    ir: PluginIR,
    target: TargetTool,
    output_dir: Path | None,
    scope: InstallScope,
    dry_run: bool,
    best_effort: bool,
    commands_as_skills: bool = False,
) -> ConversionReport:
    """Convert IR to a single target format."""
    report = ConversionReport(
        source_plugin=ir.identity,
        target_tool=target,
        timestamp=datetime.now(),
        dry_run=dry_run,
        best_effort=best_effort,
        output_directory=output_dir,
    )

    # Add source diagnostics
    for diag in ir.diagnostics:
        report.add_diagnostic(diag)

    # Get emitter and emit
    try:
        emitter = get_emitter(target, scope, commands_as_skills=commands_as_skills)
        result = emitter.emit(ir)
    except Exception as e:
        if best_effort:
            from ai_config.converters.ir import Diagnostic

            report.add_diagnostic(
                Diagnostic(
                    severity=Severity.ERROR,
                    message=f"Emitter failed: {e}",
                )
            )
            return report
        raise

    # Add emitter diagnostics
    for diag in result.diagnostics:
        report.add_diagnostic(diag)

    # Record component mappings
    for mapping in result.mappings:
        lost_features = list(mapping.lost_features)

        report.add_component(
            kind=mapping.component_kind,
            name=mapping.component_name,
            status=mapping.status,
            target_path=mapping.target_path,
            notes=mapping.notes,
            lost_features=lost_features,
        )

    # Write files (or preview in dry-run)
    if output_dir:
        for f in result.files:
            full_path = output_dir / f.path
            if isinstance(f.content, bytes):
                size = len(f.content)
            else:
                size = len(f.content.encode("utf-8"))

            if dry_run:
                action = "preview"
            elif full_path.exists():
                action = "update"
            else:
                action = "create"

            report.add_file(
                path=full_path,
                action=action,
                size_bytes=size,
            )

        # Actually write files if not dry-run
        if not dry_run:
            result.write_to(output_dir)

    return report


def convert_plugin_simple(
    plugin_path: Path | str,
    target: str | TargetTool,
    output_dir: Path | str | None = None,
) -> EmitResult:
    """Simple conversion function for quick use.

    Args:
        plugin_path: Path to the Claude plugin directory
        target: Target tool (string or enum)
        output_dir: Output directory (writes files if provided)

    Returns:
        EmitResult with files and diagnostics
    """
    plugin_path = Path(plugin_path)
    if isinstance(target, str):
        target = TargetTool(target)
    if output_dir:
        output_dir = Path(output_dir)

    # Parse and emit
    ir = parse_claude_plugin(plugin_path)
    emitter = get_emitter(target)
    result = emitter.emit(ir)

    # Write if output specified
    if output_dir:
        result.write_to(Path(output_dir))

    return result


def preview_conversion(
    plugin_path: Path | str,
    targets: list[str] | list[TargetTool],
    output_dir: Path | str | None = None,
    commands_as_skills: bool = False,
) -> str:
    """Preview what conversion would produce without writing files.

    Args:
        plugin_path: Path to the Claude plugin directory
        targets: List of target tools
        output_dir: Optional output directory for path display
        commands_as_skills: For Codex, convert commands to skills instead of prompts.

    Returns:
        Formatted preview string
    """
    plugin_path = Path(plugin_path)
    if output_dir:
        output_dir = Path(output_dir)

    # Normalize targets
    target_enums = [TargetTool(t) if isinstance(t, str) else t for t in targets]

    # Parse
    ir = parse_claude_plugin(plugin_path)

    lines = [
        f"Plugin: {ir.identity.name} (v{ir.identity.version or 'unknown'})",
        f"Source: {plugin_path}",
        "",
    ]

    # Check for parse errors
    if ir.has_errors():
        lines.append("⚠️ Parse errors:")
        for diag in ir.diagnostics:
            if diag.severity == Severity.ERROR:
                lines.append(f"  ✗ {diag.message}")
        lines.append("")

    # Preview each target
    for target in target_enums:
        lines.append(f"═══ {target.value.upper()} ═══")
        lines.append("")

        try:
            emitter = get_emitter(target, commands_as_skills=commands_as_skills)
            result = emitter.emit(ir)
            lines.append(result.preview(output_dir if output_dir is None else Path(output_dir)))
        except Exception as e:
            lines.append(f"Error: {e}")

        lines.append("")

    return "\n".join(lines)
