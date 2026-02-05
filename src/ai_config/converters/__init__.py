"""Plugin conversion module for ai-config.

This module provides functionality to convert Claude Code plugins
to equivalent artifacts for other AI coding tools (Codex, Cursor, OpenCode).
"""

from ai_config.converters.ir import (
    Component,
    ComponentKind,
    Diagnostic,
    InstallScope,
    MappingStatus,
    PluginIdentity,
    PluginIR,
    Severity,
    TargetTool,
)

__all__ = [
    "Component",
    "ComponentKind",
    "Diagnostic",
    "InstallScope",
    "MappingStatus",
    "PluginIdentity",
    "PluginIR",
    "Severity",
    "TargetTool",
]
