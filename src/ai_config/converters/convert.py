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
from ai_config.pi_ownership import (
    PiDesiredFile,
    apply_pi_reconciliation,
    load_pi_ownership,
    standalone_pi_source_identity,
)


def _standalone_pi_retained_sources(root: Path, source_plugin: str) -> set[str]:
    """Keep other standalone projections while the core reconciler checks collisions."""
    previous = load_pi_ownership(root)
    return {entry.source_plugin for entry in previous.values()} - {source_plugin}


def convert_plugin(
    plugin_path: Path,
    targets: list[TargetTool],
    output_dir: Path | None = None,
    scope: InstallScope = InstallScope.PROJECT,
    dry_run: bool = False,
    best_effort: bool = False,
) -> dict[TargetTool, ConversionReport]:
    """Convert a Claude Code plugin to one or more target tool formats.

    Args:
        plugin_path: Path to the Claude plugin directory
        targets: List of target tools to convert to
        output_dir: Base output directory. If None, no files are written.
        scope: Installation scope (user or project)
        dry_run: If True, don't write files, just generate report
        best_effort: If True, continue conversion even on errors

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
            source_path=plugin_path,
            target=target,
            output_dir=output_dir,
            scope=scope,
            dry_run=dry_run,
            best_effort=best_effort,
        )
        reports[target] = report

    return reports


def _convert_to_target(
    ir: PluginIR,
    source_path: Path,
    target: TargetTool,
    output_dir: Path | None,
    scope: InstallScope,
    dry_run: bool,
    best_effort: bool,
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
        emitter = get_emitter(target, scope)
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

    # Pi output is always reconciled through its ownership ledger. This lets a
    # standalone conversion remove only this plugin's stale files while retaining
    # projections from other plugins at the same root.
    if output_dir and target == TargetTool.PI:
        source_plugin = standalone_pi_source_identity(source_path, ir.identity.plugin_id)
        desired = [
            PiDesiredFile(
                source_plugin,
                file.path,
                file.content.encode("utf-8") if isinstance(file.content, str) else file.content,
                file.executable,
            )
            for file in result.files
        ]
        retained_sources = _standalone_pi_retained_sources(output_dir, source_plugin)
        actions = apply_pi_reconciliation(
            output_dir,
            desired,
            dry_run=dry_run,
            retained_sources=retained_sources,
            ownership_domain="standalone",
        )
        desired_sizes = {item.relative_path: len(item.content) for item in desired}
        for item in actions:
            report.add_file(
                path=output_dir / item.path,
                action=item.action.removesuffix("_pi_output"),
                size_bytes=desired_sizes.get(item.path, 0),
                reason=item.reason,
            )
    elif output_dir:
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

    # Pi writes must establish ownership, even through this convenience API.
    if output_dir:
        if target == TargetTool.PI:
            root = Path(output_dir)
            source_plugin = standalone_pi_source_identity(plugin_path, ir.identity.plugin_id)
            desired = [
                PiDesiredFile(
                    source_plugin,
                    file.path,
                    file.content.encode("utf-8") if isinstance(file.content, str) else file.content,
                    file.executable,
                )
                for file in result.files
            ]
            retained_sources = _standalone_pi_retained_sources(root, source_plugin)
            apply_pi_reconciliation(
                root, desired, retained_sources=retained_sources, ownership_domain="standalone"
            )
        else:
            result.write_to(Path(output_dir))

    return result


def preview_conversion(
    plugin_path: Path | str,
    targets: list[str] | list[TargetTool],
    output_dir: Path | str | None = None,
    scope: InstallScope = InstallScope.PROJECT,
) -> str:
    """Preview what conversion would produce without writing files.

    Args:
        plugin_path: Path to the Claude plugin directory
        targets: List of target tools
        output_dir: Optional output directory for path display
        scope: Installation scope to preview

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
            emitter = get_emitter(target, scope=scope)
            result = emitter.emit(ir)
            lines.append(result.preview(output_dir if output_dir is None else Path(output_dir)))
        except Exception as e:
            lines.append(f"Error: {e}")

        lines.append("")

    return "\n".join(lines)
