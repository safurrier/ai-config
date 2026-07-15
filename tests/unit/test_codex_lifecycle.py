"""Tests for declarative Codex package lifecycle ownership."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_config.adapters.codex import CodexCLI, CodexCommandError
from ai_config.codex_lifecycle import sync_codex_packages
from ai_config.converters.codex_package import CODEX_OWNERSHIP_FILE, codex_package_spec


class FakeCodexCLI:
    """Stateful fake exposing only the lifecycle adapter protocol."""

    def __init__(
        self,
        *,
        marketplaces: list[dict] | None = None,
        plugins: list[dict] | None = None,
    ) -> None:
        self.marketplaces = marketplaces or []
        self.plugins = plugins or []
        self.calls: list[tuple[str, str]] = []

    def list_marketplaces(self) -> list[dict]:
        return self.marketplaces

    def list_plugins(self) -> list[dict]:
        return self.plugins

    def add_marketplace(self, path: str) -> None:
        self.calls.append(("add_marketplace", path))

    def remove_marketplace(self, name: str) -> None:
        self.calls.append(("remove_marketplace", name))

    def add_plugin(self, plugin_id: str) -> None:
        self.calls.append(("add_plugin", plugin_id))

    def remove_plugin(self, plugin_id: str) -> None:
        self.calls.append(("remove_plugin", plugin_id))


def _package(tmp_path: Path, name: str = "demo"):
    spec = codex_package_spec(name, "1.0.0", tmp_path)
    manifest = spec.marketplace_path / ".agents/plugins/marketplace.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}")
    return spec


def test_first_sync_registers_and_installs(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    cli = FakeCodexCLI()

    actions = sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids={spec.plugin_id},
        cli=cli,  # type: ignore[arg-type]
    )

    assert [action.action for action in actions] == [
        "register_codex_marketplace",
        "install_codex_plugin",
    ]
    assert cli.calls == [
        ("add_marketplace", str(spec.marketplace_path)),
        ("add_plugin", spec.plugin_id),
    ]
    ownership = json.loads((tmp_path / CODEX_OWNERSHIP_FILE).read_text())
    assert set(ownership["packages"]) == {spec.plugin_id}


def test_unchanged_sync_is_idempotent(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    first = FakeCodexCLI()
    sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids={spec.plugin_id},
        cli=first,  # type: ignore[arg-type]
    )
    cli = FakeCodexCLI(
        marketplaces=[{"name": spec.marketplace_name, "root": str(spec.marketplace_path)}],
        plugins=[{"pluginId": spec.plugin_id, "enabled": True}],
    )

    actions = sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids=set(),
        cli=cli,  # type: ignore[arg-type]
    )

    assert actions == []
    assert cli.calls == []


def test_refresh_reinstalls_through_codex_cli(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids={spec.plugin_id},
        cli=FakeCodexCLI(),  # type: ignore[arg-type]
    )
    cli = FakeCodexCLI(
        marketplaces=[{"name": spec.marketplace_name, "root": str(spec.marketplace_path)}],
        plugins=[{"pluginId": spec.plugin_id, "enabled": True}],
    )

    actions = sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids={spec.plugin_id},
        cli=cli,  # type: ignore[arg-type]
    )

    assert [action.action for action in actions] == ["update_codex_plugin"]
    assert cli.calls == [
        ("remove_plugin", spec.plugin_id),
        ("add_plugin", spec.plugin_id),
    ]


def test_removal_touches_only_owned_state(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids={spec.plugin_id},
        cli=FakeCodexCLI(),  # type: ignore[arg-type]
    )
    unrelated = tmp_path / ".codex/config.toml"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text('model = "keep"\n')
    cli = FakeCodexCLI(
        marketplaces=[
            {"name": spec.marketplace_name, "root": str(spec.marketplace_path)},
            {"name": "user-market", "root": "/user/market"},
        ],
        plugins=[
            {"pluginId": spec.plugin_id, "enabled": True},
            {"pluginId": "user@user-market", "enabled": False},
        ],
    )

    actions = sync_codex_packages(
        [],
        output_dir=tmp_path,
        refreshed_plugin_ids=set(),
        cli=cli,  # type: ignore[arg-type]
    )

    assert [action.action for action in actions] == [
        "remove_codex_plugin",
        "remove_codex_marketplace",
    ]
    assert cli.calls == [
        ("remove_plugin", spec.plugin_id),
        ("remove_marketplace", spec.marketplace_name),
    ]
    assert unrelated.read_text() == 'model = "keep"\n'


@pytest.mark.parametrize("marketplace", [{"root": "/unrelated"}, {}])
def test_marketplace_name_collision_fails_closed(
    tmp_path: Path, marketplace: dict[str, str]
) -> None:
    spec = _package(tmp_path)
    cli = FakeCodexCLI(
        marketplaces=[{"name": spec.marketplace_name, **marketplace}],
    )
    with pytest.raises(ValueError, match="will not modify"):
        sync_codex_packages(
            [spec],
            output_dir=tmp_path,
            refreshed_plugin_ids={spec.plugin_id},
            cli=cli,  # type: ignore[arg-type]
        )
    assert cli.calls == []


def test_removal_fails_closed_if_owned_marketplace_was_replaced(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids={spec.plugin_id},
        cli=FakeCodexCLI(),  # type: ignore[arg-type]
    )
    cli = FakeCodexCLI(
        marketplaces=[{"name": spec.marketplace_name, "root": "/unrelated"}],
        plugins=[{"pluginId": spec.plugin_id, "enabled": True}],
    )

    with pytest.raises(ValueError, match="will not remove"):
        sync_codex_packages(
            [],
            output_dir=tmp_path,
            refreshed_plugin_ids=set(),
            cli=cli,  # type: ignore[arg-type]
        )

    assert cli.calls == []


def test_dry_run_plans_without_calling_codex(tmp_path: Path) -> None:
    spec = _package(tmp_path)
    actions = sync_codex_packages(
        [spec],
        output_dir=tmp_path,
        refreshed_plugin_ids={spec.plugin_id},
        dry_run=True,
        cli=FakeCodexCLI(),  # type: ignore[arg-type]
    )
    assert len(actions) == 2
    assert not (tmp_path / CODEX_OWNERSHIP_FILE).exists()


def test_cli_failure_names_stage_command_and_remediation() -> None:
    completed = subprocess.CompletedProcess(
        args=["codex"],
        returncode=7,
        stdout="",
        stderr="broken config",
    )
    with patch("ai_config.adapters.codex.subprocess.run", return_value=completed):
        with pytest.raises(CodexCommandError) as caught:
            CodexCLI("/bin/codex").add_plugin("demo@ai-config-demo")
    message = str(caught.value)
    assert "stage 'install-plugin'" in message
    assert "/bin/codex plugin add demo@ai-config-demo --json" in message
    assert "Remediation:" in message
