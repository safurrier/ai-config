"""Tests for Emitter Protocol pattern.

These tests verify that emitters follow the Protocol pattern (structural typing)
matching the validator pattern in ai_config/validators/base.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import pytest

from ai_config.converters.emitters import (
    CodexEmitter,
    CursorEmitter,
    EmitResult,
    OpenCodeEmitter,
    get_emitter,
    skill_to_markdown,
)
from ai_config.converters.ir import (
    InstallScope,
    PluginIdentity,
    PluginIR,
    Skill,
    TargetTool,
    TextFile,
)


class TestEmitterProtocol:
    """Tests that emitters satisfy the Emitter protocol."""

    def test_codex_emitter_has_required_attributes(self) -> None:
        """CodexEmitter has target and scope attributes."""
        emitter = CodexEmitter()
        assert hasattr(emitter, "target")
        assert hasattr(emitter, "scope")
        assert emitter.target == TargetTool.CODEX
        assert emitter.scope == InstallScope.PROJECT

    def test_cursor_emitter_has_required_attributes(self) -> None:
        """CursorEmitter has target and scope attributes."""
        emitter = CursorEmitter()
        assert hasattr(emitter, "target")
        assert hasattr(emitter, "scope")
        assert emitter.target == TargetTool.CURSOR
        assert emitter.scope == InstallScope.PROJECT

    def test_opencode_emitter_has_required_attributes(self) -> None:
        """OpenCodeEmitter has target and scope attributes."""
        emitter = OpenCodeEmitter()
        assert hasattr(emitter, "target")
        assert hasattr(emitter, "scope")
        assert emitter.target == TargetTool.OPENCODE
        assert emitter.scope == InstallScope.PROJECT

    def test_emitters_have_emit_method(self) -> None:
        """All emitters have an emit method that returns EmitResult."""
        ir = PluginIR(
            identity=PluginIdentity(plugin_id="test", name="Test Plugin"),
            components=[],
        )

        for emitter_class in [CodexEmitter, CursorEmitter, OpenCodeEmitter]:
            emitter = emitter_class()
            assert hasattr(emitter, "emit")
            assert callable(emitter.emit)

            result = emitter.emit(ir)
            assert isinstance(result, EmitResult)

    def test_emitter_scope_can_be_set(self) -> None:
        """Emitter scope can be set via constructor."""
        emitter = CodexEmitter(scope=InstallScope.USER)
        assert emitter.scope == InstallScope.USER

        emitter = CursorEmitter(scope=InstallScope.USER)
        assert emitter.scope == InstallScope.USER

        emitter = OpenCodeEmitter(scope=InstallScope.USER)
        assert emitter.scope == InstallScope.USER


class TestEmitterProtocolDuckTyping:
    """Tests that emitters work with duck typing (structural subtyping)."""

    def test_custom_emitter_satisfies_protocol(self) -> None:
        """A custom class with the right shape satisfies the protocol."""
        # Define a minimal protocol inline for testing
        @runtime_checkable
        class Emitter(Protocol):
            target: TargetTool
            scope: InstallScope

            def emit(self, ir: PluginIR) -> EmitResult: ...

        # Verify built-in emitters satisfy it
        codex = CodexEmitter()
        cursor = CursorEmitter()
        opencode = OpenCodeEmitter()

        assert isinstance(codex, Emitter)
        assert isinstance(cursor, Emitter)
        assert isinstance(opencode, Emitter)

    def test_emitters_can_be_used_interchangeably(self) -> None:
        """Emitters can be used interchangeably via common interface."""
        ir = PluginIR(
            identity=PluginIdentity(plugin_id="test", name="Test Plugin"),
            components=[
                Skill(
                    name="test-skill",
                    description="A test skill",
                    files=[
                        TextFile(
                            relpath="SKILL.md",
                            content="---\nname: test-skill\ndescription: A test skill\n---\n\n# Test",
                        )
                    ],
                )
            ],
        )

        emitters = [CodexEmitter(), CursorEmitter(), OpenCodeEmitter()]
        results = []

        for emitter in emitters:
            result = emitter.emit(ir)
            results.append(result)

        # All should produce valid results
        assert len(results) == 3
        for result in results:
            assert isinstance(result, EmitResult)
            assert len(result.files) > 0


class TestSkillToMarkdownHelper:
    """Tests for the module-level skill_to_markdown helper function."""

    def test_skill_to_markdown_basic(self) -> None:
        """skill_to_markdown converts a skill to SKILL.md format."""
        skill = Skill(
            name="my-skill",
            description="A helpful skill",
            files=[
                TextFile(
                    relpath="SKILL.md",
                    content="---\nname: my-skill\ndescription: A helpful skill\n---\n\n# My Skill\n\nInstructions here.",
                )
            ],
        )

        markdown = skill_to_markdown(skill)

        assert "---" in markdown
        assert "name: my-skill" in markdown
        assert "description: A helpful skill" in markdown
        assert "# My Skill" in markdown or "Instructions here" in markdown

    def test_skill_to_markdown_strips_claude_fields_by_default(self) -> None:
        """skill_to_markdown strips Claude-specific fields by default."""
        skill = Skill(
            name="my-skill",
            description="A helpful skill",
            allowed_tools=["Read", "Write"],
            model="claude-sonnet",
            context="include",
            files=[
                TextFile(
                    relpath="SKILL.md",
                    content="---\nname: my-skill\ndescription: A helpful skill\nallowed-tools: [Read, Write]\nmodel: claude-sonnet\n---\n\n# My Skill",
                )
            ],
        )

        markdown = skill_to_markdown(skill, strip_claude_fields=True)

        # Should NOT contain Claude-specific fields
        assert "allowed-tools" not in markdown
        assert "model" not in markdown
        assert "context" not in markdown

        # Should still have basic fields
        assert "name: my-skill" in markdown
        assert "description:" in markdown

    def test_skill_to_markdown_preserves_claude_fields_when_requested(self) -> None:
        """skill_to_markdown can preserve Claude-specific fields."""
        skill = Skill(
            name="my-skill",
            description="A helpful skill",
            allowed_tools=["Read", "Write"],
            model="claude-sonnet",
            files=[
                TextFile(
                    relpath="SKILL.md",
                    content="---\nname: my-skill\n---\n\n# My Skill",
                )
            ],
        )

        markdown = skill_to_markdown(skill, strip_claude_fields=False)

        # Should contain Claude-specific fields
        assert "allowed-tools" in markdown
        assert "model" in markdown

    def test_skill_to_markdown_handles_empty_body(self) -> None:
        """skill_to_markdown handles skills with no body content."""
        skill = Skill(
            name="minimal-skill",
            description="Minimal",
            files=[
                TextFile(
                    relpath="SKILL.md",
                    content="---\nname: minimal-skill\ndescription: Minimal\n---\n",
                )
            ],
        )

        markdown = skill_to_markdown(skill)

        assert "name: minimal-skill" in markdown
        # Should not crash with empty body


class TestGetEmitterFactory:
    """Tests for the get_emitter factory function."""

    def test_get_emitter_returns_correct_type(self) -> None:
        """get_emitter returns the correct emitter type."""
        codex = get_emitter(TargetTool.CODEX)
        assert isinstance(codex, CodexEmitter)

        cursor = get_emitter(TargetTool.CURSOR)
        assert isinstance(cursor, CursorEmitter)

        opencode = get_emitter(TargetTool.OPENCODE)
        assert isinstance(opencode, OpenCodeEmitter)

    def test_get_emitter_passes_scope(self) -> None:
        """get_emitter passes scope to the emitter."""
        emitter = get_emitter(TargetTool.CODEX, scope=InstallScope.USER)
        assert emitter.scope == InstallScope.USER

    def test_get_emitter_invalid_target_raises(self) -> None:
        """get_emitter raises ValueError for invalid target."""
        with pytest.raises(ValueError, match="No emitter for target"):
            get_emitter(TargetTool.CLAUDE)  # Claude is source, not target


class TestEmitResultInterface:
    """Tests for EmitResult interface consistency."""

    def test_emit_result_has_expected_attributes(self) -> None:
        """EmitResult has files, mappings, and diagnostics."""
        result = EmitResult(target=TargetTool.CODEX)

        assert hasattr(result, "files")
        assert hasattr(result, "mappings")
        assert hasattr(result, "diagnostics")
        assert hasattr(result, "target")

    def test_emit_result_helper_methods(self) -> None:
        """EmitResult has helper methods for adding content."""
        result = EmitResult(target=TargetTool.CODEX)

        assert hasattr(result, "add_file")
        assert hasattr(result, "add_mapping")
        assert hasattr(result, "add_diagnostic")
        assert hasattr(result, "write_to")
        assert hasattr(result, "preview")
        assert hasattr(result, "has_errors")

    def test_emit_result_write_to_dry_run(self, tmp_path: Path) -> None:
        """EmitResult.write_to with dry_run doesn't create files."""
        result = EmitResult(target=TargetTool.CODEX)
        result.add_file("test.md", "# Test content")

        written = result.write_to(tmp_path, dry_run=True)

        assert len(written) == 1
        assert not (tmp_path / "test.md").exists()

    def test_emit_result_write_to_creates_files(self, tmp_path: Path) -> None:
        """EmitResult.write_to creates files when not dry_run."""
        result = EmitResult(target=TargetTool.CODEX)
        result.add_file("test.md", "# Test content")

        written = result.write_to(tmp_path, dry_run=False)

        assert len(written) == 1
        assert (tmp_path / "test.md").exists()
        assert (tmp_path / "test.md").read_text() == "# Test content"
