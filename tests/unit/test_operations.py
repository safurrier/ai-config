"""Tests for ai_config.operations module."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest

from ai_config.adapters.claude import CommandResult, InstalledMarketplace, InstalledPlugin
from ai_config.codex_lifecycle import (
    CodexLifecycleAction,
    CodexLifecycleExecutionError,
)
from ai_config.converters.codex_package import codex_package_spec
from ai_config.converters.ir import Diagnostic, PluginIdentity, Severity, TargetTool
from ai_config.converters.report import ConversionReport
from ai_config.operations import (
    get_status,
    sync_config,
    sync_discrepancies,
    sync_target,
    update_plugins,
    verify_sync,
)
from ai_config.pi_ownership import PiDesiredFile, apply_pi_reconciliation, load_pi_ownership
from ai_config.sync_state import (
    _CONVERSION_CACHE_VERSION,
)
from ai_config.sync_state import (
    compute_owned_codex_hash as _compute_owned_codex_hash,
)
from ai_config.sync_state import (
    conversion_signature as _conversion_signature,
)
from ai_config.sync_state import (
    load_conversion_cache as _load_conversion_cache,
)
from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    ConversionConfig,
    MarketplaceConfig,
    PluginConfig,
    PluginSource,
    SyncAction,
    SyncResult,
    TargetConfig,
)


class RuntimeObservationRecorder:
    """Record fresh-cache and runtime-observation call ordering."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def clear_cache(self) -> CommandResult:
        self.calls.append("clear")
        return CommandResult(success=True, stdout="", stderr="", returncode=0)

    def marketplaces(self) -> tuple[list[InstalledMarketplace], list[str]]:
        self.calls.append("marketplaces")
        return [], []

    def plugins(self) -> tuple[list[InstalledPlugin], list[str]]:
        self.calls.append("plugins")
        return [], []


@pytest.fixture(autouse=True)
def isolate_codex_lifecycle():
    """Operations tests do not invoke the real Codex binary."""
    with patch("ai_config.sync_conversion.sync_codex_packages", return_value=[]) as lifecycle:
        yield lifecycle


@pytest.fixture
def sample_config() -> AIConfig:
    """Sample config with one marketplace and two plugins."""
    marketplace = MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
    plugin1 = PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True)
    plugin2 = PluginConfig(id="plugin2@my-marketplace", scope="project", enabled=False)
    target_config = ClaudeTargetConfig(
        marketplaces={"my-marketplace": marketplace},
        plugins=(plugin1, plugin2),
    )
    target = TargetConfig(type="claude", config=target_config)
    return AIConfig(version=1, targets=(target,))


@pytest.fixture
def mock_installed_plugins(tmp_path: Path) -> list[InstalledPlugin]:
    """Mock installed plugins backed by a valid local source package."""
    plugin_path = tmp_path / "plugin1"
    (plugin_path / ".claude-plugin").mkdir(parents=True)
    (plugin_path / ".claude-plugin/plugin.json").write_text('{"name":"plugin1","version":"1.0.0"}')
    return [
        InstalledPlugin(
            id="plugin1@my-marketplace",
            version="1.0.0",
            scope="user",
            enabled=True,
            install_path=str(plugin_path),
        ),
    ]


@pytest.fixture
def mock_installed_marketplaces() -> list[InstalledMarketplace]:
    """Mock installed marketplaces."""
    return [
        InstalledMarketplace(
            name="my-marketplace",
            source=PluginSource.GITHUB,
            repo="owner/repo",
            install_location="/path/to/marketplace",
        ),
    ]


@pytest.mark.parametrize(
    ("scope", "root_suffix", "skill_path", "prompt_path", "extension_path"),
    [
        (
            "user",
            "home",
            ".pi/agent/skills/dev-tools-nested-skill/SKILL.md",
            ".pi/agent/prompts/dev-tools-commit.md",
            ".pi/agent/extensions/dev-tools-hooks.ts",
        ),
        (
            "project",
            "project",
            ".pi/skills/dev-tools-nested-skill/SKILL.md",
            ".pi/prompts/dev-tools-commit.md",
            ".pi/extensions/dev-tools-hooks.ts",
        ),
    ],
)
def test_pi_sync_target_reconciles_real_emitter_output_at_each_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scope: Literal["user", "project"],
    root_suffix: str,
    skill_path: str,
    prompt_path: str,
    extension_path: str,
) -> None:
    """Exercise Pi ownership through sync_target using a complete Claude plugin fixture."""
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures/sample-plugins/complete-plugin", source)
    root = tmp_path / root_suffix
    native_relative = Path("prompts/native.md")
    native_source = source / "targets/pi" / native_relative
    native_source.parent.mkdir(parents=True)
    native_source.write_text("native Pi prompt")
    monkeypatch.setattr(Path, "home", lambda: root)
    target = TargetConfig(
        type="claude",
        config=ClaudeTargetConfig(
            plugins=(PluginConfig(id="dev-tools@local", scope=scope, enabled=True),),
            conversion=ConversionConfig(targets=("pi",), scope=scope, output_dir=str(root)),
        ),
    )
    installed = [InstalledPlugin("dev-tools@local", "1", scope, True, str(source))]
    with (
        patch("ai_config.operations.claude.list_installed_plugins", return_value=(installed, [])),
        patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
    ):
        result = sync_target(target)
        repeat = sync_target(target)

    assert result.success, result.errors
    assert {action.action for action in result.actions_taken} == {"create_pi_output"}
    reference_path = skill_path.replace("SKILL.md", "resources/reference.md")
    native_output = (
        Path(".pi/agent") / native_relative if scope == "user" else Path(".pi") / native_relative
    )
    expected = {
        Path(skill_path),
        Path(reference_path),
        Path(prompt_path),
        Path(extension_path),
        native_output,
    }
    ledger = load_pi_ownership(root)
    assert expected <= set(ledger)
    for relative in expected:
        owned = ledger[relative]
        output = root / relative
        assert output.is_file()
        assert owned.source_plugin == "dev-tools@local"
        assert owned.relative_path == relative
        assert owned.digest == hashlib.sha256(output.read_bytes()).hexdigest()
        assert owned.executable is bool(output.stat().st_mode & 0o111)
    assert {action.action for action in repeat.actions_taken} == {"noop_pi_output"}


