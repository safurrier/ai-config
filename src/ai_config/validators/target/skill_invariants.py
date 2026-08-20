"""Deterministic invariants shared by generated target skill validators and emitters."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any


def generated_skill_bytes_invariant_errors(
    files: Mapping[PurePosixPath, bytes], metadata: dict[str, Any]
) -> list[str]:
    """Return failures for leaked build metadata or Claude-root dependencies."""
    errors: list[str] = []
    if "x-ai-config-includes" in metadata:
        errors.append("Generated SKILL.md retains x-ai-config-includes build metadata")
    for relative, content_bytes in sorted(files.items(), key=lambda item: item[0].as_posix()):
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "${CLAUDE_PLUGIN_ROOT}" in content:
            errors.append(f"Generated skill retains ${{CLAUDE_PLUGIN_ROOT}} in {relative}")
    return errors


def generated_skill_invariant_errors(skill_dir: Path, metadata: dict[str, Any]) -> list[str]:
    """Read a generated skill tree and apply the shared byte-level invariants."""
    files: dict[PurePosixPath, bytes] = {}
    errors: list[str] = []
    for path in sorted(skill_dir.rglob("*")):
        if path.is_symlink():
            errors.append(f"Generated skill contains a symlink: {path.relative_to(skill_dir)}")
            continue
        if not path.is_file():
            continue
        try:
            files[PurePosixPath(path.relative_to(skill_dir).as_posix())] = path.read_bytes()
        except OSError as error:
            errors.append(
                f"Generated skill file is unreadable: {path.relative_to(skill_dir)}: {error}"
            )
    return errors + generated_skill_bytes_invariant_errors(files, metadata)
