#!/usr/bin/env python3
"""Probe Claude validation and native loading of ai-config include metadata."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def run(command: list[str]) -> None:
    print("$ " + " ".join(command))
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    print(completed.stdout, end="")
    print(completed.stderr, end="")
    print(f"exit={completed.returncode}")
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    claude = shutil.which("claude")
    if claude is None:
        raise SystemExit("claude is required for this compatibility probe")
    with tempfile.TemporaryDirectory(prefix="ai-config-include-probe-") as temporary:
        plugin = Path(temporary)
        (plugin / ".claude-plugin").mkdir()
        (plugin / "skills/one").mkdir(parents=True)
        (plugin / "shared").mkdir()
        (plugin / ".claude-plugin/plugin.json").write_text(
            json.dumps(
                {
                    "name": "include-probe",
                    "version": "1.0.0",
                    "description": "Validate ai-config include metadata",
                    "author": {"name": "ai-config probe"},
                    "skills": "./skills",
                }
            )
        )
        (plugin / "shared/data.txt").write_text("shared payload\n")
        (plugin / "skills/one/SKILL.md").write_text(
            "---\n"
            "name: one\n"
            "description: Probe exact skill include metadata\n"
            "x-ai-config-includes:\n"
            "  - shared/data.txt\n"
            "---\n\n"
            "Read `${CLAUDE_PLUGIN_ROOT}/shared/data.txt`.\n"
        )
        run([claude, "plugin", "validate", "--strict", str(plugin)])
        run([claude, "--plugin-dir", str(plugin), "plugin", "details", "include-probe"])


if __name__ == "__main__":
    main()
