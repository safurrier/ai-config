#!/usr/bin/env python3
"""Probe shared skill resources through auth-free target runtime surfaces."""

from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from probe_codex_plugin_package import SENSITIVE_ENV_VARS, load_json, run

from ai_config.codex_lifecycle import sync_codex_packages
from ai_config.converters import InstallScope, TargetTool, convert_plugin
from ai_config.converters.codex_package import codex_package_spec
from ai_config.validators.target.cursor import CursorOutputValidator

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests/fixtures/sample-plugins/shared-includes"
RESOURCE_PATHS = (
    Path("shared/data.txt"),
    Path("shared/dependency.json"),
    Path("shared/run.sh"),
    Path("shared/blob.bin"),
)
FORBIDDEN_OUTPUT = (b"x-ai-config-includes", b"CLAUDE_PLUGIN_ROOT")
AUTH_ENV_VARS = SENSITIVE_ENV_VARS | {
    "ANTHROPIC_API_KEY",
    "CURSOR_API_KEY",
    "OPENCODE_API_KEY",
    "PI_API_KEY",
}


def isolated_env(home: Path) -> dict[str, str]:
    """Return an isolated runtime environment with ambient credentials removed."""
    env = {key: value for key, value in os.environ.items() if key not in AUTH_ENV_VARS}
    env.update(
        {
            "HOME": str(home),
            "CODEX_HOME": str(home / ".codex"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
        }
    )
    return env


def convert(target: TargetTool, output: Path, scope: InstallScope = InstallScope.PROJECT) -> None:
    """Convert the checked-in fixture and require a successful report."""
    report = convert_plugin(FIXTURE, [target], output_dir=output, scope=scope)[target]
    if not report.success:
        raise AssertionError(report.to_json())


def assert_materialized(output: Path, skill_roots: tuple[Path, ...]) -> None:
    """Require self-contained, byte-exact, skill-relative shared resources."""
    for relative_root in skill_roots:
        skill_root = output / relative_root
        skill_text = (skill_root / "SKILL.md").read_text()
        if "_shared/shared/data.txt" not in skill_text:
            raise AssertionError(f"skill-relative shared resource reference missing: {skill_root}")
        for marker in FORBIDDEN_OUTPUT:
            if marker.decode() in skill_text:
                raise AssertionError(f"source-only marker remained in {skill_root / 'SKILL.md'}")
        for source_relative in RESOURCE_PATHS:
            source = FIXTURE / source_relative
            emitted = skill_root / "_shared" / source_relative
            if emitted.read_bytes() != source.read_bytes():
                raise AssertionError(f"materialized resource differs from source: {emitted}")
            source_executable = bool(source.stat().st_mode & stat.S_IXUSR)
            emitted_executable = bool(emitted.stat().st_mode & stat.S_IXUSR)
            if emitted_executable != source_executable:
                raise AssertionError(f"materialized executable bit differs from source: {emitted}")

    for path in output.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            for marker in FORBIDDEN_OUTPUT:
                if marker in content:
                    raise AssertionError(f"source-only marker {marker!r} remained in {path}")


def pi_commands(
    pi: str,
    *,
    cwd: Path,
    agent_dir: Path,
    env: dict[str, str],
) -> list[dict[str, object]]:
    """Read Pi's real auth-free RPC command discovery response."""
    runtime_env = dict(env)
    runtime_env.update({"PI_OFFLINE": "1", "PI_CODING_AGENT_DIR": str(agent_dir)})
    process = subprocess.Popen(
        [
            pi,
            "--offline",
            "--mode",
            "rpc",
            "--no-session",
            "--no-extensions",
            "--provider",
            "openai",
            "--model",
            "gpt-4o-mini",
            "--api-key",
            "fake",
        ],
        cwd=cwd,
        env=runtime_env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write('{"id":"shared-skills","type":"get_commands"}\n')
    process.stdin.flush()

    response: dict[str, object] | None = None
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            readable, _, _ = select.select([process.stdout], [], [], 0.5)
            if not readable:
                if process.poll() is not None:
                    break
                continue
            line = process.stdout.readline()
            if not line:
                break
            event: object = json.loads(line)
            if (
                isinstance(event, dict)
                and event.get("type") == "response"
                and event.get("command") == "get_commands"
            ):
                response = event
                break
    finally:
        process.kill()
        process.wait(timeout=5)

    if response is None:
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise AssertionError(f"Pi RPC get_commands did not respond; stderr:\n{stderr}")
    data = response.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("commands"), list):
        raise AssertionError(f"unexpected Pi get_commands response: {response}")
    return data["commands"]


def assert_pi_discovery(
    commands: list[dict[str, object]], expected_roots: tuple[Path, ...]
) -> None:
    """Require both converted skills and their exact emitted paths in Pi RPC."""
    by_name = {command.get("name"): command for command in commands}
    for skill_name, root in zip(("alpha", "beta"), expected_roots, strict=True):
        name = f"skill:shared-includes-{skill_name}"
        command = by_name.get(name)
        if command is None:
            raise AssertionError(f"converted Pi skill {name!r} missing: {commands}")
        source_info = command.get("sourceInfo")
        path = source_info.get("path") if isinstance(source_info, dict) else None
        expected = str((root / "SKILL.md").resolve())
        if path != expected:
            raise AssertionError(f"Pi reported {path!r} for {name}, expected {expected!r}")


def probe_pi(pi: str) -> dict[str, object]:
    """Convert both Pi scopes and discover them through real RPC/get_commands."""
    with tempfile.TemporaryDirectory(prefix="ai-config-shared-pi-") as temporary:
        root = Path(temporary)
        home = root / "home"
        home.mkdir()
        env = isolated_env(home)

        project = root / "project"
        convert(TargetTool.PI, project)
        project_relative = tuple(
            Path(f".pi/skills/shared-includes-{name}") for name in ("alpha", "beta")
        )
        assert_materialized(project, project_relative)
        project_roots = tuple(project / path for path in project_relative)
        assert_pi_discovery(
            pi_commands(pi, cwd=project, agent_dir=root / "project-agent", env=env),
            project_roots,
        )

        user = root / "user"
        convert(TargetTool.PI, user, InstallScope.USER)
        user_relative = tuple(
            Path(f".pi/agent/skills/shared-includes-{name}") for name in ("alpha", "beta")
        )
        assert_materialized(user, user_relative)
        user_roots = tuple(user / path for path in user_relative)
        assert_pi_discovery(
            pi_commands(pi, cwd=root, agent_dir=user / ".pi/agent", env=env),
            user_roots,
        )

    return {
        "result": "passed",
        "target": "pi",
        "runtime": "real offline RPC/get_commands",
        "scopes": ["project", "user"],
        "skills": ["shared-includes-alpha", "shared-includes-beta"],
        "resources": [str(path) for path in RESOURCE_PATHS],
        "credentials": "ambient credentials removed; fake offline key only",
    }


def probe_opencode(opencode: str) -> dict[str, object]:
    """Discover converted skills through real OpenCode debug skill."""
    with tempfile.TemporaryDirectory(prefix="ai-config-shared-opencode-") as temporary:
        root = Path(temporary)
        home = root / "home"
        output = root / "project"
        home.mkdir()
        env = isolated_env(home)
        convert(TargetTool.OPENCODE, output)
        relative_roots = tuple(
            Path(f".opencode/skills/shared-includes-{name}") for name in ("alpha", "beta")
        )
        assert_materialized(output, relative_roots)

        result = subprocess.run(
            [opencode, "debug", "skill"],
            cwd=output,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"opencode debug skill failed ({result.returncode})\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        discovered: object = json.loads(result.stdout)
        if not isinstance(discovered, list):
            raise AssertionError(f"unexpected opencode debug skill output: {discovered!r}")
        names = {
            item.get("name")
            for item in discovered
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        expected = {"shared-includes-alpha", "shared-includes-beta"}
        if not expected.issubset(names):
            raise AssertionError(f"OpenCode did not discover converted skills: {discovered!r}")

    return {
        "result": "passed",
        "target": "opencode",
        "runtime": "real opencode debug skill",
        "skills": sorted(expected),
        "resources": [str(path) for path in RESOURCE_PATHS],
        "credentials": "ambient credentials removed",
    }


def probe_codex(codex: str) -> dict[str, object]:
    """Install and discover the converted package through Codex's auth-free lifecycle."""
    with tempfile.TemporaryDirectory(prefix="ai-config-shared-codex-") as temporary:
        root = Path(temporary)
        home = root / "home"
        codex_home = home / ".codex"
        output = root / "project"
        codex_home.mkdir(parents=True)
        (codex_home / "config.toml").write_text("")
        env = isolated_env(home)
        convert(TargetTool.CODEX, output)
        package_relative = Path(
            ".ai-config/codex/marketplaces/ai-config-shared-includes/plugins/shared-includes/skills"
        )
        relative_roots = tuple(package_relative / name for name in ("alpha", "beta"))
        assert_materialized(output, relative_roots)

        spec = codex_package_spec("shared-includes", "1.0.0", output)
        original_env = os.environ.copy()
        os.environ.clear()
        os.environ.update(env)
        try:
            sync_codex_packages(
                [spec],
                output_dir=output,
                refreshed_plugin_ids={spec.plugin_id},
            )
            installed = load_json(run(codex, ["plugin", "list", "--json"], env))["installed"]
            package = next(
                (item for item in installed if item.get("pluginId") == spec.plugin_id),
                None,
            )
            if package is None or package.get("enabled") is not True:
                raise AssertionError(
                    f"shared-includes package not installed and enabled: {installed}"
                )

            prompt = run(codex, ["-C", str(output), "debug", "prompt-input", "probe"], env).stdout
            for name in ("shared-includes:alpha", "shared-includes:beta"):
                if name not in prompt:
                    raise AssertionError(f"Codex did not discover {name!r}:\n{prompt}")

            manifests = list(
                (codex_home / "plugins/cache").glob(
                    "ai-config-shared-includes/shared-includes/*/.codex-plugin/plugin.json"
                )
            )
            if len(manifests) != 1:
                raise AssertionError(f"expected one installed shared-includes package: {manifests}")
            installed_root = manifests[0].parents[1]
            assert_materialized(
                installed_root,
                tuple(Path("skills") / name for name in ("alpha", "beta")),
            )
        finally:
            try:
                sync_codex_packages([], output_dir=output, refreshed_plugin_ids=set())
            finally:
                os.environ.clear()
                os.environ.update(original_env)

    return {
        "result": "passed",
        "target": "codex",
        "runtime": "real marketplace/package install and debug prompt-input discovery",
        "package": "shared-includes@ai-config-shared-includes",
        "skills": ["shared-includes:alpha", "shared-includes:beta"],
        "resources": [str(path) for path in RESOURCE_PATHS],
        "credentials": "ambient credentials removed",
    }


def probe_cursor() -> dict[str, object]:
    """Verify Cursor's accepted v1 file-shape proof without claiming runtime execution."""
    with tempfile.TemporaryDirectory(prefix="ai-config-shared-cursor-") as temporary:
        output = Path(temporary) / "project"
        convert(TargetTool.CURSOR, output)
        relative_roots = tuple(
            Path(f".cursor/skills/shared-includes-{name}") for name in ("alpha", "beta")
        )
        assert_materialized(output, relative_roots)
        failures = [
            result.message
            for result in CursorOutputValidator().validate_all(output)
            if result.status == "fail"
        ]
        if failures:
            raise AssertionError(f"Cursor output validation failed: {failures}")

    return {
        "result": "passed",
        "target": "cursor",
        "runtime": "not executed: accepted v1 proof is deterministic file shape and validator only",
        "skills": ["shared-includes-alpha", "shared-includes-beta"],
        "resources": [str(path) for path in RESOURCE_PATHS],
        "credentials": "no credentials used",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("pi", "opencode", "codex", "cursor"), required=True)
    parser.add_argument("--pi", default=shutil.which("pi"))
    parser.add_argument("--opencode", default=shutil.which("opencode"))
    parser.add_argument("--codex", default=shutil.which("codex"))
    args = parser.parse_args()

    if args.target == "pi":
        if not args.pi:
            raise SystemExit("pi executable not found")
        result = probe_pi(args.pi)
    elif args.target == "opencode":
        if not args.opencode:
            raise SystemExit("opencode executable not found")
        result = probe_opencode(args.opencode)
    elif args.target == "codex":
        if not args.codex:
            raise SystemExit("codex executable not found")
        result = probe_codex(args.codex)
    else:
        result = probe_cursor()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
