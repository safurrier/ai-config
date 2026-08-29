# E2E testing infrastructure

Docker-based end-to-end tests validate ai-config against real AI coding-tool command-line interfaces.

## Docker test images

| Image | Tag | Dockerfile | Tools |
|---|---|---|---|
| claude-only | `ai-config-test:claude-only` | `tests/docker/Dockerfile.claude-only` | Claude Code |
| all-tools | `ai-config-test:all-tools` | `tests/docker/Dockerfile.all-tools` | Claude, Codex, OpenCode, Cursor |

The test session builds each image once and caches it for later tests.

## Fixture hierarchy

`tests/e2e/conftest.py` defines this fixture hierarchy.

```
docker_available (session)     ← checks Docker daemon
  └─ docker_client (session)   ← SDK client (auto-detects Colima/Desktop/Linux)
       ├─ claude_image (session)      ← builds/caches claude-only image
       │    └─ claude_container (class) ← runs container, auto-remove on stop
       └─ all_tools_image (session)   ← builds/caches all-tools image
            └─ all_tools_container (class) ← runs container, auto-remove on stop
```

Class-scoped containers share state among methods in one class. Each class gets a fresh container.

Container environment:

- User: `testuser`
- Working directory: `/home/testuser/ai-config`
- Repository: copied into the container, not mounted as a volume

## Helper functions

```python
exec_in_container(container, command, user="testuser") -> (exit_code, output)
check_tool_installed(container, tool_name, version_cmd) -> (bool, version_or_error)
```

## Tmux test helper

`tests/e2e/tmux_helper.py` provides `TmuxTestSession` for interactive CLIs:

```python
with TmuxTestSession() as session:
    session.create_session(working_dir="/home/testuser/ai-config")
    session.send_keys("codex --version")
    session.wait_for_output("codex", timeout=10.0)
    output = session.capture_pane()
```

Its key methods are `send_keys()`, `capture_pane()`, `wait_for_output()`, and `wait_for_prompt()`. Use `is_tmux_available()` as a standalone check.

## Test suites

| File | Marker | Container | Purpose |
|---|---|---|---|
| `test_conversion.py` | `e2e`, `docker` | claude | Convert command, per-target output, binary assets, reports, doctor |
| `test_fresh_install.py` | `e2e`, `docker`, `slow` | all-tools | Sync, dry-run, config validation, status |
| `test_integration_smoke.py` | `e2e`, `docker` | claude | Full workflow: preflight → convert → verify → sync |
| `test_tool_validation.py` | `e2e`, `docker`, `slow` | all-tools | Interactive CLI introspection via tmux |

## Write E2E tests

1. Choose `claude_container` for fast Claude tests or `all_tools_container` for tests that need several tools.
2. Use `exec_in_container()` for non-interactive commands.
3. Use `TmuxTestSession` for interactive CLI tests.
4. Add `@pytest.mark.e2e` and `@pytest.mark.docker`. Add `@pytest.mark.slow` for all-tools tests.
5. Group related tests in one class to share container state.

## Configuration path requirement

Configuration in `~/.ai-config/config.yaml` resolves relative paths from `/home/testuser/`, not from the repository. Use absolute paths:

```python
REPO_DIR = "/home/testuser/ai-config"
config = f"path: {REPO_DIR}/tests/fixtures/test-marketplace"
```

## Run locally

```bash
# All E2E tests (needs Docker)
uv run pytest tests/e2e/ -m "e2e and docker" -v

# Just the smoke test (fast, claude-only)
uv run pytest tests/e2e/test_integration_smoke.py -v

# Interactive debug shell
python tests/docker/test_in_docker.py --shell

# See also: tests/e2e/MANUAL_VALIDATION.md for interactive checks
```
