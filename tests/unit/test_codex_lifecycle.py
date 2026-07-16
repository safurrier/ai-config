"""Tests for declarative Codex package lifecycle ownership."""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import pytest

from ai_config.adapters.codex import (
    CodexCLI,
    CodexCommandError,
    CodexInstalledPlugin,
    CodexMarketplace,
    CodexPluginInstall,
)
from ai_config.codex_lifecycle import sync_codex_packages
from ai_config.converters.codex_package import CODEX_OWNERSHIP_FILE, codex_package_spec


class FakeCodexCLI:
    """Stateful typed fake exposing the lifecycle adapter protocol."""

    def __init__(
        self,
        *,
        marketplaces: list[CodexMarketplace] | None = None,
        plugins: list[CodexInstalledPlugin] | None = None,
        install_version: str = "1.0.0",
    ) -> None:
        self.marketplaces = marketplaces or []
        self.plugins = plugins or []
        self.install_version = install_version
        self.calls: list[tuple[str, ...]] = []

    def list_marketplaces(self) -> list[CodexMarketplace]:
        return self.marketplaces

    def list_plugins(self) -> list[CodexInstalledPlugin]:
        return self.plugins

    def add_marketplace(self, path: str, expected_name: str) -> CodexMarketplace:
        self.calls.append(("add_marketplace", path, expected_name))
        return CodexMarketplace(expected_name, Path(path).resolve())

    def remove_marketplace(self, name: str) -> None:
        self.calls.append(("remove_marketplace", name))

    def add_plugin(self, plugin_id: str) -> CodexPluginInstall:
        self.calls.append(("add_plugin", plugin_id))
        name, marketplace = plugin_id.split("@", 1)
        return CodexPluginInstall(
            plugin_id=plugin_id,
            name=name,
            marketplace_name=marketplace,
            version=self.install_version,
            installed_path=Path("/installed"),
        )

    def remove_plugin(self, plugin_id: str) -> None:
        self.calls.append(("remove_plugin", plugin_id))


def _package(
    tmp_path: Path,
    name: str = "demo",
    version: str = "1.0.0",
    *,
    source_plugin_id: str | None = None,
):
    spec = codex_package_spec(
        name,
        version,
        tmp_path,
        source_plugin_id=source_plugin_id,
    )
    manifest = spec.marketplace_path / ".agents/plugins/marketplace.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{}")
    return spec


def _marketplace(spec) -> CodexMarketplace:
    return CodexMarketplace(spec.marketplace_name, spec.marketplace_path)


def _installed(spec, *, enabled: bool = True, version: str | None = None) -> CodexInstalledPlugin:
    source = spec.marketplace_path / "plugins" / spec.plugin_name
    return CodexInstalledPlugin(
        plugin_id=spec.plugin_id,
        name=spec.plugin_name,
        marketplace_name=spec.marketplace_name,
        version=version or spec.version,
        enabled=enabled,
        source_path=source,
        marketplace_root=spec.marketplace_path,
    )


def _establish_ownership(spec, tmp_path: Path) -> None:
    sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids={spec.plugin_id},
        cli=FakeCodexCLI(install_version=spec.version),
    )


def test_first_sync_registers_and_installs(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    cli = FakeCodexCLI()

    actions = sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids={spec.plugin_id},
        cli=cli,
    )

    assert [action.action for action in actions] == [
        "register_codex_marketplace",
        "install_codex_plugin",
    ]
    assert cli.calls == [
        ("add_marketplace", str(spec.marketplace_path), spec.marketplace_name),
        ("add_plugin", spec.plugin_id),
    ]
    ownership = json.loads((tmp_path / CODEX_OWNERSHIP_FILE).read_text())
    assert set(ownership["packages"]) == {spec.plugin_id}


