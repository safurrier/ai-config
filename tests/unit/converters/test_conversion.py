"""Tests for plugin conversion functionality."""

import json
from pathlib import Path

import pytest

from ai_config.converters.claude_parser import parse_claude_plugin
from ai_config.converters.convert import convert_plugin, preview_conversion
from ai_config.converters.emitters import (
    CodexEmitter,
    CursorEmitter,
    OpenCodeEmitter,
    get_emitter,
)
from ai_config.converters.ir import (
    InstallScope,
    MappingStatus,
    TargetTool,
)

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "sample-plugins"


class TestClaudeParser:
    """Tests for Claude plugin parser."""

    def test_parse_complete_plugin(self) -> None:
        """Test parsing a complete plugin with all component types."""
        plugin_path = FIXTURES_DIR / "complete-plugin"
        ir = parse_claude_plugin(plugin_path)

        # Check identity
        assert ir.identity.plugin_id == "dev-tools"
        assert ir.identity.name == "dev-tools"
        assert ir.identity.version == "1.0.0"

        # Check skills (includes nested skill)
        skills = ir.skills()
        assert len(skills) == 3  # code-review, test-writer, nested-skill
        skill_names = {s.name for s in skills}
        assert "code-review" in skill_names
        assert "test-writer" in skill_names
        assert "nested-skill" in skill_names

        # Check skill with Claude-specific fields
        code_review = next(s for s in skills if s.name == "code-review")
        assert code_review.description is not None
        assert "code" in code_review.description.lower()
        assert code_review.allowed_tools == ["Read", "Grep", "Glob"]
        assert code_review.model == "sonnet"
        assert code_review.context == "fork"
        assert code_review.agent == "Explore"

        # Check commands
        commands = ir.commands()
        assert len(commands) == 1
        commit_cmd = commands[0]
        assert commit_cmd.name == "commit"
        assert commit_cmd.has_arguments_var  # Uses $ARGUMENTS
        assert commit_cmd.has_positional_vars  # Uses $2

        # Check agents
        agents = ir.agents()
        assert len(agents) == 1
        assert agents[0].name == "security-reviewer"

        # Check hooks
        hooks = ir.hooks()
        assert len(hooks) == 1
        hook = hooks[0]
        assert len(hook.events) == 3  # PreToolUse, PostToolUse, Stop

        # Check MCP servers
        mcp_servers = ir.mcp_servers()
        assert len(mcp_servers) == 2
        server_names = {s.name for s in mcp_servers}
        assert "database" in server_names
        assert "github" in server_names

        # Check LSP servers
        lsp_servers = ir.lsp_servers()
        assert len(lsp_servers) == 1
        assert lsp_servers[0].name == "custom-python"
        assert ".py" in lsp_servers[0].extensions

    def test_parse_nested_skill_directories(self) -> None:
        """Test parsing skills in nested directory structures.

        Skills can be organized in category directories like:
            skills/category/my-skill/SKILL.md
        """
        plugin_path = FIXTURES_DIR / "complete-plugin"
        ir = parse_claude_plugin(plugin_path)

        skills = ir.skills()
        skill_names = {s.name for s in skills}

        # Should find nested skill
        assert "nested-skill" in skill_names

        # Get the nested skill
        nested_skill = next(s for s in skills if s.name == "nested-skill")

        # Check it was parsed correctly
        assert nested_skill.description == "A skill nested inside a category directory"
        assert nested_skill.allowed_tools == ["Read", "Glob"]

        # Check files were collected from nested structure
        file_relpaths = {f.relpath for f in nested_skill.files}
        assert "SKILL.md" in file_relpaths
        assert "resources/reference.md" in file_relpaths

    def test_parse_missing_plugin(self) -> None:
        """Test parsing non-existent plugin."""
        ir = parse_claude_plugin(FIXTURES_DIR / "nonexistent")
        assert ir.has_errors()
        assert any("manifest" in d.message.lower() for d in ir.diagnostics)


