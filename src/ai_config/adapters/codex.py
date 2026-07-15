"""Subprocess adapter for the Codex plugin lifecycle CLI."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, cast


@dataclass(frozen=True)
class CodexCommandError(RuntimeError):
    """Actionable failure from one Codex lifecycle stage."""

    stage: str
    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    remediation: str

    def __str__(self) -> str:
        rendered = shlex.join(self.command)
        detail = self.stderr.strip() or self.stdout.strip() or "no command output"
        return (
            f"Codex plugin lifecycle failed at stage '{self.stage}': {rendered} "
            f"(exit {self.returncode}). {detail}. Remediation: {self.remediation}"
        )


class CodexCLI:
    """Thin JSON-oriented wrapper around the installed ``codex`` executable."""

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("codex") or "codex"

    def run_json(
        self,
        stage: str,
        args: list[str],
        *,
        remediation: str,
    ) -> dict[str, Any]:
        command = (self.executable, *args)
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            raise CodexCommandError(
                stage=stage,
                command=command,
                returncode=None,
                stdout="",
                stderr=str(error),
                remediation=remediation,
            ) from error
        if completed.returncode != 0:
            raise CodexCommandError(
                stage=stage,
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                remediation=remediation,
            )
        try:
            payload: object = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise CodexCommandError(
                stage=stage,
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=f"expected JSON output: {error}",
                remediation=remediation,
            ) from error
        if not isinstance(payload, dict):
            raise CodexCommandError(
                stage=stage,
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr="expected a JSON object",
                remediation=remediation,
            )
        return cast(dict[str, Any], payload)

    def list_marketplaces(self) -> list[dict[str, Any]]:
        payload = self.run_json(
            "list-marketplaces",
            ["plugin", "marketplace", "list", "--json"],
            remediation="Run `codex plugin marketplace list --json` and repair Codex config errors.",
        )
        value = payload.get("marketplaces")
        return (
            [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []
        )

    def add_marketplace(self, path: str) -> None:
        self.run_json(
            "add-marketplace",
            ["plugin", "marketplace", "add", path, "--json"],
            remediation="Validate the generated .agents/plugins/marketplace.json, then retry sync.",
        )

    def remove_marketplace(self, name: str) -> None:
        self.run_json(
            "remove-marketplace",
            ["plugin", "marketplace", "remove", name, "--json"],
            remediation="Inspect the named ai-config marketplace with Codex, then retry sync.",
        )

    def list_plugins(self) -> list[dict[str, Any]]:
        payload = self.run_json(
            "list-plugins",
            ["plugin", "list", "--json"],
            remediation="Run `codex plugin list --json` and repair Codex config errors.",
        )
        value = payload.get("installed")
        return (
            [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []
        )

    def add_plugin(self, plugin_id: str) -> None:
        self.run_json(
            "install-plugin",
            ["plugin", "add", plugin_id, "--json"],
            remediation="Confirm the generated marketplace is registered and the plugin is available, then retry sync.",
        )

    def remove_plugin(self, plugin_id: str) -> None:
        self.run_json(
            "remove-plugin",
            ["plugin", "remove", plugin_id, "--json"],
            remediation="Inspect the ai-config-owned plugin entry and cache with Codex, then retry sync.",
        )
