# Plugin Conversion Implementation Plan

**Date**: 2026-02-04
**Status**: Updated after prototype validation
**Branch**: `research/plugin-conversion-feasibility`

---

## Overview

This plan incorporates learnings from the working prototype and addresses identified gaps. The goal is production-ready plugin conversion integrated into ai-config.

---

## Phase 1: Core Conversion (DONE - Prototype)

### Completed
- [x] Pydantic IR models
- [x] Claude plugin parser
- [x] Emitters for Codex, Cursor, OpenCode
- [x] Unit tests (24 tests, all passing)
- [x] Sample plugin fixture

### Known Gaps from Prototype
- [ ] Binary file handling (silently skipped)
- [ ] Env var syntax transformation
- [ ] Nested skill directories
- [ ] Path normalization edge cases

---

## Phase 2: Production Hardening

### 2.1 Conversion Report System

Generate a detailed, reusable report for each conversion:

```python
@dataclass
class ConversionReport:
    """Complete record of a conversion operation."""

    # Identity
    source_plugin: PluginIdentity
    target_tool: TargetTool
    timestamp: datetime

    # Results
    components_converted: list[ComponentMapping]
    components_skipped: list[ComponentMapping]
    components_degraded: list[ComponentMapping]  # Lost functionality

    # Files
    files_written: list[Path]
    files_skipped: list[Path]  # Binary, too large, etc.

    # Diagnostics
    errors: list[Diagnostic]
    warnings: list[Diagnostic]
    info: list[Diagnostic]

    # Metadata
    dry_run: bool
    best_effort: bool  # Continue despite errors

    def to_json(self) -> str: ...
    def to_markdown(self) -> str: ...  # Human-readable
    def summary(self) -> str: ...  # One-line summary
```

**Output formats:**
- JSON (machine-readable, for CI/automation)
- Markdown (human-readable, includes recommendations)
- Console (colorized summary with Rich)

### 2.2 Dry-Run Support

Add `--dry-run` flag that:
1. Parses source plugin
2. Runs all conversions
3. Generates report showing what WOULD be written
4. Does NOT write any files
5. Returns non-zero if errors would occur

```python
class EmitResult:
    # Existing fields...

    def preview(self) -> str:
        """Generate preview of what would be written."""
        lines = []
        for f in self.files:
            lines.append(f"{'[CREATE]' if not f.path.exists() else '[UPDATE]'} {f.path}")
            lines.append(f"  {len(f.content)} bytes")
        return "\n".join(lines)
```

### 2.3 Best-Effort Conversion

Add `--best-effort` flag that:
1. Continues conversion even when components fail
2. Converts everything possible
3. Loudly warns about each failure
4. Generates comprehensive report
5. Exits with warning code (not error)

```python
def convert_best_effort(ir: PluginIR, targets: list[TargetTool]) -> dict[TargetTool, EmitResult]:
    results = {}
    for target in targets:
        try:
            emitter = get_emitter(target)
            results[target] = emitter.emit(ir)
        except Exception as e:
            # Create error result instead of failing
            results[target] = EmitResult(
                target=target,
                diagnostics=[Diagnostic(Severity.ERROR, str(e))]
            )
    return results
```

### 2.4 Nested Skill Directory Support

Update parser to handle:
```
skills/
├── simple-skill/
│   └── SKILL.md
├── category/
│   ├── skill-a/
│   │   └── SKILL.md
│   └── skill-b/
│       └── SKILL.md
└── deep/
    └── nested/
        └── skill-c/
            └── SKILL.md
```

```python
def _find_skills_recursive(self, base_path: Path, max_depth: int = 5) -> list[Path]:
    """Find all SKILL.md files up to max_depth."""
    skills = []
    for skill_md in base_path.rglob("SKILL.md"):
        # Check depth
        rel_path = skill_md.relative_to(base_path)
        if len(rel_path.parts) <= max_depth:
            skills.append(skill_md.parent)
    return skills
```

### 2.5 Env Var Syntax Transformation

Add syntax transformation during emission:

```python
ENV_VAR_PATTERNS = {
    TargetTool.CLAUDE: r"\$\{(\w+)\}",           # ${VAR}
    TargetTool.CODEX: r"\$\{(\w+)\}",            # ${VAR} (same)
    TargetTool.CURSOR: r"\$\{env:(\w+)\}",       # ${env:VAR}
    TargetTool.OPENCODE: r"\{env:(\w+)\}",       # {env:VAR}
}

def transform_env_vars(content: str, source: TargetTool, target: TargetTool) -> str:
    """Transform env var syntax from source to target format."""
    source_pattern = ENV_VAR_PATTERNS[source]

    def replacer(match):
        var_name = match.group(1)
        if target == TargetTool.CURSOR:
            return f"${{env:{var_name}}}"
        elif target == TargetTool.OPENCODE:
            return f"{{env:{var_name}}}"
        else:
            return f"${{{var_name}}}"

    return re.sub(source_pattern, replacer, content)
```

---

## Phase 3: CLI Integration

### 3.1 New Commands

```bash
# Basic conversion
ai-config convert <plugin-path> --to codex,cursor,opencode

# With options
ai-config convert <plugin-path> --to codex \
    --output ./converted/ \
    --scope user \
    --dry-run \
    --best-effort \
    --report report.json

# Install after conversion
ai-config convert <plugin-path> --to codex --install

# Validate without converting
ai-config convert <plugin-path> --to codex --validate-only
```

### 3.2 CLI Implementation

```python
@main.group()
def convert() -> None:
    """Convert plugins between AI coding tools."""

@convert.command(name="plugin")
@click.argument("plugin_path", type=click.Path(exists=True, path_type=Path))
@click.option("--to", "targets", required=True, help="Target tools (comma-separated)")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output directory")
@click.option("--scope", type=click.Choice(["user", "project"]), default="project")
@click.option("--dry-run", is_flag=True, help="Show what would be done")
@click.option("--best-effort", is_flag=True, help="Continue despite errors")
@click.option("--install", is_flag=True, help="Install after conversion")
@click.option("--report", type=click.Path(path_type=Path), help="Write report to file")
def convert_plugin(
    plugin_path: Path,
    targets: str,
    output: Path | None,
    scope: str,
    dry_run: bool,
    best_effort: bool,
    install: bool,
    report: Path | None,
) -> None:
    """Convert a Claude Code plugin to other tool formats."""
    ...
```

---

## Phase 4: Interactive Wizard Integration

### 4.1 Conversion Prompt in Init Wizard

After plugin selection, ask about conversion:

```python
# In init.py, after plugin selection

if selected_plugins:
    # Check if other tools are installed
    other_tools = detect_installed_tools()  # Returns list of available tools

    if other_tools:
        convert_choice = questionary.select(
            "Would you like to convert plugins for other AI coding tools?",
            choices=[
                {"name": "No, just configure for Claude Code", "value": "none"},
                {"name": f"Yes, also convert for {', '.join(other_tools)}", "value": "all"},
                {"name": "Let me choose specific tools...", "value": "select"},
            ]
        ).ask()

        if convert_choice == "all":
            conversion_targets = other_tools
        elif convert_choice == "select":
            conversion_targets = questionary.checkbox(
                "Select target tools:",
                choices=[{"name": t, "value": t} for t in other_tools]
            ).ask()
        else:
            conversion_targets = []
```

### 4.2 Conversion Progress Display

```python
def show_conversion_progress(
    plugin: str,
    targets: list[str],
    results: dict[str, EmitResult]
) -> None:
    """Display conversion results with Rich."""

    console = Console()

    for target, result in results.items():
        if result.has_errors():
            console.print(f"[red]✗[/red] {target}: {len(result.diagnostics)} errors")
        elif result.diagnostics:
            console.print(f"[yellow]⚠[/yellow] {target}: {len(result.files)} files ({len(result.diagnostics)} warnings)")
        else:
            console.print(f"[green]✓[/green] {target}: {len(result.files)} files")

        # Show key mappings
        for mapping in result.mappings:
            status_icon = {
                MappingStatus.NATIVE: "✓",
                MappingStatus.TRANSFORM: "~",
                MappingStatus.FALLBACK: "↓",
                MappingStatus.UNSUPPORTED: "✗",
            }.get(mapping.status, "?")

            console.print(f"  {status_icon} {mapping.component_kind}:{mapping.component_name}")
```

