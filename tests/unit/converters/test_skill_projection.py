"""Direct contracts for canonical include IR and target-neutral skill projection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_config.converters.ir import Skill, SkillInclude, TextFile
from ai_config.converters.skill_projection import project_skill


@pytest.mark.parametrize(
    "source",
    ["../outside", "/absolute", "./shared/data", "shared//data", "bad\0name"],
)
def test_direct_skill_include_construction_rejects_noncanonical_source(source: str) -> None:
    with pytest.raises(ValidationError):
        SkillInclude(source_relative_path=source, content=b"payload")


def test_projected_path_is_derived_from_safe_source() -> None:
    include = SkillInclude(source_relative_path="shared/data.txt", content=b"payload")
    assert include.projected_path == "_shared/shared/data.txt"
    with pytest.raises(ValidationError):
        SkillInclude(  # type: ignore[call-arg]
            source_relative_path="shared/data.txt",
            projected_path="elsewhere/data.txt",
            content=b"payload",
        )


def test_projection_rejects_collision_and_unresolved_plugin_root() -> None:
    skill = Skill(
        name="example",
        description="example",
        files=[
            TextFile(relpath="_shared/shared/data.txt", content="collision"),
            TextFile(relpath="notes.md", content="${CLAUDE_PLUGIN_ROOT}/undeclared"),
        ],
        includes=(SkillInclude(source_relative_path="shared/data.txt", content=b"payload"),),
    )
    projection = project_skill(skill, "body")
    assert any("collides" in error for error in projection.errors)
    assert any("reference remains" in error for error in projection.errors)
