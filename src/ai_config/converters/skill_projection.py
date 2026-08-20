"""Pure target-neutral projection of self-contained generated skills."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from ai_config.converters.ir import BinaryFile, Skill, TextFile

_ROOT = "${CLAUDE_PLUGIN_ROOT}"


@dataclass(frozen=True)
class ProjectedSkillFile:
    """One file relative to an emitted skill root."""

    relative_path: PurePosixPath
    content: str | bytes
    executable: bool = False


@dataclass(frozen=True)
class IncludeProjectionEvidence:
    """Per-include projection facts independent of a target output root."""

    source_relative_path: str
    projected_path: str
    duplicated_bytes: int
    direct_rewrite_count: int


@dataclass(frozen=True)
class SkillProjection:
    """Complete projected skill plus include evidence and blocking errors."""

    files: tuple[ProjectedSkillFile, ...]
    include_evidence: tuple[IncludeProjectionEvidence, ...]
    errors: tuple[str, ...] = ()


def _conflicts(left: PurePosixPath, right: PurePosixPath) -> bool:
    return left == right or left in right.parents or right in left.parents


def _rewrite_declared(markdown: str, source_path: str, projected_path: str) -> tuple[str, int]:
    token = f"{_ROOT}/{source_path}"
    # Do not rewrite a declaration that is merely a prefix of a longer path.
    pattern = re.compile(re.escape(token) + r"(?![A-Za-z0-9._/~-])")
    return pattern.subn(projected_path, markdown)


def project_skill(skill: Skill, generated_skill_markdown: str) -> SkillProjection:
    """Materialize declared includes and rewrite only instruction Markdown.

    Rewrites are always relative to the emitted skill root, including references
    found in nested Markdown files. Included payload bytes are never decoded or
    rewritten.
    """
    source_files: list[ProjectedSkillFile] = [
        ProjectedSkillFile(PurePosixPath("SKILL.md"), generated_skill_markdown)
    ]
    for item in skill.files:
        if item.relpath == "SKILL.md":
            continue
        path = PurePosixPath(item.relpath)
        if isinstance(item, TextFile):
            source_files.append(ProjectedSkillFile(path, item.content, item.executable))
        elif isinstance(item, BinaryFile):
            source_files.append(
                ProjectedSkillFile(path, base64.b64decode(item.content_b64), item.executable)
            )

    evidence_counts = {item.source_relative_path: 0 for item in skill.includes}
    rewritten_files: list[ProjectedSkillFile] = []
    for item in source_files:
        content = item.content
        if isinstance(content, str) and item.relative_path.suffix.lower() in {".md", ".markdown"}:
            for include in skill.includes:
                content, count = _rewrite_declared(
                    content, include.source_relative_path, include.projected_path
                )
                evidence_counts[include.source_relative_path] += count
        rewritten_files.append(ProjectedSkillFile(item.relative_path, content, item.executable))

    errors: list[str] = []
    for item in rewritten_files:
        if isinstance(item.content, str) and _ROOT in item.content:
            errors.append(
                f"undeclared or non-instruction {_ROOT} reference remains in {item.relative_path}"
            )

    occupied = [item.relative_path for item in rewritten_files]
    for include in skill.includes:
        projected = PurePosixPath(include.projected_path)
        if _ROOT.encode("utf-8") in include.content:
            errors.append(
                f"included file {include.source_relative_path} retains {_ROOT}; "
                "included files must self-locate"
            )
        conflict = next((path for path in occupied if _conflicts(path, projected)), None)
        if conflict is not None:
            errors.append(f"included path {projected} collides with skill file {conflict}")
            continue
        occupied.append(projected)
        rewritten_files.append(ProjectedSkillFile(projected, include.content, include.executable))

    evidence = tuple(
        IncludeProjectionEvidence(
            source_relative_path=include.source_relative_path,
            projected_path=include.projected_path,
            duplicated_bytes=len(include.content),
            direct_rewrite_count=evidence_counts[include.source_relative_path],
        )
        for include in skill.includes
    )
    return SkillProjection(tuple(rewritten_files), evidence, tuple(errors))