def test_pi_sync_config_removes_renamed_and_disabled_fixture_components(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A real emitter refresh removes obsolete owned paths even while directories remain."""
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures/sample-plugins/complete-plugin", source)
    output = tmp_path / "output"
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    enabled = PluginConfig(id="dev-tools@local", scope="project", enabled=True)
    config = AIConfig(
        version=1,
        targets=(
            TargetConfig(
                type="claude",
                config=ClaudeTargetConfig(
                    plugins=(enabled,),
                    conversion=ConversionConfig(
                        targets=("pi",), scope="project", output_dir=str(output)
                    ),
                ),
            ),
        ),
    )
    installed = [InstalledPlugin("dev-tools@local", "1", "project", True, str(source))]
    with (
        patch("ai_config.operations.claude.list_installed_plugins", return_value=(installed, [])),
        patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
        patch(
            "ai_config.operations.claude.disable_plugin",
            return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
        ),
    ):
        assert sync_config(config)["claude"].success
        old_prompt = output / ".pi/prompts/dev-tools-commit.md"
        old_reference = output / ".pi/skills/dev-tools-nested-skill/resources/reference.md"
        stale = old_reference.parent / "manual.txt"
        stale.write_text("unowned")
        (source / "commands/commit.md").rename(source / "commands/renamed.md")
        (source / "skills/category/nested-skill/resources/reference.md").unlink()
        refreshed = sync_config(config)["claude"]
        assert refreshed.success, refreshed.errors
        assert not old_prompt.exists()
        assert not old_reference.exists()
        assert stale.read_text() == "unowned"
        assert (output / ".pi/prompts/dev-tools-renamed.md").is_file()
        assert any(action.action == "remove_pi_output" for action in refreshed.actions_taken)
        disabled = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(
                            PluginConfig(id="dev-tools@local", scope="project", enabled=False),
                        ),
                        conversion=ConversionConfig(
                            targets=("pi",), scope="project", output_dir=str(output)
                        ),
                    ),
                ),
            ),
        )
        removed = sync_config(disabled)["claude"]

    assert removed.success, removed.errors
    assert not load_pi_ownership(output)
    assert stale.exists()
    # The removed reference's parent is deliberately retained only because it has user content.
    assert old_reference.parent.exists()


def test_pi_target_and_plugin_removal_retire_cached_root_after_reconciliation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Pi root tracking survives until its owned files are safely reconciled away."""
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures/sample-plugins/complete-plugin", source)
    home, output = tmp_path / "home", tmp_path / "output"
    monkeypatch.setattr(Path, "home", lambda: home)
    installed = [InstalledPlugin("dev-tools@local", "1", "project", True, str(source))]

    def config(targets: tuple[str, ...], plugins: tuple[PluginConfig, ...]) -> TargetConfig:
        return TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(
                plugins=plugins,
                conversion=ConversionConfig(
                    targets=targets, scope="project", output_dir=str(output)
                ),
            ),
        )

    enabled = PluginConfig(id="dev-tools@local", scope="project", enabled=True)
    with (
        patch("ai_config.operations.claude.list_installed_plugins", return_value=(installed, [])),
        patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
    ):
        assert sync_target(config(("pi", "cursor"), (enabled,))).success
        cache_path = home / ".ai-config/cache/conversion-hashes.json"
        assert str(output.resolve()) in json.loads(cache_path.read_text())["pi_output_dirs"]
        removed_target = sync_target(config(("cursor",), (enabled,)))
        assert removed_target.success, removed_target.errors
        assert not load_pi_ownership(output)
        assert str(output.resolve()) not in json.loads(cache_path.read_text())["pi_output_dirs"]
        # Re-create ownership, then prove a plugin removed entirely from config follows the same path.
        assert sync_target(config(("pi",), (enabled,))).success
        removed_plugin = sync_target(config(("pi",), ()))

    assert removed_plugin.success, removed_plugin.errors
    assert not load_pi_ownership(output)
    assert str(output.resolve()) not in json.loads(cache_path.read_text())["pi_output_dirs"]


def test_pi_preserved_retired_roots_remain_tracked_until_repeat_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures/sample-plugins/complete-plugin", source)
    home, old_root, new_root = tmp_path / "home", tmp_path / "old", tmp_path / "new"
    monkeypatch.setattr(Path, "home", lambda: home)
    installed = [InstalledPlugin("dev-tools@local", "1", "project", True, str(source))]
    plugin = PluginConfig(id="dev-tools@local", scope="project", enabled=True)

    def target(root: Path, targets: tuple[str, ...]) -> TargetConfig:
        return TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(
                plugins=(plugin,),
                conversion=ConversionConfig(targets=targets, scope="project", output_dir=str(root)),
            ),
        )

    with (
        patch("ai_config.operations.claude.list_installed_plugins", return_value=(installed, [])),
        patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
    ):
        assert sync_target(target(old_root, ("pi",))).success
        modified = old_root / ".pi/prompts/dev-tools-commit.md"
        modified.write_text("local edit")
        cache_path = home / ".ai-config/cache/conversion-hashes.json"
        before_dry_run = cache_path.read_bytes()

        dry_run = sync_target(target(old_root, ("cursor",)), dry_run=True)
        assert any(action.action == "preserve_pi_output" for action in dry_run.actions_taken)
        assert cache_path.read_bytes() == before_dry_run
        retired = sync_target(target(old_root, ("cursor",)))
        assert retired.success, retired.errors
        assert str(old_root.resolve()) in json.loads(cache_path.read_text())["pi_output_dirs"]

        # A subsequent sync revisits the retained root and prunes it after user cleanup.
        modified.unlink()
        cleaned = sync_target(target(old_root, ("cursor",)))
        assert cleaned.success, cleaned.errors
        assert not load_pi_ownership(old_root)
        assert str(old_root.resolve()) not in json.loads(cache_path.read_text())["pi_output_dirs"]

        assert sync_target(target(old_root, ("pi",))).success
        modified = old_root / ".pi/prompts/dev-tools-commit.md"
        modified.write_text("local edit")
        migrated = sync_target(target(new_root, ("pi",)))
        assert migrated.success, migrated.errors
        tracked = json.loads(cache_path.read_text())["pi_output_dirs"]
        assert str(old_root.resolve()) in tracked
        assert str(new_root.resolve()) in tracked

        modified.unlink()
        repeated = sync_target(target(new_root, ("pi",)))

    assert repeated.success, repeated.errors
    assert not load_pi_ownership(old_root)
    assert json.loads(cache_path.read_text())["pi_output_dirs"] == [str(new_root.resolve())]


def test_pi_dry_run_matches_apply_without_mutating_output_or_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures/sample-plugins/complete-plugin", source)
    home, output = tmp_path / "home", tmp_path / "output"
    monkeypatch.setattr(Path, "home", lambda: home)
    target = TargetConfig(
        type="claude",
        config=ClaudeTargetConfig(
            plugins=(PluginConfig(id="dev-tools@local", scope="project", enabled=True),),
            conversion=ConversionConfig(targets=("pi",), scope="project", output_dir=str(output)),
        ),
    )
    installed = [InstalledPlugin("dev-tools@local", "1", "project", True, str(source))]
    with (
        patch("ai_config.operations.claude.list_installed_plugins", return_value=(installed, [])),
        patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
    ):
        assert sync_target(target).success
        old_prompt = output / ".pi/prompts/dev-tools-commit.md"
        ledger_path = output / ".ai-config/pi-ownership.json"
        cache_path = home / ".ai-config/cache/conversion-hashes.json"
        before = (old_prompt.read_bytes(), ledger_path.read_bytes(), cache_path.read_bytes())
        (source / "commands/commit.md").unlink()
        planned = sync_target(target, dry_run=True)
        assert before == (
            old_prompt.read_bytes(),
            ledger_path.read_bytes(),
            cache_path.read_bytes(),
        )
        applied = sync_target(target)

    assert [(a.action, a.target) for a in planned.actions_taken] == [
        (a.action, a.target) for a in applied.actions_taken
    ]
    assert not old_prompt.exists()