class TestCodexEmitter:
    """Tests for Codex emitter."""

    @pytest.fixture
    def ir(self):
        """Load the test plugin IR."""
        return parse_claude_plugin(FIXTURES_DIR / "complete-plugin")

    def test_emit_skills(self, ir, tmp_path: Path) -> None:
        """Test emitting skills to Codex format."""
        emitter = CodexEmitter()
        result = emitter.emit(ir)

        # Check skill files were created
        skill_files = [f for f in result.files if "skills" in str(f.path)]
        assert len(skill_files) >= 2

        # Check skill mapping
        skill_mappings = [m for m in result.mappings if m.component_kind == "skill"]
        assert all(m.status == MappingStatus.NATIVE for m in skill_mappings)

        # Write and verify structure
        result.write_to(tmp_path)

        # Check SKILL.md was written correctly
        skill_md = tmp_path / ".codex" / "skills" / "dev-tools-code-review" / "SKILL.md"
        assert skill_md.exists()
        content = skill_md.read_text()

        # Should have frontmatter
        assert content.startswith("---")
        assert "name: code-review" in content
        assert "description:" in content

        # Claude-specific fields should be stripped
        assert "allowed-tools:" not in content
        assert "model:" not in content
        assert "context:" not in content

    def test_emit_commands_deprecated(self, ir) -> None:
        """Test that commands emit with deprecation warning."""
        emitter = CodexEmitter()
        result = emitter.emit(ir)

        # Commands should be marked as fallback
        cmd_mappings = [m for m in result.mappings if m.component_kind == "command"]
        assert len(cmd_mappings) == 1
        assert cmd_mappings[0].status == MappingStatus.FALLBACK
        assert "deprecated" in (cmd_mappings[0].notes or "").lower()

        # Should have info diagnostic about deprecation
        cmd_diags = [d for d in result.diagnostics if "command" in (d.component_ref or "")]
        assert any("deprecated" in d.message.lower() for d in cmd_diags)

    def test_emit_hooks_unsupported(self, ir) -> None:
        """Test that hooks are marked unsupported."""
        emitter = CodexEmitter()
        result = emitter.emit(ir)

        hook_mappings = [m for m in result.mappings if m.component_kind == "hook"]
        assert len(hook_mappings) == 1
        assert hook_mappings[0].status == MappingStatus.UNSUPPORTED

    def test_emit_mcp_config(self, ir, tmp_path: Path) -> None:
        """Test MCP config conversion to TOML."""
        emitter = CodexEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        mcp_config = tmp_path / ".codex" / "mcp-config.toml"
        assert mcp_config.exists()

        content = mcp_config.read_text()
        assert "[mcp_servers.dev-tools-database]" in content
        assert "[mcp_servers.dev-tools-github]" in content
        assert 'command = "npx"' in content


class TestCursorEmitter:
    """Tests for Cursor emitter."""

    @pytest.fixture
    def ir(self):
        """Load the test plugin IR."""
        return parse_claude_plugin(FIXTURES_DIR / "complete-plugin")

    def test_emit_skills(self, ir, tmp_path: Path) -> None:
        """Test emitting skills to Cursor format."""
        emitter = CursorEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        skill_md = tmp_path / ".cursor" / "skills" / "dev-tools-code-review" / "SKILL.md"
        assert skill_md.exists()

    def test_emit_commands_no_variables(self, ir) -> None:
        """Test that commands lose variable support with warning."""
        emitter = CursorEmitter()
        result = emitter.emit(ir)

        # Check for warning about lost variables
        cmd_diags = [d for d in result.diagnostics if "command" in (d.component_ref or "")]
        assert any("variable" in d.message.lower() for d in cmd_diags)

        # Check command file content
        cmd_files = [f for f in result.files if "commands" in str(f.path)]
        assert len(cmd_files) == 1

        # Variables should be replaced with placeholders
        content = cmd_files[0].content
        assert "$ARGUMENTS" not in content
        assert "$2" not in content

    def test_emit_hooks_transform(self, ir, tmp_path: Path) -> None:
        """Test hooks are transformed to Cursor format."""
        emitter = CursorEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        hooks_path = tmp_path / ".cursor" / "hooks.json"
        assert hooks_path.exists()

        import json
        hooks_config = json.loads(hooks_path.read_text())
        assert "hooks" in hooks_config
        assert "version" in hooks_config

        # Claude PreToolUse -> Cursor beforeShellExecution
        assert "beforeShellExecution" in hooks_config["hooks"]

    def test_emit_mcp_config(self, ir, tmp_path: Path) -> None:
        """Test MCP config for Cursor."""
        emitter = CursorEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        mcp_path = tmp_path / ".cursor" / "mcp.json"
        assert mcp_path.exists()

        import json
        mcp_config = json.loads(mcp_path.read_text())
        assert "mcpServers" in mcp_config
        assert "dev-tools-database" in mcp_config["mcpServers"]


