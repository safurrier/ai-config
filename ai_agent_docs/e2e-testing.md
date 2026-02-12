# E2E Testing Infrastructure

Docker-based E2E tests that validate ai-config against real AI coding tool CLIs.

## Docker Images

| Image | Tag | Dockerfile | Tools |
|-------|-----|------------|-------|
| claude-only | `ai-config-test:claude-only` | `tests/docker/Dockerfile.claude-only` | Claude Code |
| all-tools | `ai-config-test:all-tools` | `tests/docker/Dockerfile.all-tools` | Claude, Codex, OpenCode, Cursor |

Images are session-scoped (built once per test run, cached across runs).

## Fixture Hierarchy (`tests/e2e/conftest.py`)

```
docker_available (session)     ← checks Docker daemon
  └─ docker_client (session)   ← SDK client (auto-detects Colima/Desktop/Linux)
       ├─ claude_image (session)      ← builds/caches claude-only image
       │    └─ claude_container (class) ← runs container, auto-remove on stop
       └─ all_tools_image (session)   ← builds/caches all-tools image
            └─ all_tools_container (class) ← runs container, auto-remove on stop
```

**Class-scoped containers**: Tests within one class share a container (state persists between methods). Different classes get fresh containers.

Container environment:
- User: `testuser`
- Working dir: `/home/testuser/ai-config`
- Repo mounted as copy (not volume)

## Helper Functions

```python
exec_in_container(container, command, user="testuser") -> (exit_code, output)
check_tool_installed(container, tool_name, version_cmd) -> (bool, version_or_error)
```

## Tmux Helper (`tests/e2e/tmux_helper.py`)

`TmuxTestSession` drives interactive CLIs inside containers:

```python
with TmuxTestSession() as session:
    session.create_session(working_dir="/home/testuser/ai-config")
    session.send_keys("codex --version")
    session.wait_for_output("codex", timeout=10.0)
    output = session.capture_pane()
```

Key methods: `send_keys()`, `capture_pane()`, `wait_for_output()`, `wait_for_prompt()`

Standalone check: `is_tmux_available() -> bool`

## Test Suites

| File | Marker | Container | Purpose |
|------|--------|-----------|---------|
| `test_conversion.py` | `e2e`, `docker` | claude | Convert command, per-target output, binary assets, reports, doctor |
| `test_fresh_install.py` | `e2e`, `docker`, `slow` | all-tools | Sync, dry-run, config validation, status |
| `test_integration_smoke.py` | `e2e`, `docker` | claude | Full workflow: preflight → convert → verify → sync |
| `test_tool_validation.py` | `e2e`, `docker`, `slow` | all-tools | Interactive CLI introspection via tmux |

## Writing New E2E Tests

1. Choose container: `claude_container` (fast) or `all_tools_container` (needs multiple tools)
2. Use `exec_in_container()` for non-interactive commands
3. Use `TmuxTestSession` for interactive CLI testing
4. Mark with `@pytest.mark.e2e` + `@pytest.mark.docker` (add `@pytest.mark.slow` for all-tools)
5. Group related tests in a class (shares container state)

## Config Path Gotcha

Config written to `~/.ai-config/config.yaml` resolves relative paths from `/home/testuser/`, not the repo. Always use absolute paths:

```python
REPO_DIR = "/home/testuser/ai-config"
config = f"path: {REPO_DIR}/tests/fixtures/test-marketplace"
```

## Running Locally

```bash
# All E2E tests (needs Docker)
uv run pytest tests/e2e/ -m "e2e and docker" -v

# Just the smoke test (fast, claude-only)
uv run pytest tests/e2e/test_integration_smoke.py -v

# Interactive debug shell
python tests/docker/test_in_docker.py --shell

# See also: tests/e2e/MANUAL_VALIDATION.md for interactive checks
```