def test_pi_operation_preserves_local_change_and_rejects_unowned_collision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures/sample-plugins/complete-plugin", source)
    output = tmp_path / "output"
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    target = TargetConfig(
        type="claude",
        config=ClaudeTargetConfig(
            plugins=(PluginConfig(id="dev-tools@local", scope="project", enabled=True),),
            conversion=ConversionConfig(targets=("pi",), scope="project", output_dir=str(output)),
        ),
    )
    installed = [InstalledPlugin("dev-tools@local", "1", "project", True, str(source))]
    with (
        patch("ai_config.operations.claude.list_installed_plugins", return_value=(installed, [])),
        patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
    ):
        assert sync_target(target).success
        owned = output / ".pi/prompts/dev-tools-commit.md"
        owned.write_text("user edit")
        (source / "commands/commit.md").unlink()
        preserved = sync_target(target)
        assert any(action.action == "preserve_pi_output" for action in preserved.actions_taken)
        assert owned.read_text() == "user edit"
        assert verify_sync(AIConfig(version=1, targets=(target,)))

    collision_source = tmp_path / "collision-source"
    shutil.copytree(
        Path(__file__).parents[1] / "fixtures/sample-plugins/complete-plugin", collision_source
    )
    collision_output = tmp_path / "collision-output"
    collision = collision_output / ".pi/prompts/dev-tools-commit.md"
    collision.parent.mkdir(parents=True)
    collision.write_text("user owned")
    collision_installed = [
        InstalledPlugin("dev-tools@local", "1", "project", True, str(collision_source))
    ]
    collision_target = TargetConfig(
        type="claude",
        config=ClaudeTargetConfig(
            plugins=(PluginConfig(id="dev-tools@local", scope="project", enabled=True),),
            conversion=ConversionConfig(
                targets=("pi",), scope="project", output_dir=str(collision_output)
            ),
        ),
    )
    with (
        patch(
            "ai_config.operations.claude.list_installed_plugins",
            return_value=(collision_installed, []),
        ),
        patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
    ):
        failed = sync_target(collision_target)

    assert not failed.success
    assert any("Unowned Pi output collision" in error for error in failed.errors)
    assert collision.read_text() == "user owned"
    assert not load_pi_ownership(collision_output)


def test_pi_unavailable_source_recovers_and_converges_on_next_real_sync(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    shutil.copytree(Path(__file__).parents[1] / "fixtures/sample-plugins/complete-plugin", source)
    output = tmp_path / "output"
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    target = TargetConfig(
        type="claude",
        config=ClaudeTargetConfig(
            plugins=(PluginConfig(id="dev-tools@local", scope="project", enabled=True),),
            conversion=ConversionConfig(targets=("pi",), scope="project", output_dir=str(output)),
        ),
    )
    available = [InstalledPlugin("dev-tools@local", "1", "project", True, str(source))]
    unavailable = [InstalledPlugin("dev-tools@local", "1", "project", True, None)]
    old_prompt = output / ".pi/prompts/dev-tools-commit.md"
    with patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])):
        with patch(
            "ai_config.operations.claude.list_installed_plugins", return_value=(available, [])
        ):
            assert sync_target(target).success
        (source / "commands/commit.md").unlink()
        with patch(
            "ai_config.operations.claude.list_installed_plugins", return_value=(unavailable, [])
        ):
            blocked = sync_target(target)
        assert not blocked.success
        assert old_prompt.exists()
        with patch(
            "ai_config.operations.claude.list_installed_plugins", return_value=(available, [])
        ):
            recovered = sync_target(target)

    assert recovered.success, recovered.errors
    assert not old_prompt.exists()
    assert not load_pi_ownership(output).get(Path(".pi/prompts/dev-tools-commit.md"))


def test_noop_pi_output_is_not_a_verification_discrepancy() -> None:
    result = SyncResult(actions_taken=[SyncAction("noop_pi_output", ".pi/skill", reason="matches")])
    assert sync_discrepancies({"claude": result}) == []


def test_pi_parse_error_preserves_owned_output_before_any_reconciliation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "home"
    apply_pi_reconciliation(
        output, [PiDesiredFile("plugin1@my-marketplace", Path(".pi/old"), b"old")]
    )
    broken_source = tmp_path / "broken"
    broken_source.mkdir()
    target = TargetConfig(
        type="claude",
        config=ClaudeTargetConfig(
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=ConversionConfig(targets=("pi",), scope="user"),
        ),
    )
    monkeypatch.setattr(Path, "home", lambda: output)
    with (
        patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
        patch(
            "ai_config.operations.claude.list_installed_plugins",
            return_value=(
                [InstalledPlugin("plugin1@my-marketplace", "1", "user", True, str(broken_source))],
                [],
            ),
        ),
        patch(
            "ai_config.sync_state.load_conversion_cache",
            return_value={"version": 7, "entries": {}},
        ),
    ):
        result = sync_target(target)
    assert not result.success
    assert any("Pi conversion failed" in error for error in result.errors)
    assert (output / ".pi/old").read_bytes() == b"old"