def test_unchanged_sync_reports_noop_with_reason(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    _establish_ownership(spec, tmp_path)
    cli = FakeCodexCLI(marketplaces=[_marketplace(spec)], plugins=[_installed(spec)])

    actions = sync_codex_packages([spec], output_dir=tmp_path, refreshed_plugin_ids=set(), cli=cli)

    assert [action.action for action in actions] == ["noop_codex_plugin"]
    assert "already match" in actions[0].reason
    assert cli.calls == []


def test_refresh_reinstalls_through_codex_cli(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    _establish_ownership(spec, tmp_path)
    cli = FakeCodexCLI(marketplaces=[_marketplace(spec)], plugins=[_installed(spec)])

    actions = sync_codex_packages(
        [spec], output_dir=tmp_path, refreshed_plugin_ids={spec.plugin_id}, cli=cli
    )

    assert [action.action for action in actions] == ["update_codex_plugin"]
    assert cli.calls == [("remove_plugin", spec.plugin_id), ("add_plugin", spec.plugin_id)]


def test_drifted_disabled_plugin_reports_reinstall(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    _establish_ownership(spec, tmp_path)
    cli = FakeCodexCLI(
        marketplaces=[_marketplace(spec)],
        plugins=[_installed(spec, enabled=False)],
    )

    actions = sync_codex_packages(
        [spec], output_dir=tmp_path, refreshed_plugin_ids=set(), dry_run=True, cli=cli
    )

    assert [action.action for action in actions] == ["reinstall_codex_plugin"]
    assert "disabled" in actions[0].reason
    assert cli.calls == []


def test_missing_runtime_state_reports_register_and_install(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    _establish_ownership(spec, tmp_path)

    actions = sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids=set(),
        dry_run=True,
        cli=FakeCodexCLI(),
    )

    assert [action.action for action in actions] == [
        "register_codex_marketplace",
        "install_codex_plugin",
    ]


def test_version_upgrade_reports_update_and_downgrade_fails_closed(tmp_path: Path) -> None:
    old = _package(tmp_path, version="1.0.0")
    _establish_ownership(old, tmp_path)
    upgraded = codex_package_spec("demo", "1.1.0", tmp_path)
    cli = FakeCodexCLI(
        marketplaces=[_marketplace(upgraded)],
        plugins=[_installed(upgraded, version="1.0.0")],
        install_version="1.1.0",
    )

    actions = sync_codex_packages(
        [upgraded], output_dir=tmp_path, refreshed_plugin_ids=set(), dry_run=True, cli=cli
    )
    assert [action.action for action in actions] == ["update_codex_plugin"]

    downgraded = codex_package_spec("demo", "0.9.0", tmp_path)
    with pytest.raises(ValueError, match="would downgrade"):
        sync_codex_packages(
            [downgraded],
            output_dir=tmp_path,
            refreshed_plugin_ids=set(),
            dry_run=True,
            cli=cli,
        )


def test_normalized_identity_collision_fails_before_cli(tmp_path: Path) -> None:
    first = _package(tmp_path, source_plugin_id="My Plugin@one")
    duplicate = codex_package_spec("demo", "1.0.0", tmp_path, source_plugin_id="demo@two")
    cli = FakeCodexCLI()

    with pytest.raises(ValueError, match="identity collision"):
        sync_codex_packages(
            [first, duplicate],
            output_dir=tmp_path,
            refreshed_plugin_ids=set(),
            cli=cli,
        )
    assert cli.calls == []


def test_removal_touches_only_owned_state(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    _establish_ownership(spec, tmp_path)
    unrelated = tmp_path / ".codex/config.toml"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text('model = "keep"\n')
    user_root = Path("/user/market").resolve()
    cli = FakeCodexCLI(
        marketplaces=[_marketplace(spec), CodexMarketplace("user-market", user_root)],
        plugins=[
            _installed(spec),
            CodexInstalledPlugin(
                plugin_id="user@user-market",
                name="user",
                marketplace_name="user-market",
                version="1.0.0",
                enabled=False,
                source_path=user_root / "plugins/user",
                marketplace_root=user_root,
            ),
        ],
    )

    actions = sync_codex_packages([], output_dir=tmp_path, refreshed_plugin_ids=set(), cli=cli)

    assert [action.action for action in actions] == [
        "remove_codex_plugin",
        "remove_codex_marketplace",
    ]
    assert cli.calls == [
        ("remove_plugin", spec.plugin_id),
        ("remove_marketplace", spec.marketplace_name),
    ]
    assert unrelated.read_text() == 'model = "keep"\n'


@pytest.mark.parametrize("root", [Path("/unrelated"), Path("/unknown")])
def test_marketplace_name_collision_fails_closed(tmp_path: Path, root: Path) -> None:
    spec = _package(tmp_path)
    cli = FakeCodexCLI(marketplaces=[CodexMarketplace(spec.marketplace_name, root)])
    with pytest.raises(ValueError, match="will not modify"):
        sync_codex_packages(
            [spec], output_dir=tmp_path, refreshed_plugin_ids={spec.plugin_id}, cli=cli
        )
    assert cli.calls == []


def test_ambiguous_ownership_json_fails_before_cli(tmp_path: Path) -> None:
    ownership = tmp_path / CODEX_OWNERSHIP_FILE
    ownership.parent.mkdir(parents=True)
    ownership.write_text(
        '{"version":1,"packages":{"demo@ai-config-demo":'
        '{"marketplace_name":"ai-config-demo","marketplace_path":"/tmp/ai-config-demo",'
        '"version":"1.0.0"},"demo@ai-config-demo":'
        '{"marketplace_name":"ai-config-demo","marketplace_path":"/tmp/ai-config-demo",'
        '"version":"1.0.0"}}}'
    )
    cli = FakeCodexCLI()

    with pytest.raises(ValueError, match="duplicate key"):
        sync_codex_packages([], output_dir=tmp_path, refreshed_plugin_ids=set(), cli=cli)
    assert cli.calls == []


def test_invalid_semver_fails_at_package_boundary(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Semantic Versioning"):
        codex_package_spec("demo", "1.0", tmp_path)


def test_cli_list_schema_rejects_partial_duplicate_and_inconsistent_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = CodexCLI("/bin/codex")
    monkeypatch.setattr(cli, "_ensure_supported_version", lambda: "0.144.5")

    monkeypatch.setattr(cli, "run_json", lambda *args, **kwargs: {"installed": []})
    with pytest.raises(CodexCommandError, match="installed and available"):
        cli.list_plugins()

    duplicate = {
        "installed": [
            {
                "pluginId": "demo@market",
                "name": "demo",
                "marketplaceName": "market",
                "version": "1.0.0",
                "installed": True,
                "enabled": True,
                "source": {"source": "local", "path": "/market/plugins/demo"},
                "marketplaceSource": {"sourceType": "local", "source": "/market"},
                "installPolicy": "AVAILABLE",
                "authPolicy": "ON_INSTALL",
            }
        ]
        * 2,
        "available": [],
    }
    monkeypatch.setattr(cli, "run_json", lambda *args, **kwargs: duplicate)
    with pytest.raises(CodexCommandError, match="duplicate installed plugin"):
        cli.list_plugins()

    duplicate["installed"] = [{**duplicate["installed"][0], "pluginId": "wrong@market"}]
    monkeypatch.setattr(cli, "run_json", lambda *args, **kwargs: duplicate)
    with pytest.raises(CodexCommandError, match="identity fields disagree"):
        cli.list_plugins()


def test_cli_preserves_typed_nonlocal_unrelated_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Documented Git/remote rows are validated without being mistaken for owned local state."""
    cli = CodexCLI("/bin/codex")
    monkeypatch.setattr(cli, "_ensure_supported_version", lambda: "0.144.5")
    responses = iter(
        [
            {
                "marketplaces": [
                    {
                        "name": "git-market",
                        "root": "/cache/git-market",
                        "marketplaceSource": {
                            "sourceType": "git",
                            "source": "https://example.test/market.git",
                        },
                    }
                ]
            },
            {
                "installed": [
                    {
                        "pluginId": "remote-plugin@git-market",
                        "name": "remote-plugin",
                        "marketplaceName": "git-market",
                        "version": "2.0.0",
                        "installed": True,
                        "enabled": False,
                        "source": {
                            "source": "git",
                            "url": "https://example.test/plugin.git",
                        },
                        "marketplaceSource": {
                            "sourceType": "git",
                            "source": "https://example.test/market.git",
                        },
                        "installPolicy": "AVAILABLE",
                        "authPolicy": "ON_INSTALL",
                    }
                ],
                "available": [],
            },
        ]
    )
    monkeypatch.setattr(cli, "run_json", lambda *args, **kwargs: next(responses))

    assert cli.list_marketplaces()[0].name == "git-market"
    installed = cli.list_plugins()[0]
    assert installed.plugin_id == "remote-plugin@git-market"
    assert installed.source_path is None
    assert installed.marketplace_root is None


@pytest.mark.parametrize(
    "payload",
    [
        {"installed": [], "available": []},
        {"marketplaces": [{"name": "demo"}]},
    ],
)
def test_cli_marketplace_list_schema_rejects_wrong_shape(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    cli = CodexCLI("/bin/codex")
    monkeypatch.setattr(cli, "_ensure_supported_version", lambda: "0.144.5")
    monkeypatch.setattr(cli, "run_json", lambda *args, **kwargs: payload)

    with pytest.raises(CodexCommandError, match="invalid Codex 0.144.x JSON response"):
        cli.list_marketplaces()


def test_cli_json_rejects_malformed_and_duplicate_keys(tmp_path: Path) -> None:
    for index, payload in enumerate(('{"marketplaces":', '{"marketplaces":[],"marketplaces":[]}')):
        executable = tmp_path / f"codex-json-{index}"
        executable.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "--version" ]; then echo \'codex-cli 0.144.5\'; exit 0; fi\n'
            f"printf '%s' '{payload}'\n"
        )
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        with pytest.raises(CodexCommandError, match="unambiguous JSON"):
            CodexCLI(str(executable)).list_marketplaces()


def test_cli_mutation_schema_rejects_semantically_wrong_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = CodexCLI("/bin/codex")
    monkeypatch.setattr(cli, "_ensure_supported_version", lambda: "0.144.5")
    monkeypatch.setattr(
        cli,
        "run_json",
        lambda *args, **kwargs: {
            "pluginId": "other@market",
            "name": "other",
            "marketplaceName": "market",
            "version": "unknown",
            "installedPath": "/tmp/plugin",
            "authPolicy": "ON_INSTALL",
        },
    )
    with pytest.raises(CodexCommandError, match="did not match"):
        cli.add_plugin("demo@market")

    monkeypatch.setattr(
        cli,
        "run_json",
        lambda *args, **kwargs: {
            "pluginId": "demo@market",
            "name": "demo",
            "marketplaceName": "market",
            "version": "unknown",
            "installedPath": "/tmp/plugin",
            "authPolicy": "ON_INSTALL",
        },
    )
    with pytest.raises(CodexCommandError, match="Semantic Versioning"):
        cli.add_plugin("demo@market")

    monkeypatch.setattr(
        cli,
        "run_json",
        lambda *args, **kwargs: {
            "pluginId": "other@market",
            "name": "other",
            "marketplaceName": "market",
        },
    )
    with pytest.raises(CodexCommandError, match="did not confirm removal"):
        cli.remove_plugin("demo@market")


def test_cli_unknown_version_fails_closed(tmp_path: Path) -> None:
    executable = tmp_path / "codex-version"
    executable.write_text("#!/bin/sh\necho 'codex-cli 0.145.0'\n")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    with pytest.raises(CodexCommandError, match="unsupported Codex CLI response contract"):
        CodexCLI(str(executable)).list_marketplaces()


def test_cli_failure_sanitizes_and_bounds_output(tmp_path: Path) -> None:
    executable = tmp_path / "codex-fail"
    executable.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo \'codex-cli 0.144.5\'; exit 0; fi\n'
        "printf '\\033[31mbroken\\033[0m\\000' >&2\n"
        "exit 7\n"
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    with pytest.raises(CodexCommandError) as caught:
        CodexCLI(str(executable)).list_marketplaces()
    message = str(caught.value)
    assert "stage 'list-marketplaces'" in message
    assert "\x1b" not in message
    assert "broken" in message
    assert "Remediation:" in message


@pytest.mark.skipif(os.name != "posix", reason="process-group descendant test requires POSIX")
def test_cli_timeout_kills_forked_descendant(tmp_path: Path) -> None:
    marker = tmp_path / "descendant-survived"
    executable = tmp_path / "codex-timeout.py"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import subprocess, sys, time\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('codex-cli 0.144.5')\n"
        "    raise SystemExit(0)\n"
        f"subprocess.Popen([sys.executable, '-c', \"import time; time.sleep(0.8); open({str(marker)!r}, 'w').write('alive')\"])\n"
        "time.sleep(30)\n"
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    with pytest.raises(CodexCommandError, match="timed out"):
        CodexCLI(str(executable), timeout_seconds=0.2).list_marketplaces()
    time.sleep(1.0)
    assert not marker.exists()
