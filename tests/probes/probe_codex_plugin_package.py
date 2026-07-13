#!/usr/bin/env python3
"""Probe the experimental Codex plugin fixture without using live config or credentials."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

PLUGIN_ID = "experimental-package@ai-config-experimental"
MARKETPLACE_NAME = "ai-config-experimental"
SKILL_MARKER = "experimental-package:hello"
SENSITIVE_ENV_VARS = {
    "CHATGPT_API_KEY",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_ORG_ID",
    "OPENAI_PROJECT_ID",
}


def run_codex(
    codex: str,
    args: list[str],
    env: dict[str, str],
    *,
    expected_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    """Run one isolated Codex command and fail with its captured output."""
    result = subprocess.run(
        [codex, *args],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )
    if result.returncode not in expected_codes:
        command = " ".join([codex, *args])
        raise RuntimeError(
            f"command failed ({result.returncode}): {command}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def load_json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    """Parse a JSON object from a successful Codex command."""
    payload: object = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise AssertionError("expected a JSON object from Codex")
    return cast(dict[str, object], payload)


def object_field_equals(value: object, key: str, expected: object) -> bool:
    """Return whether a JSON object contains the expected field value."""
    if not isinstance(value, dict):
        return False
    return cast(dict[str, object], value).get(key) == expected


def installed_plugin(payload: dict[str, object]) -> dict[str, object]:
    """Return the probe plugin entry from a plugin-list response."""
    installed = payload.get("installed")
    if not isinstance(installed, list):
        raise AssertionError("plugin list did not contain an installed array")
    for entry in installed:
        if object_field_equals(entry, "pluginId", PLUGIN_ID):
            return cast(dict[str, object], entry)
    raise AssertionError(f"{PLUGIN_ID} was not listed as installed")


def set_plugin_enabled(config_path: Path, enabled: bool) -> None:
    """Toggle only the probe plugin in the temporary Codex config."""
    old = f'[plugins."{PLUGIN_ID}"]\nenabled = {str(not enabled).lower()}'
    new = f'[plugins."{PLUGIN_ID}"]\nenabled = {str(enabled).lower()}'
    config = config_path.read_text(encoding="utf-8")
    if config.count(old) != 1:
        raise AssertionError("temporary config did not contain the expected plugin toggle")
    config_path.write_text(config.replace(old, new), encoding="utf-8")


def probe(codex: str, fixture_root: Path) -> dict[str, str]:
    """Exercise marketplace and plugin lifecycle in disposable HOME directories."""
    if not (fixture_root / ".agents/plugins/marketplace.json").is_file():
        raise FileNotFoundError(f"invalid marketplace fixture: {fixture_root}")

    with tempfile.TemporaryDirectory(prefix="ai-config-codex-plugin-") as tmp:
        temp_root = Path(tmp)
        home = temp_root / "home"
        codex_home = home / ".codex"
        codex_home.mkdir(parents=True)

        env = {key: value for key, value in os.environ.items() if key not in SENSITIVE_ENV_VARS}
        env.update({"HOME": str(home), "CODEX_HOME": str(codex_home)})

        version = run_codex(codex, ["--version"], env).stdout.strip()
        features = run_codex(codex, ["features", "list"], env).stdout
        for expected in (
            "hooks                                stable             true",
            "plugin_sharing                       stable             true",
            "plugins                              stable             true",
            "remote_plugin                        under development  false",
        ):
            if expected not in features:
                raise AssertionError(f"missing expected feature row: {expected}")

        plugin_help = run_codex(codex, ["plugin", "--help"], env).stdout
        if "validate" in plugin_help:
            raise AssertionError("update the probe: Codex now exposes plugin validation")

        initial_marketplaces = load_json(
            run_codex(codex, ["plugin", "marketplace", "list", "--json"], env)
        )
        if initial_marketplaces != {"marketplaces": []}:
            raise AssertionError("temporary Codex home was not empty")

        added = load_json(
            run_codex(
                codex,
                ["plugin", "marketplace", "add", str(fixture_root), "--json"],
                env,
            )
        )
        if added.get("marketplaceName") != MARKETPLACE_NAME:
            raise AssertionError("Codex added an unexpected marketplace")

        marketplaces = load_json(run_codex(codex, ["plugin", "marketplace", "list", "--json"], env))
        listed_marketplaces = marketplaces.get("marketplaces")
        if not isinstance(listed_marketplaces, list) or not any(
            object_field_equals(entry, "name", MARKETPLACE_NAME) for entry in listed_marketplaces
        ):
            raise AssertionError("added marketplace was not listed")

        available = load_json(
            run_codex(codex, ["plugin", "list", "--available", "--json"], env)
        ).get("available")
        if not isinstance(available, list) or not any(
            object_field_equals(entry, "pluginId", PLUGIN_ID) for entry in available
        ):
            raise AssertionError("fixture plugin was not available")

        install = load_json(run_codex(codex, ["plugin", "add", PLUGIN_ID, "--json"], env))
        install_path_value = install.get("installedPath")
        if not isinstance(install_path_value, str):
            raise AssertionError("install result omitted installedPath")
        install_path = Path(install_path_value)
        expected_files = (
            ".codex-plugin/plugin.json",
            "skills/hello/SKILL.md",
            "hooks/hooks.json",
        )
        for relative_path in expected_files:
            if not (install_path / relative_path).is_file():
                raise AssertionError(f"installed cache omitted {relative_path}")

        config_path = codex_home / "config.toml"
        with config_path.open("rb") as config_file:
            config = tomllib.load(config_file)
        plugins_config = config.get("plugins")
        if not isinstance(plugins_config, dict):
            raise AssertionError("install did not create a plugins config table")
        plugin_config = plugins_config.get(PLUGIN_ID)
        if not isinstance(plugin_config, dict) or plugin_config.get("enabled") is not True:
            raise AssertionError("install did not enable the plugin in config.toml")

        listed = load_json(run_codex(codex, ["plugin", "list", "--json"], env))
        if installed_plugin(listed).get("enabled") is not True:
            raise AssertionError("installed plugin was not enabled")

        prompt = run_codex(
            codex,
            ["-C", str(fixture_root), "debug", "prompt-input", "probe"],
            env,
        ).stdout
        if SKILL_MARKER not in prompt:
            raise AssertionError("enabled plugin skill was not discovered")

        set_plugin_enabled(config_path, False)
        disabled = load_json(run_codex(codex, ["plugin", "list", "--json"], env))
        if installed_plugin(disabled).get("enabled") is not False:
            raise AssertionError("disabled plugin was still reported as enabled")
        disabled_prompt = run_codex(
            codex,
            ["-C", str(fixture_root), "debug", "prompt-input", "probe"],
            env,
        ).stdout
        if SKILL_MARKER in disabled_prompt:
            raise AssertionError("disabled plugin skill was still discovered")

        set_plugin_enabled(config_path, True)
        enabled_prompt = run_codex(
            codex,
            ["-C", str(fixture_root), "debug", "prompt-input", "probe"],
            env,
        ).stdout
        if SKILL_MARKER not in enabled_prompt:
            raise AssertionError("re-enabled plugin skill was not discovered")

        strict_plugin = run_codex(
            codex,
            ["--strict-config", "plugin", "list", "--json"],
            env,
            expected_codes=(1,),
        )
        if "not supported for `codex plugin`" not in strict_plugin.stderr:
            raise AssertionError("strict-config behavior for plugin commands changed")

        doctor = load_json(
            run_codex(
                codex,
                ["--strict-config", "doctor", "--json"],
                env,
                expected_codes=(0, 1),
            )
        )
        checks = doctor.get("checks")
        checks_by_name = cast(dict[str, object], checks) if isinstance(checks, dict) else {}
        config_check = checks_by_name.get("config.load")
        if not object_field_equals(config_check, "status", "ok"):
            raise AssertionError("strict Codex doctor did not load the generated config")

        run_codex(codex, ["plugin", "remove", PLUGIN_ID, "--json"], env)
        after_remove = load_json(run_codex(codex, ["plugin", "list", "--json"], env))
        if after_remove.get("installed") != [] or install_path.exists():
            raise AssertionError("plugin removal left the installed plugin or cache version")

        run_codex(
            codex,
            ["plugin", "marketplace", "remove", MARKETPLACE_NAME, "--json"],
            env,
        )
        final_marketplaces = load_json(
            run_codex(codex, ["plugin", "marketplace", "list", "--json"], env)
        )
        if final_marketplaces != {"marketplaces": []}:
            raise AssertionError("marketplace removal left configured state")

    return {
        "codex": codex,
        "version": version,
        "fixture": str(fixture_root),
        "result": "passed",
    }


def main() -> None:
    """Run the probe and print a small machine-readable result."""
    fixture_root = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "experimental"
        / "codex-plugin-marketplace"
    )
    codex = shutil.which("codex")
    if codex is None:
        raise SystemExit("codex executable not found")
    result = probe(codex, fixture_root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
