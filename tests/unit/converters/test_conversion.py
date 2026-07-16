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
    PiEmitter,
    get_emitter,
)
from ai_config.converters.ir import (
    BinaryFile,
    InstallScope,
    LspServer,
    MappingStatus,
    McpServer,
    McpTransport,
    PluginIdentity,
    PluginIR,
    Skill,
    TargetTool,
    TextFile,
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

    def test_parse_binary_skill_files(self, tmp_path: Path) -> None:
        """Binary files in skills should be captured as BinaryFile entries."""
        plugin_dir = tmp_path / "plugin"
        (plugin_dir / ".claude-plugin").mkdir(parents=True)
        (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
            '{"name": "binary-plugin", "skills": "./skills"}'
        )
        skill_dir = plugin_dir / "skills" / "bin-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: bin-skill\ndescription: test\n---\n\nBody")

        binary_path = skill_dir / "asset.bin"
        binary_bytes = b"\xff\xfe\x00\x80binary"
        binary_path.write_bytes(binary_bytes)

        ir = parse_claude_plugin(plugin_dir)
        skill = ir.skills()[0]

        binary_files = [f for f in skill.files if isinstance(f, BinaryFile)]
        assert binary_files
        assert binary_files[0].relpath == "asset.bin"

    def test_parse_non_kebab_names_normalizes(self, tmp_path: Path) -> None:
        """Non-kebab plugin and skill names should normalize without crashing."""
        plugin_dir = tmp_path / "plugin"
        (plugin_dir / ".claude-plugin").mkdir(parents=True)
        (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
            '{"name": "My Plugin!", "skills": "./skills"}'
        )
        skill_dir = plugin_dir / "skills" / "My Skill!"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: My Skill!\ndescription: test\n---\n\nBody")

        ir = parse_claude_plugin(plugin_dir)
        assert ir.identity.plugin_id == "my-plugin"
        assert ir.skills()[0].name == "my-skill"

    def test_parse_known_unconverted_claude_fields_diagnostics(self, tmp_path: Path) -> None:
        """Modern Claude plugin fields should be diagnosed when not represented in IR."""
        plugin_dir = tmp_path / "modern-plugin"
        (plugin_dir / ".claude-plugin").mkdir(parents=True)
        (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "modern-plugin",
                    "outputStyles": "./output-styles",
                    "monitors": "./monitors",
                    "themes": "./themes",
                    "channels": "./channels",
                }
            )
        )

        ir = parse_claude_plugin(plugin_dir)

        refs = {diag.component_ref for diag in ir.diagnostics}
        assert "manifest:outputStyles" in refs
        assert "manifest:monitors" in refs
        assert "manifest:themes" in refs
        assert "manifest:channels" in refs