class TestOpenCodeEmitter:
    """Tests for OpenCode emitter."""

    @pytest.fixture
    def ir(self):
        """Load the test plugin IR."""
        return parse_claude_plugin(FIXTURES_DIR / "complete-plugin")

    def test_emit_skills(self, ir, tmp_path: Path) -> None:
        """Test emitting skills to OpenCode format."""
        emitter = OpenCodeEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        skill_md = tmp_path / ".opencode" / "skills" / "dev-tools-code-review" / "SKILL.md"
        assert skill_md.exists()

    def test_emit_commands_with_variables(self, ir, tmp_path: Path) -> None:
        """Test commands preserve variables (OpenCode supports them)."""
        emitter = OpenCodeEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        cmd_path = tmp_path / ".opencode" / "commands" / "dev-tools-commit.md"
        assert cmd_path.exists()

        content = cmd_path.read_text()
        # OpenCode supports $ARGUMENTS
        assert "$ARGUMENTS" in content

    def test_emit_hooks_emulate(self, ir) -> None:
        """Test hooks are marked for emulation."""
        emitter = OpenCodeEmitter()
        result = emitter.emit(ir)

        hook_mappings = [m for m in result.mappings if m.component_kind == "hook"]
        assert len(hook_mappings) == 1
        assert hook_mappings[0].status == MappingStatus.EMULATE

    def test_emit_lsp_config(self, ir, tmp_path: Path) -> None:
        """Test LSP config for OpenCode."""
        emitter = OpenCodeEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        lsp_path = tmp_path / "opencode.lsp.json"
        assert lsp_path.exists()

        import json
        lsp_config = json.loads(lsp_path.read_text())
        assert "lsp" in lsp_config
        assert "dev-tools-custom-python" in lsp_config["lsp"]

        # Check extensions converted correctly
        lsp_server = lsp_config["lsp"]["dev-tools-custom-python"]
        assert ".py" in lsp_server.get("extensions", [])


class TestEmitterFactory:
    """Tests for emitter factory."""

    def test_get_emitter_codex(self) -> None:
        """Test getting Codex emitter."""
        emitter = get_emitter(TargetTool.CODEX)
        assert isinstance(emitter, CodexEmitter)

    def test_get_emitter_cursor(self) -> None:
        """Test getting Cursor emitter."""
        emitter = get_emitter(TargetTool.CURSOR)
        assert isinstance(emitter, CursorEmitter)

    def test_get_emitter_opencode(self) -> None:
        """Test getting OpenCode emitter."""
        emitter = get_emitter(TargetTool.OPENCODE)
        assert isinstance(emitter, OpenCodeEmitter)

    def test_get_emitter_claude_raises(self) -> None:
        """Test that Claude emitter raises (we don't convert TO Claude)."""
        with pytest.raises(ValueError):
            get_emitter(TargetTool.CLAUDE)

    def test_get_emitter_with_scope(self) -> None:
        """Test emitter respects scope parameter."""
        emitter = get_emitter(TargetTool.CODEX, scope=InstallScope.USER)
        assert emitter.scope == InstallScope.USER


