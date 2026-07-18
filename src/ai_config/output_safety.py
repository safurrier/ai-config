"""Filesystem guards for writes rooted in configured conversion output directories."""

from __future__ import annotations

from pathlib import Path


def validated_output_path(output_root: Path, relative_path: Path) -> Path:
    """Return one rooted path after rejecting unsafe or symlinked descendants."""
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"Output path must stay beneath its configured root: {relative_path}")

    resolved_root = output_root.expanduser().resolve()
    candidate = resolved_root
    for component in relative_path.parts:
        if component in {"", "."}:
            continue
        candidate /= component
        if candidate.is_symlink():
            raise ValueError(
                f"Refusing output path with symlinked component beneath {resolved_root}: {candidate}"
            )
    return candidate