### 4.3 Post-Sync Conversion Option

Add to `sync` command:

```python
@main.command()
@click.option("--convert-to", help="Also convert plugins to these targets")
def sync(convert_to: str | None) -> None:
    """Sync plugins to match config."""

    # Normal sync...
    result = sync_config(config)

    # Optional conversion
    if convert_to and result.success:
        targets = [TargetTool(t.strip()) for t in convert_to.split(",")]
        for plugin in config.plugins:
            if plugin.enabled:
                convert_plugin_to_targets(plugin, targets)
```

---

## Phase 5: E2E Validation Tests

### 5.1 Docker Infrastructure Updates

Add tmux to Dockerfiles:

```dockerfile
# In both Dockerfile.claude-only and Dockerfile.all-tools
RUN apt-get update && apt-get install -y \
    curl \
    git \
    tmux \  # ADD THIS
    ...
```

### 5.2 E2E Test Fixtures

Create conversion-specific fixtures:

```python
# tests/e2e/conftest.py

@pytest.fixture(scope="class")
def conversion_container(all_tools_container):
    """Container with test plugin ready for conversion."""
    container = all_tools_container

    # Copy test plugin
    exec_in_container(container, """
        cp -r /home/testuser/ai-config/tests/fixtures/sample-plugins/complete-plugin \
              /home/testuser/test-plugin
    """)

    yield container

@pytest.fixture
def tmux_session(conversion_container):
    """tmux session for TUI testing."""
    container = conversion_container

    # Start tmux
    exec_in_container(container, "tmux new-session -d -s test")
    yield container

    # Cleanup
    exec_in_container(container, "tmux kill-session -t test 2>/dev/null || true")
```

### 5.3 E2E Test Cases

```python
# tests/e2e/test_conversion.py

@pytest.mark.e2e
@pytest.mark.docker
class TestPluginConversion:
    """Test plugin conversion across tools."""

    def test_convert_to_codex_creates_files(self, conversion_container):
        """Verify conversion creates expected Codex files."""
        container = conversion_container

        # Run conversion
        exit_code, output = exec_in_container(
            container,
            "uv run ai-config convert /home/testuser/test-plugin --to codex --output /tmp/converted"
        )
        assert exit_code == 0

        # Check files created
        exit_code, output = exec_in_container(
            container,
            "ls -la /tmp/converted/.codex/skills/"
        )
        assert exit_code == 0
        assert "dev-tools-code-review" in output

    def test_convert_dry_run_no_files(self, conversion_container):
        """Verify dry-run doesn't create files."""
        container = conversion_container

        # Run dry-run conversion
        exit_code, output = exec_in_container(
            container,
            "uv run ai-config convert /home/testuser/test-plugin --to codex --dry-run"
        )
        assert exit_code == 0
        assert "[CREATE]" in output or "Would create" in output

        # Verify no files created
        exit_code, _ = exec_in_container(
            container,
            "ls /tmp/converted 2>&1"
        )
        assert exit_code != 0  # Directory shouldn't exist

    def test_convert_generates_report(self, conversion_container):
        """Verify conversion report is generated."""
        container = conversion_container

        exit_code, output = exec_in_container(
            container,
            "uv run ai-config convert /home/testuser/test-plugin --to codex --report /tmp/report.json"
        )
        assert exit_code == 0

        # Check report
        exit_code, report = exec_in_container(container, "cat /tmp/report.json")
        assert exit_code == 0

        data = json.loads(report)
        assert "components_converted" in data
        assert "target_tool" in data


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.slow
class TestConvertedPluginFunctionality:
    """Test that converted plugins actually work in target tools."""

    @pytest.mark.skipif(not check_tool_available("codex"), reason="Codex not available")
    def test_codex_recognizes_converted_skill(self, conversion_container, tmux_session):
        """Verify Codex can see converted skill."""
        container = tmux_session

        # Convert and install
        exec_in_container(
            container,
            "uv run ai-config convert /home/testuser/test-plugin --to codex --install --scope user"
        )

        # Start Codex in tmux
        exec_in_container(container, "tmux send-keys -t test 'codex' Enter")
        time.sleep(3)

        # Type / to see skills
        exec_in_container(container, "tmux send-keys -t test '/' ")
        time.sleep(1)

        # Capture output
        _, output = exec_in_container(container, "tmux capture-pane -t test -p")

        # Check skill appears (may need adjustment based on actual Codex UI)
        assert "code-review" in output.lower() or "skill" in output.lower()

    def test_converted_mcp_config_valid_json(self, conversion_container):
        """Verify MCP config is valid JSON."""
        container = conversion_container

        exec_in_container(
            container,
            "uv run ai-config convert /home/testuser/test-plugin --to cursor --output /tmp/cursor"
        )

        exit_code, output = exec_in_container(
            container,
            "python3 -c \"import json; json.load(open('/tmp/cursor/.cursor/mcp.json'))\""
        )
        assert exit_code == 0

    def test_converted_hooks_valid_json(self, conversion_container):
        """Verify Cursor hooks config is valid JSON."""
        container = conversion_container

        exec_in_container(
            container,
            "uv run ai-config convert /home/testuser/test-plugin --to cursor --output /tmp/cursor"
        )

        exit_code, output = exec_in_container(
            container,
            "python3 -c \"import json; d=json.load(open('/tmp/cursor/.cursor/hooks.json')); assert 'hooks' in d\""
        )
        assert exit_code == 0
```