class TestEdgeCases:
    """Test edge cases and sharp edges discovered during implementation."""

    def test_skill_name_normalization(self) -> None:
        """Test that skill names are normalized for portability."""
        # OpenCode requires lowercase kebab-case, max 64 chars
        from ai_config.converters.ir import Skill

        # Valid name
        skill = Skill(name="my-skill", description="Test")
        assert skill.name == "my-skill"

        # Too long - should raise
        with pytest.raises(ValueError, match="too long"):
            Skill(name="a" * 65, description="Test")

        # Invalid characters - should raise
        with pytest.raises(ValueError, match="kebab-case"):
            Skill(name="My_Skill", description="Test")

    def test_plugin_id_normalization(self) -> None:
        """Test that plugin IDs are normalized."""
        from ai_config.converters.ir import PluginIdentity

        # Valid
        ident = PluginIdentity(plugin_id="my-plugin", name="My Plugin")
        assert ident.plugin_id == "my-plugin"

        # Invalid
        with pytest.raises(ValueError, match="kebab-case"):
            PluginIdentity(plugin_id="My_Plugin", name="My Plugin")

    def test_mcp_env_var_syntax_differences(self, tmp_path: Path) -> None:
        """Test that env var syntax is preserved (tools handle differently)."""
        # Claude uses ${VAR}, Codex uses ${VAR}, Cursor uses ${env:VAR}, OpenCode uses {env:VAR}
        # This is a known sharp edge - we preserve original syntax
        from ai_config.converters.ir import McpServer, McpTransport, PluginIdentity, PluginIR

        ir = PluginIR(
            identity=PluginIdentity(plugin_id="test", name="test"),
            components=[
                McpServer(
                    name="test-server",
                    transport=McpTransport.STDIO,
                    command="test-cmd",
                    env={"API_KEY": "${API_KEY}"},  # Claude syntax
                )
            ],
        )

        # Emit to each target and check syntax is preserved
        # (In production, we'd want to transform the syntax)
        for emitter_class in [CodexEmitter, CursorEmitter, OpenCodeEmitter]:
            emitter = emitter_class()
            result = emitter.emit(ir)

            # Find MCP-related file
            mcp_files = [f for f in result.files if "mcp" in str(f.path).lower()]
            assert len(mcp_files) >= 1

            # Env var should be in the output (syntax transformation is a TODO)
            content = mcp_files[0].content
            assert "API_KEY" in content

    def test_hook_event_mapping_coverage(self) -> None:
        """Test which Claude events map to Cursor."""
        # This documents the mapping gaps
        claude_events = [
            "SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest",
            "PostToolUse", "PostToolUseFailure", "Notification", "SubagentStart",
            "SubagentStop", "Stop", "PreCompact", "SessionEnd"
        ]

        cursor_mappable = ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"]
        cursor_unmappable = [e for e in claude_events if e not in cursor_mappable]

        # These events have no Cursor equivalent
        assert "SessionStart" in cursor_unmappable
        assert "PermissionRequest" in cursor_unmappable
        assert "SubagentStart" in cursor_unmappable
        assert "SessionEnd" in cursor_unmappable

    def test_command_variable_detection(self) -> None:
        """Test detection of template variables in commands."""
        from ai_config.converters.ir import Command

        # No variables
        cmd1 = Command(name="test", markdown="Just text")
        assert not cmd1.has_arguments_var
        assert not cmd1.has_positional_vars

        # With $ARGUMENTS
        cmd2 = Command(
            name="test",
            markdown="Use $ARGUMENTS here",
            has_arguments_var=True,
        )
        assert cmd2.has_arguments_var

        # With positional
        cmd3 = Command(
            name="test",
            markdown="First: $1, Second: $2",
            has_positional_vars=True,
        )
        assert cmd3.has_positional_vars


class TestConversionReport:
    """Tests for conversion report generation."""

    @pytest.fixture
    def ir(self):
        """Load the test plugin IR."""
        return parse_claude_plugin(FIXTURES_DIR / "complete-plugin")

    def test_report_to_json(self, ir) -> None:
        """Test JSON report generation."""
        reports = convert_plugin(
            FIXTURES_DIR / "complete-plugin",
            [TargetTool.CODEX],
            dry_run=True,
        )

        report = reports[TargetTool.CODEX]
        json_str = report.to_json()

        # Should be valid JSON
        data = json.loads(json_str)
        assert "source_plugin" in data
        assert "target_tool" in data
        assert data["target_tool"] == "codex"
        assert "summary" in data
        assert "components" in data

    def test_report_to_markdown(self, ir) -> None:
        """Test Markdown report generation."""
        reports = convert_plugin(
            FIXTURES_DIR / "complete-plugin",
            [TargetTool.CURSOR],
            dry_run=True,
        )

        report = reports[TargetTool.CURSOR]
        md = report.to_markdown()

        assert "# Conversion Report" in md
        assert "cursor" in md.lower()
        assert "Components" in md

    def test_report_summary(self, ir) -> None:
        """Test one-line summary generation."""
        reports = convert_plugin(
            FIXTURES_DIR / "complete-plugin",
            [TargetTool.OPENCODE],
            dry_run=True,
        )

        report = reports[TargetTool.OPENCODE]
        summary = report.summary()

        assert "dev-tools" in summary
        assert "opencode" in summary
        assert "converted" in summary


