"""Target-runtime acceptance proof for materialized shared skill resources."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.e2e.conftest import exec_in_container

if TYPE_CHECKING:
    from docker.models.containers import Container

pytestmark = [pytest.mark.e2e, pytest.mark.docker, pytest.mark.slow]


def _run_probe(container: Container, target: str) -> str:
    """Run one credential-free probe against an isolated temporary home."""
    exit_code, output = exec_in_container(
        container,
        "env -u ANTHROPIC_API_KEY -u CHATGPT_API_KEY -u CODEX_API_KEY "
        "-u CURSOR_API_KEY -u OPENAI_API_KEY -u OPENAI_ORG_ID -u OPENAI_PROJECT_ID "
        "-u OPENCODE_API_KEY -u PI_API_KEY "
        f"uv run python tests/probes/probe_shared_skill_resources.py --target {target}",
    )
    assert exit_code == 0, f"{target} shared-resource probe failed:\n{output}"
    assert '"result": "passed"' in output
    assert '"resources"' in output
    return output


class TestSharedSkillResourceRuntimes:
    """Prove the shared-includes fixture remains usable after target conversion."""

    def test_pi_discovers_project_and_user_skills_with_materialized_resources(
        self, all_tools_container: Container
    ) -> None:
        """Pi RPC discovers both scopes after byte/mode/reference checks."""
        output = _run_probe(all_tools_container, "pi")
        assert '"runtime": "real offline RPC/get_commands"' in output
        assert '"project"' in output and '"user"' in output

    def test_opencode_discovers_skills_with_accessible_materialized_resources(
        self, all_tools_container: Container
    ) -> None:
        """OpenCode debug skill discovers both self-contained converted skills."""
        output = _run_probe(all_tools_container, "opencode")
        assert '"runtime": "real opencode debug skill"' in output

    def test_codex_installs_and_discovers_package_with_materialized_resources(
        self, all_tools_container: Container
    ) -> None:
        """Codex installs the package and discovers skills with resources in its cache."""
        output = _run_probe(all_tools_container, "codex")
        assert "real marketplace/package install and debug prompt-input discovery" in output
        assert "shared-includes@ai-config-shared-includes" in output

    def test_cursor_file_shape_only_has_deterministic_materialized_resources(
        self, all_tools_container: Container
    ) -> None:
        """Cursor v1 proof is validator/file-shape only, not authenticated runtime execution."""
        output = _run_probe(all_tools_container, "cursor")
        assert "accepted v1 proof is deterministic file shape and validator only" in output
        assert '"credentials": "no credentials used"' in output