### 5.4 Validation via Tool CLIs

```python
class TestToolCLIValidation:
    """Validate conversions using each tool's CLI."""

    def test_claude_plugin_validate(self, conversion_container):
        """Use claude plugin validate on source."""
        container = conversion_container

        exit_code, output = exec_in_container(
            container,
            "claude plugin validate /home/testuser/test-plugin"
        )
        # May exit non-zero if plugin.json location differs
        # Check for meaningful validation output
        assert "valid" in output.lower() or exit_code == 0

    @pytest.mark.skipif(not check_tool_available("opencode"), reason="OpenCode not available")
    def test_opencode_skill_loadable(self, conversion_container):
        """Verify OpenCode can load converted skill."""
        container = conversion_container

        # Convert to OpenCode format
        exec_in_container(
            container,
            "uv run ai-config convert /home/testuser/test-plugin --to opencode --output ~/.opencode"
        )

        # Check skill directory exists
        exit_code, output = exec_in_container(
            container,
            "ls ~/.opencode/skills/"
        )
        assert exit_code == 0
        assert "dev-tools" in output

        # Validate SKILL.md format
        exit_code, output = exec_in_container(
            container,
            "head -5 ~/.opencode/skills/dev-tools-code-review/SKILL.md"
        )
        assert "---" in output  # Has frontmatter
        assert "name:" in output
```

---

## Phase 6: Documentation

### 6.1 User Documentation

- Add to docs/: `plugin-conversion.md`
- Cover: supported tools, component mapping, limitations
- Include: examples, troubleshooting, FAQ

### 6.2 Developer Documentation

- Update `src/AGENTS.md` with converter architecture
- Document IR schema
- Document how to add new target tools

---

## Implementation Order

### Sprint 1: Core Production Features
1. [ ] Conversion report system
2. [ ] Dry-run support
3. [ ] Best-effort mode
4. [ ] CLI commands (`ai-config convert`)

### Sprint 2: Parser Improvements
5. [ ] Nested skill directories
6. [ ] Env var transformation
7. [ ] Binary file handling (or explicit skip with warning)
8. [ ] Path normalization hardening

### Sprint 3: Integration
9. [ ] Interactive wizard integration
10. [ ] Post-sync conversion option
11. [ ] Config file conversion targets

### Sprint 4: E2E Testing
12. [ ] Add tmux to Docker images
13. [ ] E2E test fixtures
14. [ ] CLI validation tests
15. [ ] TUI validation tests (where feasible)

### Sprint 5: Polish
16. [ ] User documentation
17. [ ] Developer documentation
18. [ ] Error messages and UX polish
19. [ ] Performance optimization (if needed)

---

## Success Criteria

1. **Conversion works**: 90%+ of plugin components convert successfully
2. **Reports are useful**: Users can understand what worked/failed
3. **Dry-run is reliable**: Preview matches actual conversion
4. **E2E tests pass**: Converted plugins are validated in Docker
5. **Wizard is intuitive**: Users can convert without reading docs
6. **Documentation is complete**: All features documented with examples