def test_pi_unavailable_source_dry_run_preserves_same_output_as_sync(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "home"
    owned_path = output / ".pi/old"
    apply_pi_reconciliation(
        output, [PiDesiredFile("plugin1@my-marketplace", Path(".pi/old"), b"old")]
    )
    target = TargetConfig(
        type="claude",
        config=ClaudeTargetConfig(
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=ConversionConfig(targets=("pi",), scope="user"),
        ),
    )
    monkeypatch.setattr(Path, "home", lambda: output)
    installed = [InstalledPlugin("plugin1@my-marketplace", "1", "user", True, None)]
    with (
        patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
        patch("ai_config.operations.claude.list_installed_plugins", return_value=(installed, [])),
        patch(
            "ai_config.sync_state.load_conversion_cache",
            return_value={"version": 7, "entries": {}, "pi_output_dirs": [str(output)]},
        ),
    ):
        dry_run = sync_target(target, dry_run=True)
        actual = sync_target(target)
    assert any(action.action == "preserve_pi_output" for action in dry_run.actions_taken), dry_run
    assert any("temporarily unavailable" in error for error in dry_run.errors)
    assert actual.errors == dry_run.errors
    assert owned_path.read_bytes() == b"old"


class TestConversionCache:
    """Tests for conversion cache handling."""

    def test_old_conversion_cache_version_is_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Old cache versions are invalidated after output schema migrations."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        cache_path = tmp_path / "home" / ".ai-config" / "cache" / "conversion-hashes.json"
        cache_path.parent.mkdir(parents=True)
        cache_path.write_text(
            json.dumps(
                {
                    "version": _CONVERSION_CACHE_VERSION - 1,
                    "entries": {"/plugin": {"signature": {"hash": "abc123"}}},
                }
            )
        )

        assert _load_conversion_cache() == {
            "version": _CONVERSION_CACHE_VERSION,
            "entries": {},
            "codex_output_dirs": [],
        }

    def test_current_conversion_cache_corruption_fails_closed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        cache_path = tmp_path / "home" / ".ai-config" / "cache" / "conversion-hashes.json"
        cache_path.parent.mkdir(parents=True)
        cache_path.write_text('{"version":')

        with pytest.raises(ValueError, match="Invalid conversion cache"):
            _load_conversion_cache()

    def test_owned_codex_hash_detects_tampering_deletion_and_symlinks(self, tmp_path: Path) -> None:
        spec = codex_package_spec("demo", "1.0.0", tmp_path)
        manifest = spec.marketplace_path / ".agents/plugins/marketplace.json"
        package = spec.marketplace_path / "plugins/demo/.codex-plugin/plugin.json"
        manifest.parent.mkdir(parents=True)
        package.parent.mkdir(parents=True)
        manifest.write_text('{"name":"ai-config-demo"}')
        package.write_text('{"name":"demo","version":"1.0.0"}')

        original = _compute_owned_codex_hash(spec)
        assert original is not None
        package.write_text('{"name":"demo","version":"1.0.1"}')
        assert _compute_owned_codex_hash(spec) != original
        package.write_text('{"name":"demo","version":"1.0.0"}')
        package.chmod(package.stat().st_mode | 0o111)
        assert _compute_owned_codex_hash(spec) != original
        package.unlink()
        assert _compute_owned_codex_hash(spec) is not None
        package.symlink_to(manifest)
        assert _compute_owned_codex_hash(spec) is None
        spec.marketplace_path.rename(spec.marketplace_path.with_name("deleted"))
        assert _compute_owned_codex_hash(spec) is None


class TestSyncTarget:
    """Tests for sync_target function."""

    def test_unsupported_target_type(self) -> None:
        """Unsupported target type returns error."""
        # Create a target with invalid type by bypassing validation
        target = TargetConfig.__new__(TargetConfig)
        object.__setattr__(target, "type", "codex")
        object.__setattr__(target, "config", ClaudeTargetConfig())

        result = sync_target(target)

        assert result.success is False
        assert any("only supports 'claude'" in e for e in result.errors)

    def test_unsupported_fresh_target_does_not_clear_claude_cache(self) -> None:
        target = TargetConfig.__new__(TargetConfig)
        object.__setattr__(target, "type", "codex")

        with patch("ai_config.operations.claude.clear_cache") as clear_cache:
            result = sync_target(target, fresh=True)

        assert result.success is False
        clear_cache.assert_not_called()

    def test_dry_run_no_changes(
        self,
        sample_config: AIConfig,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
    ) -> None:
        """Dry run with everything in sync makes no changes."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
        ):
            result = sync_target(sample_config.targets[0], dry_run=True)

            # plugin1 is installed and enabled (matches config)
            # plugin2 is not installed but should be disabled (no action needed)
            # marketplace is installed (no action needed)
            assert result.success is True
            assert len(result.errors) == 0

    def test_install_missing_plugin(self, sample_config: AIConfig) -> None:
        """Missing plugin is installed."""
        # No plugins installed
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.add_marketplace",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
            patch(
                "ai_config.operations.claude.install_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_install,
        ):
            result = sync_target(sample_config.targets[0])

            # Should install plugin1 (enabled) but not plugin2 (disabled)
            mock_install.assert_called_once_with("plugin1@my-marketplace", "user")
            assert result.success is True
            assert any(a.action == "install" for a in result.actions_taken)

    def test_enable_disabled_plugin(self, sample_config: AIConfig) -> None:
        """Disabled plugin that should be enabled is enabled."""
        # plugin1 is installed but disabled
        installed_plugins = [
            InstalledPlugin(
                id="plugin1@my-marketplace",
                version="1.0.0",
                scope="user",
                enabled=False,  # Currently disabled
                install_path="/path",
            ),
        ]
        installed_mps = [
            InstalledMarketplace(
                name="my-marketplace",
                source=PluginSource.GITHUB,
                repo="owner/repo",
                install_location="/path",
            ),
        ]

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(installed_mps, []),
            ),
            patch(
                "ai_config.operations.claude.enable_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_enable,
        ):
            result = sync_target(sample_config.targets[0])

            mock_enable.assert_called_once_with("plugin1@my-marketplace")
            assert result.success is True
            assert any(a.action == "enable" for a in result.actions_taken)

    def test_disable_enabled_plugin(self) -> None:
        """Enabled plugin that should be disabled is disabled."""
        # Config wants plugin disabled
        plugin = PluginConfig(id="plugin1@mp", scope="user", enabled=False)
        target_config = ClaudeTargetConfig(plugins=(plugin,))
        target = TargetConfig(type="claude", config=target_config)

        # But plugin is installed and enabled
        installed_plugins = [
            InstalledPlugin(
                id="plugin1@mp",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path="/path",
            ),
        ]

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.disable_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_disable,
        ):
            result = sync_target(target)

            mock_disable.assert_called_once_with("plugin1@mp")
            assert result.success is True
            assert any(a.action == "disable" for a in result.actions_taken)

    def test_sync_runs_conversion_when_configured(
        self,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        isolate_codex_lifecycle,
    ) -> None:
        """Sync should run conversion and Codex package lifecycle when configured."""
        conversion = ConversionConfig(
            enabled=True,
            targets=("codex",),
            scope="user",
            output_dir=None,
        )
        target_config = ClaudeTargetConfig(
            marketplaces={
                "my-marketplace": MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
            },
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=conversion,
        )
        target = TargetConfig(type="claude", config=target_config)

        # Ensure deterministic home path resolution
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        report = ConversionReport(
            source_plugin=PluginIdentity(plugin_id="plugin1", name="plugin1", version="1.0.0"),
            target_tool=TargetTool.CODEX,
        )

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
            patch("ai_config.sync_state.compute_owned_codex_hash", return_value="generated"),
            patch(
                "ai_config.sync_conversion.convert_plugin",
                return_value={TargetTool.CODEX: report},
            ) as mock_convert,
        ):
            result = sync_target(target)

            assert result.success is True
            assert mock_convert.called
            call_args = mock_convert.call_args.kwargs
            assert call_args["plugin_path"] == Path(mock_installed_plugins[0].install_path)
            assert call_args["output_dir"] == Path(tmp_path / "home")
            assert isolate_codex_lifecycle.call_count == 2

    def test_sync_skips_conversion_when_hash_unchanged(
        self,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Conversion is skipped when cached hash matches current hash."""
        conversion = ConversionConfig(
            enabled=True,
            targets=("codex",),
            scope="user",
            output_dir=None,
        )
        target_config = ClaudeTargetConfig(
            marketplaces={
                "my-marketplace": MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
            },
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=conversion,
        )
        target = TargetConfig(type="claude", config=target_config)

        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        output_dir = Path(tmp_path / "home")
        signature = _conversion_signature(conversion, output_dir)
        plugin_path = Path(mock_installed_plugins[0].install_path)

        cache = {
            "version": _CONVERSION_CACHE_VERSION,
            "entries": {
                str(plugin_path): {
                    signature: {
                        "hash": "abc123",
                        "codex_output_hash": "generated123",
                    },
                }
            },
        }

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
            patch("ai_config.sync_state.load_conversion_cache", return_value=cache),
            patch("ai_config.sync_state.compute_plugin_hash", return_value="abc123"),
            patch(
                "ai_config.sync_state.compute_owned_codex_hash",
                return_value="generated123",
            ),
            patch("ai_config.sync_conversion.convert_plugin") as mock_convert,
        ):
            result = sync_target(target)

            assert result.success is True
            mock_convert.assert_not_called()

    def test_sync_force_convert_ignores_cache(
        self,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Force-convert bypasses hash cache and runs conversion."""
        conversion = ConversionConfig(
            enabled=True,
            targets=("codex",),
            scope="user",
            output_dir=None,
        )
        target_config = ClaudeTargetConfig(
            marketplaces={
                "my-marketplace": MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
            },
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=conversion,
        )
        target = TargetConfig(type="claude", config=target_config)

        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        report = ConversionReport(
            source_plugin=PluginIdentity(plugin_id="plugin1", name="plugin1", version="1.0.0"),
            target_tool=TargetTool.CODEX,
        )

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
            patch(
                "ai_config.sync_state.load_conversion_cache",
                return_value={"version": 1, "entries": {}},
            ),
            patch("ai_config.sync_state.compute_plugin_hash", return_value="abc123"),
            patch("ai_config.sync_state.compute_owned_codex_hash", return_value="generated"),
            patch(
                "ai_config.sync_conversion.convert_plugin",
                return_value={TargetTool.CODEX: report},
            ) as mock_convert,
        ):
            result = sync_target(target, force_convert=True)

            assert result.success is True
            mock_convert.assert_called()

    def test_sync_updates_cache_on_successful_conversion(
        self,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Conversion cache is updated after a successful conversion."""
        conversion = ConversionConfig(
            enabled=True,
            targets=("codex",),
            scope="user",
            output_dir=None,
        )
        target_config = ClaudeTargetConfig(
            marketplaces={
                "my-marketplace": MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
            },
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=conversion,
        )
        target = TargetConfig(type="claude", config=target_config)

        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        output_dir = Path(tmp_path / "home")
        signature = _conversion_signature(conversion, output_dir)
        plugin_path = Path(mock_installed_plugins[0].install_path)

        identity = PluginIdentity(plugin_id="plugin1", name="plugin1", version="1.0.0")
        report = ConversionReport(source_plugin=identity, target_tool=TargetTool.CODEX)

        saved_cache: dict = {}

        def _capture_cache(cache: dict) -> None:
            saved_cache.update(cache)

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
            patch(
                "ai_config.sync_state.load_conversion_cache",
                return_value={"version": 1, "entries": {}},
            ),
            patch("ai_config.sync_state.compute_plugin_hash", return_value="abc123"),
            patch("ai_config.sync_state.compute_owned_codex_hash", return_value="generated"),
            patch(
                "ai_config.sync_conversion.convert_plugin", return_value={TargetTool.CODEX: report}
            ),
            patch("ai_config.sync_state.save_conversion_cache", side_effect=_capture_cache),
        ):
            result = sync_target(target)

            assert result.success is True
            assert saved_cache["codex_output_dirs"] == [str(output_dir.resolve())]
            assert "entries" in saved_cache
            assert str(plugin_path) in saved_cache["entries"]
            assert signature in saved_cache["entries"][str(plugin_path)]

    def test_sync_conversion_uses_local_marketplace_when_install_path_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Conversion falls back to local marketplace source when Claude cache path is stale."""
        plugin_dir = tmp_path / "marketplace" / "plugin1"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / ".claude-plugin").mkdir()
        (plugin_dir / ".claude-plugin" / "plugin.json").write_text('{"name":"plugin1"}')
        conversion = ConversionConfig(
            enabled=True,
            targets=("pi",),
            scope="user",
            output_dir=None,
        )
        target_config = ClaudeTargetConfig(
            marketplaces={
                "my-marketplace": MarketplaceConfig(
                    source=PluginSource.LOCAL,
                    path=str(tmp_path / "marketplace"),
                )
            },
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=conversion,
        )
        target = TargetConfig(type="claude", config=target_config)
        installed_plugins = [
            InstalledPlugin(
                id="plugin1@my-marketplace",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(tmp_path / "missing-cache"),
            )
        ]

        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(
                    [
                        InstalledMarketplace(
                            name="my-marketplace",
                            source=PluginSource.LOCAL,
                            repo=str(tmp_path / "marketplace"),
                            install_location=str(tmp_path / "marketplace"),
                        )
                    ],
                    [],
                ),
            ),
            patch(
                "ai_config.sync_state.load_conversion_cache",
                return_value={"version": 1, "entries": {}},
            ),
            patch("ai_config.sync_conversion.convert_plugin") as mock_convert,
        ):
            result = sync_target(target, force_convert=True)

            assert result.success is True
            assert result.errors == []
            assert mock_convert.call_args.kwargs["plugin_path"] == plugin_dir

    def test_sync_conversion_uses_local_marketplace_manifest_source(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Local fallback respects marketplace.json source paths."""
        marketplace_dir = tmp_path / "marketplace"
        plugin_dir = marketplace_dir / "plugins" / "plugin-source"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / ".claude-plugin").mkdir()
        (plugin_dir / ".claude-plugin" / "plugin.json").write_text('{"name":"plugin1"}')
        (marketplace_dir / ".claude-plugin").mkdir()
        (marketplace_dir / ".claude-plugin" / "marketplace.json").write_text(
            '{"name":"my-marketplace","plugins":[{"name":"plugin1","source":"./plugins/plugin-source"}]}'
        )
        conversion = ConversionConfig(
            enabled=True,
            targets=("pi",),
            scope="user",
            output_dir=None,
        )
        target_config = ClaudeTargetConfig(
            marketplaces={
                "my-marketplace": MarketplaceConfig(
                    source=PluginSource.LOCAL,
                    path=str(marketplace_dir),
                )
            },
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=conversion,
        )
        target = TargetConfig(type="claude", config=target_config)
        installed_plugins = [
            InstalledPlugin(
                id="plugin1@my-marketplace",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(tmp_path / "missing-cache"),
            )
        ]

        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(
                    [
                        InstalledMarketplace(
                            name="my-marketplace",
                            source=PluginSource.LOCAL,
                            repo=str(marketplace_dir),
                            install_location=str(marketplace_dir),
                        )
                    ],
                    [],
                ),
            ),
            patch(
                "ai_config.sync_state.load_conversion_cache",
                return_value={"version": 1, "entries": {}},
            ),
            patch("ai_config.sync_conversion.convert_plugin") as mock_convert,
        ):
            result = sync_target(target, force_convert=True)

            assert result.success is True
            assert result.errors == []
            assert mock_convert.call_args.kwargs["plugin_path"] == plugin_dir.resolve()

    def test_sync_conversion_reports_missing_plugin_source(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Missing installPath/local source produces a visible sync error."""
        conversion = ConversionConfig(
            enabled=True,
            targets=("pi",),
            scope="user",
            output_dir=None,
        )
        target_config = ClaudeTargetConfig(
            marketplaces={
                "my-marketplace": MarketplaceConfig(
                    source=PluginSource.LOCAL,
                    path=str(tmp_path / "marketplace"),
                )
            },
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=conversion,
        )
        target = TargetConfig(type="claude", config=target_config)
        installed_plugins = [
            InstalledPlugin(
                id="plugin1@my-marketplace",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(tmp_path / "missing-cache"),
            )
        ]

        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
            patch(
                "ai_config.sync_state.load_conversion_cache",
                return_value={"version": 1, "entries": {}},
            ),
            patch("ai_config.sync_conversion.convert_plugin") as mock_convert,
        ):
            result = sync_target(target, force_convert=True)

            assert result.success is False
            assert any("temporarily unavailable" in error for error in result.errors)
            mock_convert.assert_not_called()

    def test_sync_conversion_reports_conversion_diagnostics(
        self,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Conversion report errors are surfaced in sync output."""
        conversion = ConversionConfig(
            enabled=True,
            targets=("pi",),
            scope="user",
            output_dir=None,
        )
        target_config = ClaudeTargetConfig(
            marketplaces={
                "my-marketplace": MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
            },
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=conversion,
        )
        target = TargetConfig(type="claude", config=target_config)
        identity = PluginIdentity(plugin_id="plugin1", name="plugin1", version="1.0.0")
        report = ConversionReport(source_plugin=identity, target_tool=TargetTool.PI)
        report.add_diagnostic(
            Diagnostic(severity=Severity.ERROR, message="Could not find plugin.json manifest")
        )

        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
            patch(
                "ai_config.sync_state.load_conversion_cache",
                return_value={"version": 1, "entries": {}},
            ),
            patch("ai_config.sync_state.compute_plugin_hash", return_value="abc123"),
            patch("ai_config.sync_conversion.convert_plugin", return_value={TargetTool.PI: report}),
        ):
            result = sync_target(target, force_convert=True)

            assert result.success is False
            assert any("Could not find plugin.json manifest" in error for error in result.errors)

    def test_codex_sync_uses_emitted_normalized_identity_roundtrip(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        isolate_codex_lifecycle,
    ) -> None:
        """Config identity and lifecycle selector converge on the emitted normalized identity."""
        plugin_path = tmp_path / "source"
        (plugin_path / ".claude-plugin").mkdir(parents=True)
        (plugin_path / ".claude-plugin/plugin.json").write_text(
            '{"name":"My Plugin!","version":"1.2.3"}'
        )
        installed = InstalledPlugin(
            id="My Plugin!@market",
            version="1.2.3",
            scope="user",
            enabled=True,
            install_path=str(plugin_path),
        )
        target = TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(
                plugins=(PluginConfig(id=installed.id),),
                conversion=ConversionConfig(
                    targets=("codex",), output_dir=str(tmp_path / "output")
                ),
            ),
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([installed], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
        ):
            result = sync_target(target, force_convert=True)

        assert result.success is True
        specs = isolate_codex_lifecycle.call_args.args[0]
        assert [spec.plugin_id for spec in specs] == ["my-plugin@ai-config-my-plugin"]
        assert specs[0].source_plugin_id == "My Plugin!@market"
        emitted_manifest = next(
            (tmp_path / "output").glob(
                ".ai-config/codex/marketplaces/*/plugins/*/.codex-plugin/plugin.json"
            )
        )
        assert json.loads(emitted_manifest.read_text())["name"] == "my-plugin"

    def test_codex_sync_config_and_manifest_identity_mismatch_fails_before_emission(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        isolate_codex_lifecycle,
    ) -> None:
        """A config selector cannot silently point at a differently named emitted package."""
        source = tmp_path / "source"
        (source / ".claude-plugin").mkdir(parents=True)
        (source / ".claude-plugin/plugin.json").write_text(
            '{"name":"manifest-name","version":"1.0.0"}'
        )
        installed = InstalledPlugin(
            id="config-name@market",
            version="1.0.0",
            scope="user",
            enabled=True,
            install_path=str(source),
        )
        target = TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(
                plugins=(PluginConfig(id=installed.id),),
                conversion=ConversionConfig(
                    targets=("codex",), output_dir=str(tmp_path / "output")
                ),
            ),
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([installed], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
            patch("ai_config.sync_conversion.convert_plugin") as convert,
        ):
            result = sync_target(target, force_convert=True)

        assert result.success is False
        assert any("identity mismatch" in error for error in result.errors)
        convert.assert_not_called()
        isolate_codex_lifecycle.assert_not_called()

    def test_codex_sync_normalized_collision_fails_before_emission(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        isolate_codex_lifecycle,
    ) -> None:
        """Two configured sources cannot silently collapse onto one package selector."""
        installed: list[InstalledPlugin] = []
        configs: list[PluginConfig] = []
        for index, name in enumerate(("My Plugin!", "my-plugin")):
            source = tmp_path / f"source-{index}"
            (source / ".claude-plugin").mkdir(parents=True)
            (source / ".claude-plugin/plugin.json").write_text(
                json.dumps({"name": name, "version": "1.0.0"})
            )
            plugin_id = f"{name}@market-{index}"
            installed.append(
                InstalledPlugin(
                    id=plugin_id,
                    version="1.0.0",
                    scope="user",
                    enabled=True,
                    install_path=str(source),
                )
            )
            configs.append(PluginConfig(id=plugin_id))
        target = TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(
                plugins=tuple(configs),
                conversion=ConversionConfig(
                    targets=("codex",), output_dir=str(tmp_path / "output")
                ),
            ),
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(installed, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
            patch("ai_config.sync_conversion.convert_plugin") as convert,
        ):
            result = sync_target(target, force_convert=True)

        assert result.success is False
        assert any("identity collision" in error for error in result.errors)
        convert.assert_not_called()
        isolate_codex_lifecycle.assert_not_called()
        assert not (tmp_path / "output").exists()

    def test_configured_unavailable_source_retains_owned_codex_identity(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        isolate_codex_lifecycle,
    ) -> None:
        plugin = PluginConfig(id="missing-plugin@market", enabled=True)
        target = TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(
                plugins=(plugin,),
                conversion=ConversionConfig(
                    targets=("codex",), output_dir=str(tmp_path / "output")
                ),
            ),
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        with (
            patch("ai_config.operations.claude.list_installed_plugins", return_value=([], [])),
            patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
            patch(
                "ai_config.operations.claude.install_plugin",
                return_value=CommandResult(True, "", "", 0),
            ),
        ):
            result = sync_target(target)

        assert result.success is False
        assert any("temporarily unavailable" in error for error in result.errors)
        retained = isolate_codex_lifecycle.call_args.kwargs["retained_plugin_ids"]
        assert retained == {"missing-plugin@ai-config-missing-plugin"}

    def test_disabled_source_reconciles_prior_owned_codex_state(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        isolate_codex_lifecycle,
    ) -> None:
        target = TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(
                plugins=(PluginConfig(id="disabled@market", enabled=False),),
                conversion=ConversionConfig(
                    targets=("codex",), output_dir=str(tmp_path / "output")
                ),
            ),
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        with (
            patch("ai_config.operations.claude.list_installed_plugins", return_value=([], [])),
            patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
        ):
            result = sync_target(target)

        assert result.success is True
        assert isolate_codex_lifecycle.call_args.args[0] == []
        reasons = isolate_codex_lifecycle.call_args.kwargs["removal_reasons"]
        assert reasons["disabled@ai-config-disabled"] == "Source plugin is disabled"

    @pytest.mark.parametrize("conversion", [None, ConversionConfig(enabled=False)])
    def test_removed_or_disabled_codex_target_reconciles_owned_state(
        self,
        conversion: ConversionConfig | None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        isolate_codex_lifecycle,
    ) -> None:
        output = tmp_path / "output"
        ownership = output / ".ai-config/codex/ownership.json"
        ownership.parent.mkdir(parents=True)
        ownership.write_text('{"version":1,"packages":{}}')
        if conversion is not None:
            conversion = ConversionConfig(enabled=False, output_dir=str(output))
        target = TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(conversion=conversion),
        )
        monkeypatch.chdir(output)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        with (
            patch("ai_config.operations.claude.list_installed_plugins", return_value=([], [])),
            patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
        ):
            result = sync_target(target)

        assert result.success is True
        assert isolate_codex_lifecycle.call_count == 2
        assert isolate_codex_lifecycle.call_args.args[0] == []
        assert isolate_codex_lifecycle.call_args.kwargs["output_dir"] == output

    def test_target_removed_uses_cache_to_find_prior_custom_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        isolate_codex_lifecycle,
    ) -> None:
        prior_output = tmp_path / "prior-custom-output"
        ownership = prior_output / ".ai-config/codex/ownership.json"
        ownership.parent.mkdir(parents=True)
        ownership.write_text('{"version":1,"packages":{}}')
        signature = json.dumps(
            {
                "targets": ["codex"],
                "scope": "project",
                "output_dir": str(prior_output),
            },
            sort_keys=True,
        )
        cache = {
            "version": _CONVERSION_CACHE_VERSION,
            "entries": {"/old/source": {signature: {"hash": "old"}}},
            "codex_output_dirs": [str(prior_output)],
        }
        target = TargetConfig(type="claude", config=ClaudeTargetConfig(conversion=None))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        with (
            patch("ai_config.sync_state.load_conversion_cache", return_value=cache),
            patch("ai_config.operations.claude.list_installed_plugins", return_value=([], [])),
            patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
        ):
            result = sync_target(target)

        assert result.success is True
        assert isolate_codex_lifecycle.call_count == 2
        assert isolate_codex_lifecycle.call_args.kwargs["output_dir"] == prior_output
        assert (
            isolate_codex_lifecycle.call_args.kwargs["default_removal_reason"]
            == "Codex conversion target is disabled or removed"
        )

    def test_cache_hit_reconverts_when_generated_codex_output_is_missing(
        self,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        output = tmp_path / "output"
        conversion = ConversionConfig(targets=("codex",), output_dir=str(output))
        target = TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(
                plugins=(PluginConfig(id="plugin1@my-marketplace"),),
                conversion=conversion,
            ),
        )
        signature = _conversion_signature(conversion, output)
        plugin_path = Path(mock_installed_plugins[0].install_path)
        cache = {
            "version": _CONVERSION_CACHE_VERSION,
            "entries": {
                str(plugin_path): {
                    signature: {"hash": "abc123", "codex_output_hash": "generated123"}
                }
            },
        }
        report = ConversionReport(
            source_plugin=PluginIdentity(plugin_id="plugin1", name="plugin1", version="1.0.0"),
            target_tool=TargetTool.CODEX,
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
            patch("ai_config.sync_state.load_conversion_cache", return_value=cache),
            patch("ai_config.sync_state.compute_plugin_hash", return_value="abc123"),
            patch(
                "ai_config.sync_state.compute_owned_codex_hash",
                side_effect=[None, "generated123"],
            ),
            patch(
                "ai_config.sync_conversion.convert_plugin",
                return_value={TargetTool.CODEX: report},
            ) as convert,
        ):
            result = sync_target(target)

        assert result.success is True
        assert convert.called

    def test_lifecycle_preflight_failure_leaves_generated_bytes_unchanged(
        self,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        isolate_codex_lifecycle,
    ) -> None:
        output = tmp_path / "output"
        generated = output / ".ai-config/codex/marketplaces/ai-config-plugin1/marker"
        generated.parent.mkdir(parents=True)
        generated.write_bytes(b"before")
        conversion = ConversionConfig(targets=("codex",), output_dir=str(output))
        target = TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(
                plugins=(PluginConfig(id="plugin1@my-marketplace"),),
                conversion=conversion,
            ),
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        isolate_codex_lifecycle.side_effect = ValueError("would downgrade ownership state")
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
            patch("ai_config.sync_conversion.convert_plugin") as convert,
        ):
            result = sync_target(target, force_convert=True)

        assert result.success is False
        assert any("would downgrade" in error for error in result.errors)
        assert generated.read_bytes() == b"before"
        assert convert.call_count == 1
        assert convert.call_args.kwargs["dry_run"] is True
        assert isolate_codex_lifecycle.call_args.kwargs["dry_run"] is True

    def test_partial_lifecycle_failure_preserves_completed_and_failed_actions(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        isolate_codex_lifecycle,
    ) -> None:
        output = tmp_path / "output"
        ownership = output / ".ai-config/codex/ownership.json"
        ownership.parent.mkdir(parents=True)
        ownership.write_text('{"version":1,"packages":{}}')
        completed = CodexLifecycleAction("remove_codex_plugin", "demo@market", "removed")
        failed = CodexLifecycleAction("remove_codex_marketplace", "market", "removed")
        failure = CodexLifecycleExecutionError(
            planned_actions=(completed, failed),
            completed_actions=(completed,),
            failed_action=failed,
            cause="permission denied",
        )
        isolate_codex_lifecycle.side_effect = [list(failure.planned_actions), failure]
        target = TargetConfig(
            type="claude",
            config=ClaudeTargetConfig(
                conversion=ConversionConfig(enabled=False, output_dir=str(output))
            ),
        )
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        with (
            patch("ai_config.operations.claude.list_installed_plugins", return_value=([], [])),
            patch("ai_config.operations.claude.list_installed_marketplaces", return_value=([], [])),
        ):
            result = sync_target(target)

        assert [action.action for action in result.actions_taken] == ["remove_codex_plugin"]
        assert [action.action for action in result.actions_failed] == ["remove_codex_marketplace"]
        assert result.success is False

    def test_sync_skips_conversion_when_disabled(
        self,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
    ) -> None:
        """Sync should not run conversion when conversion is disabled."""
        conversion = ConversionConfig(
            enabled=False,
            targets=("codex",),
            scope="user",
        )
        target_config = ClaudeTargetConfig(
            marketplaces={
                "my-marketplace": MarketplaceConfig(source=PluginSource.GITHUB, repo="owner/repo")
            },
            plugins=(PluginConfig(id="plugin1@my-marketplace", scope="user", enabled=True),),
            conversion=conversion,
        )
        target = TargetConfig(type="claude", config=target_config)

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
            patch("ai_config.sync_conversion.convert_plugin") as mock_convert,
        ):
            sync_target(target)
            mock_convert.assert_not_called()

    def test_add_missing_marketplace(self, sample_config: AIConfig) -> None:
        """Missing marketplace is added."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),  # No marketplaces
            ),
            patch(
                "ai_config.operations.claude.add_marketplace",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_add,
            patch(
                "ai_config.operations.claude.install_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
        ):
            result = sync_target(sample_config.targets[0])

            mock_add.assert_called_once_with(repo="owner/repo", name="my-marketplace", path=None)
            assert any(a.action == "register_marketplace" for a in result.actions_taken)

    def test_fresh_clears_cache_before_runtime_observation(self, sample_config: AIConfig) -> None:
        """Fresh mode clears cache before marketplace and plugin observation."""
        recorder = RuntimeObservationRecorder()

        with (
            patch("ai_config.operations.claude.clear_cache", side_effect=recorder.clear_cache),
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                side_effect=recorder.plugins,
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                side_effect=recorder.marketplaces,
            ),
            patch(
                "ai_config.operations.claude.add_marketplace",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
            patch(
                "ai_config.operations.claude.install_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
        ):
            sync_target(sample_config.targets[0], fresh=True)

        assert recorder.calls[:3] == ["clear", "marketplaces", "plugins"]

    def test_dry_run_skips_cache_clear(self, sample_config: AIConfig) -> None:
        """Dry run does not clear cache."""
        with (
            patch(
                "ai_config.operations.claude.clear_cache",
            ) as mock_clear,
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
        ):
            sync_target(sample_config.targets[0], dry_run=True, fresh=True)

            mock_clear.assert_not_called()


class TestSyncConfig:
    """Tests for sync_config function."""

    def test_sync_all_targets(self, sample_config: AIConfig) -> None:
        """Syncs all targets in config."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.add_marketplace",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
            patch(
                "ai_config.operations.claude.install_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
        ):
            results = sync_config(sample_config)

            assert "claude" in results
            assert results["claude"].success is True