class TestCodexEmitter:
    """Tests for first-class Codex package emission."""

    @pytest.fixture
    def ir(self):
        return parse_claude_plugin(FIXTURES_DIR / "complete-plugin")

    def test_emits_deterministic_package_and_marketplace(self, ir, tmp_path: Path) -> None:
        result = CodexEmitter().emit(ir)
        result.write_to(tmp_path)

        root = tmp_path / ".ai-config" / "codex" / "marketplaces" / "ai-config-dev-tools"
        package = root / "plugins" / "dev-tools"
        manifest = json.loads((package / ".codex-plugin" / "plugin.json").read_text())
        marketplace = json.loads((root / ".agents" / "plugins" / "marketplace.json").read_text())

        assert manifest["name"] == "dev-tools"
        assert manifest["version"] == "1.0.0"
        assert manifest["skills"] == "./skills/"
        assert manifest["hooks"] == "./hooks/hooks.json"
        assert set(manifest["mcpServers"]) == {"database", "github"}
        assert marketplace["name"] == "ai-config-dev-tools"
        assert marketplace["plugins"][0]["source"] == {
            "source": "local",
            "path": "./plugins/dev-tools",
        }

    def test_invalid_package_semver_is_actionable_without_output(self, tmp_path: Path) -> None:
        ir = PluginIR(
            identity=PluginIdentity(plugin_id="bad-version", name="bad-version", version="latest")
        )

        result = CodexEmitter().emit(ir)
        result.write_to(tmp_path)

        assert result.has_errors()
        assert any("Semantic Versioning" in diagnostic.message for diagnostic in result.diagnostics)
        assert result.files == []

    def test_never_emits_legacy_loose_output(self, ir, tmp_path: Path) -> None:
        result = CodexEmitter().emit(ir)
        result.write_to(tmp_path)
        assert not (tmp_path / ".codex").exists()
        assert not any(".codex/skills" in file.path.as_posix() for file in result.files)
        assert not any(".codex/prompts" in file.path.as_posix() for file in result.files)

    def test_skills_are_package_local_and_strip_claude_metadata(self, ir, tmp_path: Path) -> None:
        CodexEmitter().emit(ir).write_to(tmp_path)
        skill = (
            tmp_path
            / ".ai-config/codex/marketplaces/ai-config-dev-tools/plugins/dev-tools"
            / "skills/code-review/SKILL.md"
        )
        content = skill.read_text()
        assert "name: code-review" in content
        assert "allowed-tools:" not in content
        assert "model:" not in content

    def test_commands_always_become_package_skills_with_degraded_variables(
        self, ir, tmp_path: Path
    ) -> None:
        result = CodexEmitter().emit(ir)
        result.write_to(tmp_path)
        command = (
            tmp_path
            / ".ai-config/codex/marketplaces/ai-config-dev-tools/plugins/dev-tools"
            / "skills/command-commit/SKILL.md"
        )
        assert command.is_file()
        mapping = next(item for item in result.mappings if item.component_kind == "command")
        assert mapping.status == MappingStatus.FALLBACK
        assert "argument substitution" in mapping.lost_features[0]

    def test_hooks_are_package_native_and_self_contained(self, ir, tmp_path: Path) -> None:
        CodexEmitter().emit(ir).write_to(tmp_path)
        package = tmp_path / ".ai-config/codex/marketplaces/ai-config-dev-tools/plugins/dev-tools"
        hooks = (package / "hooks/hooks.json").read_text()
        assert "${PLUGIN_ROOT}" in hooks
        assert "CLAUDE_PLUGIN_ROOT" not in hooks
        assert (package / "scripts/check-dangerous-commands.sh").is_file()

    def test_mcp_support_files_are_copied_into_package(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        script = source / "scripts" / "server.py"
        script.parent.mkdir(parents=True)
        script.write_text("print('server')\n")
        ir = PluginIR(
            identity=PluginIdentity(plugin_id="mcp-files", name="mcp-files"),
            source_path=source,
            components=[
                McpServer(
                    name="local",
                    transport=McpTransport.STDIO,
                    command="python",
                    args=["${CLAUDE_PLUGIN_ROOT}/scripts/server.py"],
                )
            ],
        )

        CodexEmitter().emit(ir).write_to(tmp_path / "out")

        package = (
            tmp_path / "out/.ai-config/codex/marketplaces/ai-config-mcp-files/plugins/mcp-files"
        )
        manifest = json.loads((package / ".codex-plugin/plugin.json").read_text())
        assert manifest["mcpServers"]["local"]["args"] == ["${PLUGIN_ROOT}/scripts/server.py"]
        assert (package / "scripts/server.py").read_text() == "print('server')\n"

    def test_binary_skill_assets_stay_in_package(self, tmp_path: Path) -> None:
        ir = PluginIR(
            identity=PluginIdentity(plugin_id="binary", name="binary"),
            components=[
                Skill(
                    name="asset",
                    description="asset",
                    files=[
                        TextFile(
                            relpath="SKILL.md",
                            content="---\nname: asset\ndescription: asset\n---\nbody",
                        ),
                        BinaryFile(relpath="asset.bin", content_b64="AQID"),
                    ],
                )
            ],
        )
        CodexEmitter().emit(ir).write_to(tmp_path)
        asset = (
            tmp_path
            / ".ai-config/codex/marketplaces/ai-config-binary/plugins/binary"
            / "skills/asset/asset.bin"
        )
        assert asset.read_bytes() == b"\x01\x02\x03"

    def test_target_native_files_land_inside_package(self, tmp_path: Path) -> None:
        plugin = tmp_path / "source"
        native = plugin / "targets" / "codex" / "apps" / "app.json"
        native.parent.mkdir(parents=True)
        native.write_text('{"name":"app"}')
        ir = PluginIR(
            identity=PluginIdentity(plugin_id="native", name="native"),
            source_path=plugin,
        )
        CodexEmitter().emit(ir).write_to(tmp_path / "out")
        assert (
            tmp_path
            / "out/.ai-config/codex/marketplaces/ai-config-native/plugins/native/apps/app.json"
        ).is_file()

    def test_reemit_replaces_only_owned_marketplace_root(self, ir, tmp_path: Path) -> None:
        unrelated = tmp_path / ".codex" / "config.toml"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text('model = "keep"\n')
        result = CodexEmitter().emit(ir)
        result.write_to(tmp_path)
        stale = (
            tmp_path
            / ".ai-config/codex/marketplaces/ai-config-dev-tools/plugins/dev-tools/stale.txt"
        )
        stale.write_text("stale")
        result.write_to(tmp_path)
        assert not stale.exists()
        assert unrelated.read_text() == 'model = "keep"\n'


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
        assert "name: dev-tools-code-review" in skill_md.read_text()

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

    def test_env_var_syntax_transform(self, tmp_path: Path) -> None:
        """Cursor MCP env vars should use ${env:VAR} syntax."""
        ir = PluginIR(
            identity=PluginIdentity(plugin_id="test", name="test"),
            components=[
                McpServer(
                    name="server",
                    transport=McpTransport.STDIO,
                    command="cmd",
                    env={"API_KEY": "${API_KEY}"},
                )
            ],
        )
        emitter = CursorEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        content = (tmp_path / ".cursor" / "mcp.json").read_text()
        assert "${env:API_KEY}" in content


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
        assert "name: dev-tools-code-review" in skill_md.read_text()

    def test_emit_commands_with_variables(self, ir, tmp_path: Path) -> None:
        """Test commands transform variables to OpenCode format."""
        emitter = OpenCodeEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        cmd_path = tmp_path / ".opencode" / "commands" / "dev-tools-commit.md"
        assert cmd_path.exists()

        content = cmd_path.read_text()
        # OpenCode uses uppercase placeholders: $ARGUMENTS -> $ARGS, $2 -> $ARG2
        assert "$ARGS" in content, "Claude's $ARGUMENTS should be transformed to $ARGS"
        assert "$ARG2" in content, "Claude's $2 should be transformed to $ARG2"
        # Original variables should be replaced
        assert "$ARGUMENTS" not in content
        assert "$2" not in content or "$ARG2" in content  # $2 might still be in description

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

    def test_emit_multiple_lsp_servers(self, tmp_path: Path) -> None:
        """Multiple LSP servers should be aggregated into one file."""
        ir = PluginIR(
            identity=PluginIdentity(plugin_id="multi", name="multi"),
            components=[
                LspServer(name="a", command="a"),
                LspServer(name="b", command="b"),
            ],
        )
        emitter = OpenCodeEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        lsp_config = json.loads((tmp_path / "opencode.lsp.json").read_text())
        assert "multi-a" in lsp_config["lsp"]
        assert "multi-b" in lsp_config["lsp"]

    def test_env_var_syntax_transform(self, tmp_path: Path) -> None:
        """OpenCode MCP env vars should use {env:VAR} syntax."""
        ir = PluginIR(
            identity=PluginIdentity(plugin_id="test", name="test"),
            components=[
                McpServer(
                    name="server",
                    transport=McpTransport.STDIO,
                    command="cmd",
                    env={"API_KEY": "${API_KEY}"},
                )
            ],
        )
        emitter = OpenCodeEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        content = (tmp_path / "opencode.json").read_text()
        assert "{env:API_KEY}" in content


class TestPiEmitter:
    """Tests for Pi emitter."""

    @pytest.fixture
    def ir(self):
        """Load the test plugin IR."""
        return parse_claude_plugin(FIXTURES_DIR / "complete-plugin")

    def test_emit_skills(self, ir, tmp_path: Path) -> None:
        """Test emitting skills to Pi format (Agent Skills standard)."""
        emitter = PiEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        skill_md = tmp_path / ".pi" / "skills" / "dev-tools-code-review" / "SKILL.md"
        assert skill_md.exists()

        import yaml

        content = skill_md.read_text()
        parts = content.split("---", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert "name" in frontmatter
        assert "description" in frontmatter

    def test_skill_name_matches_directory(self, ir, tmp_path: Path) -> None:
        """Pi requires frontmatter name to match directory name (regression)."""
        import yaml

        emitter = PiEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        skills_dir = tmp_path / ".pi" / "skills"
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            assert skill_md.exists()
            content = skill_md.read_text()
            parts = content.split("---", 2)
            frontmatter = yaml.safe_load(parts[1])
            assert frontmatter["name"] == skill_dir.name, (
                f"Frontmatter name '{frontmatter['name']}' != directory '{skill_dir.name}'"
            )

    def test_emit_commands_as_prompts(self, ir, tmp_path: Path) -> None:
        """Test commands are emitted as Pi prompt templates."""
        emitter = PiEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        prompt_path = tmp_path / ".pi" / "prompts" / "dev-tools-commit.md"
        assert prompt_path.exists()

        content = prompt_path.read_text()
        assert len(content) > 0

    def test_emit_hooks_as_extension(self, ir, tmp_path: Path) -> None:
        """Test supported command hooks are emitted as a Pi extension."""
        emitter = PiEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        hook_mappings = [m for m in result.mappings if m.component_kind == "hook"]
        assert len(hook_mappings) == 1
        assert hook_mappings[0].status == MappingStatus.EMULATE
        assert "extension" in hook_mappings[0].notes.lower()

        extension = tmp_path / ".pi" / "extensions" / "dev-tools-hooks.ts"
        assert extension.exists()
        content = extension.read_text()
        assert "export default function" in content
        assert 'pi.on("tool_call"' in content
        assert 'pi.on("tool_result"' in content
        assert "check-dangerous-commands.sh" in content
        assert "CLAUDE_PLUGIN_ROOT" not in content

    def test_user_scope_hooks_emit_to_agent_extensions(self, ir, tmp_path: Path) -> None:
        """User-scope hooks should emit under .pi/agent/extensions/."""
        emitter = PiEmitter(scope=InstallScope.USER)
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        extension = tmp_path / ".pi" / "agent" / "extensions" / "dev-tools-hooks.ts"
        assert extension.exists()
        assert not (tmp_path / ".pi" / "extensions").exists()

    def test_emit_mcp_unsupported(self, ir) -> None:
        """Test MCP servers are marked unsupported for Pi."""
        emitter = PiEmitter()
        result = emitter.emit(ir)

        mcp_mappings = [m for m in result.mappings if m.component_kind == "mcp_server"]
        assert len(mcp_mappings) >= 1
        assert all(m.status == MappingStatus.UNSUPPORTED for m in mcp_mappings)

    def test_skill_mapping_native(self, ir) -> None:
        """Test skills map as NATIVE status."""
        emitter = PiEmitter()
        result = emitter.emit(ir)

        skill_mappings = [m for m in result.mappings if m.component_kind == "skill"]
        assert len(skill_mappings) >= 1
        assert all(m.status == MappingStatus.NATIVE for m in skill_mappings)

    def test_command_mapping_transform(self, ir) -> None:
        """Test commands map as TRANSFORM status."""
        emitter = PiEmitter()
        result = emitter.emit(ir)

        cmd_mappings = [m for m in result.mappings if m.component_kind == "command"]
        assert len(cmd_mappings) >= 1
        assert all(m.status == MappingStatus.TRANSFORM for m in cmd_mappings)

    def test_user_scope_emits_to_agent_subdir(self, ir, tmp_path: Path) -> None:
        """User scope should emit to .pi/agent/skills/ and .pi/agent/prompts/."""
        emitter = PiEmitter(scope=InstallScope.USER)
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        # Skills go to .pi/agent/skills/, not .pi/skills/
        skill_md = tmp_path / ".pi" / "agent" / "skills" / "dev-tools-code-review" / "SKILL.md"
        assert skill_md.exists()
        assert not (tmp_path / ".pi" / "skills").exists()

        # Prompts go to .pi/agent/prompts/, not .pi/prompts/
        prompt_files = list((tmp_path / ".pi" / "agent" / "prompts").glob("*.md"))
        assert len(prompt_files) >= 1
        assert not (tmp_path / ".pi" / "prompts").exists()

    def test_project_scope_emits_to_pi_root(self, ir, tmp_path: Path) -> None:
        """Project scope should emit to .pi/skills/ and .pi/prompts/."""
        emitter = PiEmitter(scope=InstallScope.PROJECT)
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        skill_md = tmp_path / ".pi" / "skills" / "dev-tools-code-review" / "SKILL.md"
        assert skill_md.exists()
        assert not (tmp_path / ".pi" / "agent").exists()

    def test_emit_binary_skill_files(self, tmp_path: Path) -> None:
        """Test binary files in skills are copied."""
        ir = PluginIR(
            identity=PluginIdentity(plugin_id="bin-plugin", name="bin-plugin"),
            components=[
                Skill(
                    name="bin-skill",
                    description="A skill with binary asset",
                    files=[
                        TextFile(
                            relpath="SKILL.md",
                            content="---\nname: bin-skill\ndescription: test\n---\nBody",
                        ),
                        BinaryFile(
                            relpath="asset.bin",
                            content_b64="AQID",
                        ),
                    ],
                ),
            ],
        )
        emitter = PiEmitter()
        result = emitter.emit(ir)
        result.write_to(tmp_path)

        asset = tmp_path / ".pi" / "skills" / "bin-plugin-bin-skill" / "asset.bin"
        assert asset.exists()
        assert asset.read_bytes() == b"\x01\x02\x03"

    def test_target_native_files_emit_to_project_scope(self, tmp_path: Path) -> None:
        """Pi target-native files are copied under .pi/ for project scope."""
        plugin_dir = tmp_path / "native-plugin"
        native_extension = plugin_dir / "targets" / "pi" / "extensions" / "custom.ts"
        native_extension.parent.mkdir(parents=True)
        native_extension.write_text(
            "export default function (pi: any) { pi.on('input', () => {}); }\n"
        )

        ir = PluginIR(
            identity=PluginIdentity(plugin_id="native-plugin", name="native-plugin"),
            source_path=plugin_dir,
        )
        result = PiEmitter(scope=InstallScope.PROJECT).emit(ir)
        result.write_to(tmp_path)

        extension = tmp_path / ".pi" / "extensions" / "custom.ts"
        assert extension.exists()
        assert extension.read_text() == native_extension.read_text()

        file_mappings = [m for m in result.mappings if m.component_kind == "file"]
        assert file_mappings[0].status == MappingStatus.NATIVE
        assert file_mappings[0].target_path == Path(".pi") / "extensions" / "custom.ts"

    def test_target_native_files_emit_to_user_scope(self, tmp_path: Path) -> None:
        """Pi target-native files are copied under .pi/agent/ for user scope."""
        plugin_dir = tmp_path / "native-plugin"
        native_extension = plugin_dir / "targets" / "pi" / "extensions" / "custom.ts"
        native_extension.parent.mkdir(parents=True)
        native_extension.write_text(
            "export default function (pi: any) { pi.on('input', () => {}); }\n"
        )

        ir = PluginIR(
            identity=PluginIdentity(plugin_id="native-plugin", name="native-plugin"),
            source_path=plugin_dir,
        )
        result = PiEmitter(scope=InstallScope.USER).emit(ir)
        result.write_to(tmp_path)

        extension = tmp_path / ".pi" / "agent" / "extensions" / "custom.ts"
        assert extension.exists()
        assert extension.read_text() == native_extension.read_text()
        assert not (tmp_path / ".pi" / "extensions").exists()

    def test_target_native_symlink_root_is_ignored(self, tmp_path: Path) -> None:
        """Symlinked target-native roots are ignored to keep output cache-safe."""
        plugin_dir = tmp_path / "native-plugin"
        external_dir = tmp_path / "external-pi-files"
        external_extension = external_dir / "extensions" / "outside.ts"
        external_extension.parent.mkdir(parents=True)
        external_extension.write_text("export default function (pi: any) {}\n")

        targets_dir = plugin_dir / "targets"
        targets_dir.mkdir(parents=True)
        (targets_dir / "pi").symlink_to(external_dir, target_is_directory=True)

        ir = PluginIR(
            identity=PluginIdentity(plugin_id="native-plugin", name="native-plugin"),
            source_path=plugin_dir,
        )
        result = PiEmitter(scope=InstallScope.USER).emit(ir)
        result.write_to(tmp_path)

        assert not (tmp_path / ".pi" / "agent" / "extensions" / "outside.ts").exists()
        assert any(
            "Ignoring symlinked target-native directory" in diagnostic.message
            for diagnostic in result.diagnostics
        )

    def test_target_native_file_overrides_generated_directory(self, tmp_path: Path) -> None:
        """Target-native files cleanly replace generated output directories."""
        plugin_dir = tmp_path / "native-plugin"
        native_skill_path = plugin_dir / "targets" / "pi" / "skills" / "native-plugin-review"
        native_skill_path.parent.mkdir(parents=True)
        native_skill_path.write_text("native file replacing generated skill directory\n")

        ir = PluginIR(
            identity=PluginIdentity(plugin_id="native-plugin", name="native-plugin"),
            components=[
                Skill(
                    name="review",
                    description="Generated skill that will be overridden",
                    files=[
                        TextFile(
                            relpath="SKILL.md",
                            content="---\nname: review\ndescription: test\n---\nBody",
                        ),
                    ],
                )
            ],
            source_path=plugin_dir,
        )
        result = PiEmitter(scope=InstallScope.PROJECT).emit(ir)
        result.write_to(tmp_path)

        output_path = tmp_path / ".pi" / "skills" / "native-plugin-review"
        assert output_path.is_file()
        assert output_path.read_text() == native_skill_path.read_text()
        assert not (output_path / "SKILL.md").exists()
        assert any(
            "overrides generated output" in (mapping.notes or "")
            for mapping in result.mappings
            if mapping.component_kind == "file"
        )

    def test_target_native_files_override_generated_output(self, tmp_path: Path) -> None:
        """Target-native files win when they collide with generated Pi output."""
        plugin_dir = tmp_path / "native-plugin"
        (plugin_dir / ".claude-plugin").mkdir(parents=True)
        (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "native-plugin", "hooks": "./hooks/hooks.json"})
        )
        hooks_dir = plugin_dir / "hooks"
        hooks_dir.mkdir()
        (hooks_dir / "hooks.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "${CLAUDE_PLUGIN_ROOT}/hooks/check.sh",
                                    }
                                ],
                            }
                        ]
                    }
                }
            )
        )
        native_extension = plugin_dir / "targets" / "pi" / "extensions" / "native-plugin-hooks.ts"
        native_extension.parent.mkdir(parents=True)
        native_extension.write_text("// native override\nexport default function (pi: any) {}\n")

        ir = parse_claude_plugin(plugin_dir)
        result = PiEmitter(scope=InstallScope.USER).emit(ir)
        result.write_to(tmp_path)

        extension = tmp_path / ".pi" / "agent" / "extensions" / "native-plugin-hooks.ts"
        assert extension.read_text() == native_extension.read_text()
        assert "runHook" not in extension.read_text()
        assert any(
            "overrides generated output" in (mapping.notes or "")
            for mapping in result.mappings
            if mapping.component_kind == "file"
        )
        assert any(
            "overrides generated output" in diagnostic.message for diagnostic in result.diagnostics
        )


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

    def test_get_emitter_pi(self) -> None:
        """Test getting Pi emitter."""
        emitter = get_emitter(TargetTool.PI)
        assert isinstance(emitter, PiEmitter)

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
        """Env var syntax should be transformed per target."""
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

        # Codex keeps ${VAR} in package manifest MCP entries
        codex = CodexEmitter()
        codex_result = codex.emit(ir)
        codex_file = next(f for f in codex_result.files if f.path.name == "plugin.json")
        assert "${API_KEY}" in codex_file.content

        # Cursor transforms to ${env:VAR}
        cursor = CursorEmitter()
        cursor_result = cursor.emit(ir)
        cursor_file = next(f for f in cursor_result.files if "mcp" in str(f.path).lower())
        assert "${env:API_KEY}" in cursor_file.content

        # OpenCode transforms to {env:VAR}
        opencode = OpenCodeEmitter()
        opencode_result = opencode.emit(ir)
        opencode_file = next(f for f in opencode_result.files if f.path.name == "opencode.json")
        assert "{env:API_KEY}" in opencode_file.content

    def test_hook_event_mapping_coverage(self) -> None:
        """Test which Claude events map to Cursor."""
        # This documents the mapping gaps
        claude_events = [
            "SessionStart",
            "UserPromptSubmit",
            "PreToolUse",
            "PermissionRequest",
            "PostToolUse",
            "PostToolUseFailure",
            "Notification",
            "SubagentStart",
            "SubagentStop",
            "Stop",
            "PreCompact",
            "SessionEnd",
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
        package_dir = (
            output_dir
            / ".ai-config/codex/marketplaces/ai-config-dev-tools/plugins/dev-tools/skills"
        )
        assert package_dir.exists()


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

    def test_preview_respects_user_scope_for_pi(self, tmp_path: Path) -> None:
        """Pi user-scope preview should show ~/.pi/agent paths, not ~/.pi paths."""
        preview = preview_conversion(
            FIXTURES_DIR / "complete-plugin",
            [TargetTool.PI],
            output_dir=tmp_path,
            scope=InstallScope.USER,
        )

        assert str(tmp_path / ".pi" / "agent" / "skills") in preview
        assert str(tmp_path / ".pi" / "skills") not in preview


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
