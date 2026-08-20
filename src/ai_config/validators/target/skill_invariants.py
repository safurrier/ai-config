"""Deterministic invariants shared by generated target skill validators."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generated_skill_invariant_errors(skill_dir: Path, metadata: dict[str, Any]) -> list[str]:
    """Return failures for leaked build metadata or Claude-root dependencies."""
    errors: list[str] = []
    if "x-ai-config-includes" in metadata:
        errors.append("Generated SKILL.md retains x-ai-config-includes build metadata")
    for path in sorted(skill_dir.rglob("*")):
        if path.is_symlink():
            errors.append(f"Generated skill contains a symlink: {path.relative_to(skill_dir)}")
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "${CLAUDE_PLUGIN_ROOT}" in content:
            errors.append(
                f"Generated skill retains ${{CLAUDE_PLUGIN_ROOT}} in {path.relative_to(skill_dir)}"
            )
    return errors