class TestGetStatus:
    """Tests for get_status function."""

    def test_returns_plugins_and_marketplaces(
        self,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
    ) -> None:
        """Returns status of installed plugins and marketplaces."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
        ):
            result = get_status()

            assert result.target_type == "claude"
            assert len(result.plugins) == 1
            assert result.plugins[0].id == "plugin1@my-marketplace"
            assert result.plugins[0].installed is True
            assert "my-marketplace" in result.marketplaces

    def test_unsupported_target(self) -> None:
        """Unsupported target returns error."""
        result = get_status(target_type="codex")

        assert any("only supports 'claude'" in e for e in result.errors)


class TestUpdatePlugins:
    """Tests for update_plugins function."""

    def test_update_all_plugins(
        self,
        mock_installed_plugins: list[InstalledPlugin],
    ) -> None:
        """Updates all installed plugins when no IDs specified."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.update_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_update,
        ):
            result = update_plugins()

            mock_update.assert_called_once_with("plugin1@my-marketplace")
            assert result.success is True

    def test_update_specific_plugins(
        self,
        mock_installed_plugins: list[InstalledPlugin],
    ) -> None:
        """Updates only specified plugins."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.update_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_update,
        ):
            result = update_plugins(plugin_ids=["plugin1@my-marketplace"])

            mock_update.assert_called_once_with("plugin1@my-marketplace")
            assert result.success is True

    def test_warns_about_missing_plugins(
        self,
        mock_installed_plugins: list[InstalledPlugin],
    ) -> None:
        """Warns when specified plugin is not installed."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.update_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
        ):
            result = update_plugins(plugin_ids=["nonexistent-plugin"])

            assert any("not installed" in e for e in result.errors)

    def test_fresh_clears_cache(
        self,
        mock_installed_plugins: list[InstalledPlugin],
    ) -> None:
        """Fresh mode clears cache before updating."""
        with (
            patch(
                "ai_config.operations.claude.clear_cache",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ) as mock_clear,
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.update_plugin",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
        ):
            update_plugins(fresh=True)

            mock_clear.assert_called_once()


