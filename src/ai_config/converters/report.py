"""Conversion report generation.

Provides detailed, reusable reports for plugin conversions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_config.converters.ir import (
    Diagnostic,
    MappingStatus,
    PluginIdentity,
    Severity,
    TargetTool,
)


@dataclass
class ComponentResult:
    """Result of converting a single component."""

    kind: str
    name: str
    status: MappingStatus
    target_path: Path | None = None
    notes: str | None = None
    lost_features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "status": self.status.value,
            "target_path": str(self.target_path) if self.target_path else None,
            "notes": self.notes,
            "lost_features": self.lost_features,
        }


@dataclass
class FileResult:
    """Result of a file operation."""

    path: Path
    action: str  # "create", "update", "skip"
    size_bytes: int
    reason: str | None = None  # Why skipped, if applicable

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "action": self.action,
            "size_bytes": self.size_bytes,
            "reason": self.reason,
        }


@dataclass
class ConversionReport:
    """Complete record of a conversion operation."""

    # Identity
    source_plugin: PluginIdentity
    target_tool: TargetTool
    timestamp: datetime = field(default_factory=datetime.now)

    # Results
    components_converted: list[ComponentResult] = field(default_factory=list)
    components_skipped: list[ComponentResult] = field(default_factory=list)
    components_degraded: list[ComponentResult] = field(default_factory=list)

    # Files
    files_written: list[FileResult] = field(default_factory=list)
    files_skipped: list[FileResult] = field(default_factory=list)

    # Diagnostics
    errors: list[Diagnostic] = field(default_factory=list)
    warnings: list[Diagnostic] = field(default_factory=list)
    info: list[Diagnostic] = field(default_factory=list)

    # Metadata
    dry_run: bool = False
    best_effort: bool = False
    output_directory: Path | None = None

    def add_component(
        self,
        kind: str,
        name: str,
        status: MappingStatus,
        target_path: Path | None = None,
        notes: str | None = None,
        lost_features: list[str] | None = None,
    ) -> None:
        """Add a component result."""
        result = ComponentResult(
            kind=kind,
            name=name,
            status=status,
            target_path=target_path,
            notes=notes,
            lost_features=lost_features or [],
        )

        if status == MappingStatus.UNSUPPORTED:
            self.components_skipped.append(result)
        elif status in (MappingStatus.FALLBACK, MappingStatus.EMULATE):
            self.components_degraded.append(result)
        else:
            self.components_converted.append(result)

    def add_file(
        self,
        path: Path,
        action: str,
        size_bytes: int,
        reason: str | None = None,
    ) -> None:
        """Add a file result."""
        result = FileResult(path=path, action=action, size_bytes=size_bytes, reason=reason)

        if action == "skip":
            self.files_skipped.append(result)
        else:
            self.files_written.append(result)

    def add_diagnostic(self, diagnostic: Diagnostic) -> None:
        """Add a diagnostic message."""
        if diagnostic.severity == Severity.ERROR:
            self.errors.append(diagnostic)
        elif diagnostic.severity == Severity.WARN:
            self.warnings.append(diagnostic)
        else:
            self.info.append(diagnostic)

    @property
    def success(self) -> bool:
        """Check if conversion was successful (no errors)."""
        return len(self.errors) == 0

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    @property
    def total_components(self) -> int:
        """Total number of components processed."""
        return (
            len(self.components_converted)
            + len(self.components_skipped)
            + len(self.components_degraded)
        )

    @property
    def total_files(self) -> int:
        """Total number of files processed."""
        return len(self.files_written) + len(self.files_skipped)

    def summary(self) -> str:
        """Generate one-line summary."""
        parts = [
            f"{self.source_plugin.name} → {self.target_tool.value}:",
            f"{len(self.components_converted)} converted",
        ]

        if self.components_degraded:
            parts.append(f"{len(self.components_degraded)} degraded")

        if self.components_skipped:
            parts.append(f"{len(self.components_skipped)} skipped")

        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        elif self.warnings:
            parts.append(f"{len(self.warnings)} warnings")

        if self.dry_run:
            parts.insert(1, "[DRY RUN]")

        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_plugin": {
                "plugin_id": self.source_plugin.plugin_id,
                "name": self.source_plugin.name,
                "version": self.source_plugin.version,
                "description": self.source_plugin.description,
            },
            "target_tool": self.target_tool.value,
            "timestamp": self.timestamp.isoformat(),
            "dry_run": self.dry_run,
            "best_effort": self.best_effort,
            "output_directory": str(self.output_directory) if self.output_directory else None,
            "summary": {
                "success": self.success,
                "components_converted": len(self.components_converted),
                "components_degraded": len(self.components_degraded),
                "components_skipped": len(self.components_skipped),
                "files_written": len(self.files_written),
                "files_skipped": len(self.files_skipped),
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
            "components": {
                "converted": [c.to_dict() for c in self.components_converted],
                "degraded": [c.to_dict() for c in self.components_degraded],
                "skipped": [c.to_dict() for c in self.components_skipped],
            },
            "files": {
                "written": [f.to_dict() for f in self.files_written],
                "skipped": [f.to_dict() for f in self.files_skipped],
            },
            "diagnostics": {
                "errors": [
                    {"severity": d.severity.value, "message": d.message, "ref": d.component_ref}
                    for d in self.errors
                ],
                "warnings": [
                    {"severity": d.severity.value, "message": d.message, "ref": d.component_ref}
                    for d in self.warnings
                ],
                "info": [
                    {"severity": d.severity.value, "message": d.message, "ref": d.component_ref}
                    for d in self.info
                ],
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Generate human-readable Markdown report."""
        lines = [
            "# Conversion Report",
            "",
            f"**Source**: {self.source_plugin.name} (v{self.source_plugin.version or 'unknown'})",
            f"**Target**: {self.target_tool.value}",
            f"**Date**: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        if self.dry_run:
            lines.extend(["⚠️ **DRY RUN** - No files were written", ""])

        # Summary
        lines.extend(
            [
                "## Summary",
                "",
                "| Metric | Count |",
                "|--------|-------|",
                f"| Components converted | {len(self.components_converted)} |",
                f"| Components degraded | {len(self.components_degraded)} |",
                f"| Components skipped | {len(self.components_skipped)} |",
                f"| Files written | {len(self.files_written)} |",
                f"| Errors | {len(self.errors)} |",
                f"| Warnings | {len(self.warnings)} |",
                "",
            ]
        )

        # Errors
        if self.errors:
            lines.extend(
                [
                    "## ❌ Errors",
                    "",
                ]
            )
            for e in self.errors:
                ref = f" ({e.component_ref})" if e.component_ref else ""
                lines.append(f"- {e.message}{ref}")
            lines.append("")

        # Warnings
        if self.warnings:
            lines.extend(
                [
                    "## ⚠️ Warnings",
                    "",
                ]
            )
            for w in self.warnings:
                ref = f" ({w.component_ref})" if w.component_ref else ""
                lines.append(f"- {w.message}{ref}")
            lines.append("")

        # Components converted
        if self.components_converted:
            lines.extend(
                [
                    "## ✅ Components Converted",
                    "",
                    "| Component | Type | Status | Path |",
                    "|-----------|------|--------|------|",
                ]
            )
            for c in self.components_converted:
                path = str(c.target_path) if c.target_path else "-"
                lines.append(f"| {c.name} | {c.kind} | {c.status.value} | `{path}` |")
            lines.append("")

        # Components degraded
        if self.components_degraded:
            lines.extend(
                [
                    "## ⚡ Components Degraded",
                    "",
                    "These components were converted but lost some functionality:",
                    "",
                ]
            )
            for c in self.components_degraded:
                lines.append(f"- **{c.name}** ({c.kind}): {c.notes or 'Functionality reduced'}")
                if c.lost_features:
                    for feat in c.lost_features:
                        lines.append(f"  - Lost: {feat}")
            lines.append("")

        # Components skipped
        if self.components_skipped:
            lines.extend(
                [
                    "## ⏭️ Components Skipped",
                    "",
                    "These components could not be converted:",
                    "",
                ]
            )
            for c in self.components_skipped:
                lines.append(f"- **{c.name}** ({c.kind}): {c.notes or 'Not supported'}")
            lines.append("")

        # Files
        if self.files_written:
            lines.extend(
                [
                    "## 📁 Files Written",
                    "",
                ]
            )
            total_size = sum(f.size_bytes for f in self.files_written)
            lines.append(f"Total: {len(self.files_written)} files, {total_size:,} bytes")
            lines.append("")
            for f in self.files_written[:20]:  # Limit to first 20
                lines.append(f"- `{f.path}` ({f.size_bytes:,} bytes)")
            if len(self.files_written) > 20:
                lines.append(f"- ... and {len(self.files_written) - 20} more")
            lines.append("")

        return "\n".join(lines)

    def write_to_file(self, path: Path, format: str = "json") -> None:
        """Write report to file."""
        if format == "json":
            path.write_text(self.to_json())
        elif format == "md" or format == "markdown":
            path.write_text(self.to_markdown())
        else:
            raise ValueError(f"Unknown format: {format}")