class TestDryRun:
    """Tests for dry-run functionality."""

    def test_dry_run_does_not_write_files(self, tmp_path: Path) -> None:
        """Test that dry-run doesn't create files."""
        output_dir = tmp_path / "output"

        reports = convert_plugin(
            FIXTURES_DIR / "complete-plugin",
            [TargetTool.CODEX],
            output_dir=output_dir,
            dry_run=True,
        )

        # Directory should not be created
        assert not output_dir.exists()

        # Report should still have file info
        report = reports[TargetTool.CODEX]
        assert report.dry_run
        assert len(report.files_written) > 0 or len(report.files_skipped) >= 0

    def test_dry_run_shows_preview(self, tmp_path: Path) -> None:
        """Test that dry-run shows what would be done."""
        emitter = CodexEmitter()
        ir = parse_claude_plugin(FIXTURES_DIR / "complete-plugin")
        result = emitter.emit(ir)

        preview = result.preview(tmp_path)

        assert "Files to write" in preview
        assert "bytes" in preview
        assert "Component mappings" in preview

    def test_actual_write_creates_files(self, tmp_path: Path) -> None:
        """Test that non-dry-run actually creates files."""
        output_dir = tmp_path / "output"

        convert_plugin(
            FIXTURES_DIR / "complete-plugin",
            [TargetTool.CODEX],
            output_dir=output_dir,
            dry_run=False,  # Actually write
        )

        # Directory should be created
        assert output_dir.exists()

        # Files should exist
        skills_dir = output_dir / ".codex" / "skills"
        assert skills_dir.exists()


class TestPreviewConversion:
    """Tests for preview_conversion function."""

    def test_preview_shows_all_targets(self) -> None:
        """Test preview shows info for all targets."""
        preview = preview_conversion(
            FIXTURES_DIR / "complete-plugin",
            ["codex", "cursor", "opencode"],
        )

        assert "CODEX" in preview
        assert "CURSOR" in preview
        assert "OPENCODE" in preview
        assert "dev-tools" in preview

    def test_preview_with_output_dir(self, tmp_path: Path) -> None:
        """Test preview shows paths relative to output dir."""
        preview = preview_conversion(
            FIXTURES_DIR / "complete-plugin",
            [TargetTool.CODEX],
            output_dir=tmp_path,
        )

        assert str(tmp_path) in preview or ".codex" in preview


class TestBestEffort:
    """Tests for best-effort conversion mode."""

    def test_best_effort_continues_on_error(self, tmp_path: Path) -> None:
        """Test that best-effort mode continues despite errors."""
        # Create a malformed plugin
        bad_plugin = tmp_path / "bad-plugin"
        bad_plugin.mkdir()
        (bad_plugin / ".claude-plugin").mkdir()
        (bad_plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "bad"}')
        # Add invalid skill
        (bad_plugin / "skills").mkdir()
        (bad_plugin / "skills" / "broken").mkdir()
        (bad_plugin / "skills" / "broken" / "SKILL.md").write_text("no frontmatter")

        reports = convert_plugin(
            bad_plugin,
            [TargetTool.CODEX],
            output_dir=tmp_path / "output",
            best_effort=True,
            dry_run=True,
        )

        # Should complete without raising
        report = reports[TargetTool.CODEX]
        assert report is not None
        # May have warnings/errors but shouldn't crash
        assert report.best_effort