class TestVerifySync:
    """Tests for verify_sync function."""

    def test_in_sync(
        self,
        sample_config: AIConfig,
        mock_installed_plugins: list[InstalledPlugin],
        mock_installed_marketplaces: list[InstalledMarketplace],
    ) -> None:
        """No discrepancies when in sync."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(mock_installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(mock_installed_marketplaces, []),
            ),
        ):
            discrepancies = verify_sync(sample_config)

            # plugin1 is installed and enabled (matches)
            # plugin2 is not installed but disabled (ok)
            assert discrepancies == []

    def test_missing_marketplace(self, sample_config: AIConfig) -> None:
        """Detects missing marketplace."""
        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=([], []),  # No marketplaces
            ),
        ):
            discrepancies = verify_sync(sample_config)

            assert any("register_marketplace required" in d for d in discrepancies)

    def test_missing_enabled_plugin(self, sample_config: AIConfig) -> None:
        """Detects missing enabled plugin."""
        installed_mps = [
            InstalledMarketplace(
                name="my-marketplace",
                source=PluginSource.GITHUB,
                repo="owner/repo",
                install_location="/path",
            ),
        ]

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),  # No plugins
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(installed_mps, []),
            ),
        ):
            discrepancies = verify_sync(sample_config)

            assert any("not installed" in d for d in discrepancies)

    def test_wrong_enabled_state(self, sample_config: AIConfig) -> None:
        """Detects plugin with wrong enabled state."""
        # plugin1 should be enabled but is disabled
        installed_plugins = [
            InstalledPlugin(
                id="plugin1@my-marketplace",
                version="1.0.0",
                scope="user",
                enabled=False,
                install_path="/path",
            ),
        ]
        installed_mps = [
            InstalledMarketplace(
                name="my-marketplace",
                source=PluginSource.GITHUB,
                repo="owner/repo",
                install_location="/path",
            ),
        ]

        with (
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=(installed_plugins, []),
            ),
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                return_value=(installed_mps, []),
            ),
        ):
            discrepancies = verify_sync(sample_config)

            assert any("should be enabled" in d for d in discrepancies)


class TestSyncMarketplaceNameMismatch:
    """Tests for marketplace name mismatch detection."""

    def test_detects_name_mismatch(self, sample_config: AIConfig) -> None:
        """Detects when registered name differs from config key."""
        # Config uses "my-marketplace" as key, but CLI registers as "actual-name"
        with (
            patch(
                "ai_config.operations.claude.list_installed_marketplaces",
                side_effect=[
                    ([], []),  # Initial: no marketplaces
                    ([], []),  # Pre-add baseline
                    (  # After add: registered under different name
                        [
                            InstalledMarketplace(
                                name="actual-name",
                                source=PluginSource.GITHUB,
                                repo="owner/repo",
                                install_location="/path",
                            ),
                        ],
                        [],
                    ),
                ],
            ),
            patch(
                "ai_config.operations.claude.add_marketplace",
                return_value=CommandResult(success=True, stdout="", stderr="", returncode=0),
            ),
            patch(
                "ai_config.operations.claude.list_installed_plugins",
                return_value=([], []),
            ),
        ):
            result = sync_target(sample_config.targets[0])

            # Registration completed, while the postcondition mismatch remains an error.
            assert any(action.action == "register_marketplace" for action in result.actions_taken)
            assert any("actual-name" in e and "my-marketplace" in e for e in result.errors)
