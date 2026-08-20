"""Shared skill resource projection and contained-source safety contracts."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_config.converters.claude_parser import parse_claude_plugin
from ai_config.converters.convert import convert_plugin
from ai_config.converters.emitters import CodexEmitter, CursorEmitter, OpenCodeEmitter, PiEmitter
from ai_config.converters.ir import MappingStatus, McpServer, PluginIdentity, PluginIR, TargetTool
from ai_config.pi_ownership import load_pi_ownership
from ai_config.sync_state import compute_plugin_hash, load_conversion_cache
from ai_config.validators.target.codex import CodexOutputValidator
from ai_config.validators.target.cursor import CursorOutputValidator
from ai_config.validators.target.opencode import OpenCodeOutputValidator
from ai_config.validators.target.pi import PiOutputValidator
from ai_config.validators.target.skill_invariants import generated_skill_invariant_errors

FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample-plugins" / "shared-includes"


def _plugin(tmp_path: Path, includes: object, body: str = "body") -> Path:
    plugin = tmp_path / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin/plugin.json").write_text(
        json.dumps({"name": "safe-plugin", "skills": "./skills"})
    )
    for name in ("good", "bad"):
        directory = plugin / "skills" / name
        directory.mkdir(parents=True)
        metadata = includes if name == "bad" else []
        (directory / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            f"description: {name}\n"
            f"x-ai-config-includes: {json.dumps(metadata)}\n"
            "---\n\n"
            f"{body if name == 'bad' else 'safe body'}\n"
        )
    return plugin


def _remove_include_metadata(plugin: Path) -> None:
    for name in ("alpha", "beta"):
        (plugin / f"skills/{name}/SKILL.md").write_text(
            f"---\nname: {name}\ndescription: no includes\n---\n\nplain body\n"
        )


def _target_native_alpha_skill(target: TargetTool) -> Path:
    if target == TargetTool.CODEX:
        return Path("targets/codex/skills/alpha")
    if target == TargetTool.CURSOR:
        return Path("targets/cursor/skills/shared-includes-alpha")
    if target == TargetTool.OPENCODE:
        return Path("targets/opencode/.opencode/skills/shared-includes-alpha")
    return Path("targets/pi/skills/shared-includes-alpha")


def _skill_roots(target: TargetTool) -> tuple[Path, Path]:
    if target == TargetTool.CODEX:
        root = Path(
            ".ai-config/codex/marketplaces/ai-config-shared-includes/plugins/shared-includes/skills"
        )
        return root / "alpha", root / "beta"
    prefix = {
        TargetTool.CURSOR: Path(".cursor/skills"),
        TargetTool.OPENCODE: Path(".opencode/skills"),
        TargetTool.PI: Path(".pi/skills"),
    }[target]
    return prefix / "shared-includes-alpha", prefix / "shared-includes-beta"


def test_parser_captures_immutable_byte_exact_include_records() -> None:
    ir = parse_claude_plugin(FIXTURE)
    assert not ir.has_errors()
    alpha = next(skill for skill in ir.skills() if skill.name == "alpha")
    assert alpha.includes[0].source_relative_path == "shared/data.txt"
    assert alpha.includes[0].projected_path == "_shared/shared/data.txt"
    assert alpha.includes[0].content == (FIXTURE / "shared/data.txt").read_bytes()
    assert alpha.includes[2].executable
    assert alpha.includes[3].content == (FIXTURE / "shared/blob.bin").read_bytes()
    with pytest.raises(ValidationError):
        alpha.includes[0].content = b"changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("target", "emitter"),
    [
        (TargetTool.CODEX, CodexEmitter()),
        (TargetTool.CURSOR, CursorEmitter()),
        (TargetTool.OPENCODE, OpenCodeEmitter()),
        (TargetTool.PI, PiEmitter()),
    ],
)
def test_all_emitters_materialize_independent_self_contained_skill_copies(
    target: TargetTool, emitter: object, tmp_path: Path
) -> None:
    ir = parse_claude_plugin(FIXTURE)
    result = emitter.emit(ir)  # type: ignore[union-attr]
    assert not result.has_errors()
    result.write_to(tmp_path)

    alpha, beta = _skill_roots(target)
    for root in (alpha, beta):
        skill_md = (tmp_path / root / "SKILL.md").read_text()
        assert "x-ai-config-includes" not in skill_md
        assert "CLAUDE_PLUGIN_ROOT" not in skill_md
        assert "_shared/shared/data.txt" in skill_md
        assert (tmp_path / root / "_shared/shared/data.txt").read_bytes() == (
            FIXTURE / "shared/data.txt"
        ).read_bytes()
        assert (tmp_path / root / "_shared/shared/blob.bin").read_bytes() == (
            FIXTURE / "shared/blob.bin"
        ).read_bytes()
        assert os.access(tmp_path / root / "_shared/shared/run.sh", os.X_OK)
    assert (tmp_path / alpha / "_shared/shared/data.txt") != (
        tmp_path / beta / "_shared/shared/data.txt"
    )
    assert all(
        mapping.status == MappingStatus.TRANSFORM
        for mapping in result.mappings
        if mapping.component_kind == "skill"
    )
    assert len(result.include_evidence) == 8
    dependency = next(
        item
        for item in result.include_evidence
        if item.consumer_skill == "alpha" and item.source_relative_path.endswith("dependency.json")
    )
    assert dependency.direct_rewrite_count == 0
    assert dependency.copy_count == 1


@pytest.mark.parametrize(
    ("target", "emitter"),
    [
        (TargetTool.CODEX, CodexEmitter()),
        (TargetTool.CURSOR, CursorEmitter()),
        (TargetTool.OPENCODE, OpenCodeEmitter()),
        (TargetTool.PI, PiEmitter()),
    ],
)
def test_target_native_skill_override_rechecks_invariants_and_updates_evidence(
    target: TargetTool, emitter: object, tmp_path: Path
) -> None:
    plugin = tmp_path / "plugin"
    shutil.copytree(FIXTURE, plugin)
    native_skill = plugin / _target_native_alpha_skill(target) / "SKILL.md"
    native_skill.parent.mkdir(parents=True)
    native_skill.write_text(
        "---\nname: "
        + ("alpha" if target == TargetTool.CODEX else "shared-includes-alpha")
        + "\ndescription: native safe override\n---\n\nRead `_shared/shared/data.txt`.\n"
    )
    result = emitter.emit(parse_claude_plugin(plugin))  # type: ignore[union-attr]
    assert not result.has_errors()
    alpha_evidence = [item for item in result.include_evidence if item.consumer_skill == "alpha"]
    assert alpha_evidence
    assert all(item.direct_rewrite_count == 0 for item in alpha_evidence)

    native_skill.write_text(
        "---\nname: unsafe\ndescription: unsafe\nx-ai-config-includes: [shared/data.txt]\n"
        "---\n\n${CLAUDE_PLUGIN_ROOT}/shared/data.txt\n"
    )
    unsafe = emitter.emit(parse_claude_plugin(plugin))  # type: ignore[union-attr]
    assert unsafe.has_errors()
    assert any("build metadata" in item.message for item in unsafe.diagnostics)
    assert any("CLAUDE_PLUGIN_ROOT" in item.message for item in unsafe.diagnostics)


def test_target_native_shared_override_removes_original_copy_evidence(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    shutil.copytree(FIXTURE, plugin)
    native = plugin / "targets/pi/skills/shared-includes-alpha/_shared/shared/data.txt"
    native.parent.mkdir(parents=True)
    native.write_text("native payload")
    result = PiEmitter().emit(parse_claude_plugin(plugin))
    target = Path(".pi/skills/shared-includes-alpha/_shared/shared/data.txt")
    emitted = next(item for item in result.files if item.path == target)
    assert emitted.content == "native payload"
    assert not any(item.target_path == target for item in result.include_evidence)


def test_nested_markdown_rewrites_from_skill_root_not_nested_file(tmp_path: Path) -> None:
    plugin = _plugin(
        tmp_path,
        ["shared/data.txt"],
        "body",
    )
    (plugin / "shared").mkdir()
    (plugin / "shared/data.txt").write_text("data")
    nested = plugin / "skills/bad/references/guide.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("`${CLAUDE_PLUGIN_ROOT}/shared/data.txt`")
    result = PiEmitter().emit(parse_claude_plugin(plugin))
    emitted = next(item for item in result.files if item.path.name == "guide.md")
    assert emitted.content == "`_shared/shared/data.txt`"


@pytest.mark.parametrize(
    "invalid",
    [
        "",
        ".",
        "../outside.txt",
        "/tmp/outside.txt",
        "shared\\data.txt",
        "./shared/data.txt",
        "shared//data.txt",
        "shared/./data.txt",
        "shared/missing.txt",
        "shared/*.txt",
        "shared/bad\0name",
        3,
    ],
)
def test_invalid_include_paths_fail_and_best_effort_isolates_safe_skill(
    invalid: object, tmp_path: Path
) -> None:
    plugin = _plugin(tmp_path, [invalid])
    ir = parse_claude_plugin(plugin)
    assert ir.has_errors()
    assert [skill.name for skill in ir.skills()] == ["good"]

    output = tmp_path / "out"
    report = convert_plugin(
        plugin,
        [TargetTool.PI],
        output_dir=output,
        best_effort=True,
    )[TargetTool.PI]
    assert report.errors
    assert (output / ".pi/skills/safe-plugin-good/SKILL.md").is_file()
    assert not (output / ".pi/skills/safe-plugin-bad").exists()


def test_duplicate_collision_and_undeclared_placeholder_are_blocking(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path, ["shared/data.txt", "shared/data.txt"])
    (plugin / "shared").mkdir()
    (plugin / "shared/data.txt").write_text("data")
    assert any(
        "duplicate include" in item.message for item in parse_claude_plugin(plugin).diagnostics
    )

    bad_skill = plugin / "skills/bad/SKILL.md"
    bad_skill.write_text(
        "---\nname: bad\ndescription: bad\nx-ai-config-includes: [shared/data.txt]\n---\n\n"
        "`${CLAUDE_PLUGIN_ROOT}/shared/other.txt`"
    )
    assert any(
        "reference remains" in item.message for item in parse_claude_plugin(plugin).diagnostics
    )

    bad_skill.write_text(
        "---\nname: bad\ndescription: bad\nx-ai-config-includes: [shared/data.txt]\n---\nbody"
    )
    collision = plugin / "skills/bad/_shared/shared/data.txt"
    collision.parent.mkdir(parents=True)
    collision.write_text("collision")
    assert any("collides" in item.message for item in parse_claude_plugin(plugin).diagnostics)


def test_include_directory_is_rejected(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path, ["shared"])
    (plugin / "shared").mkdir()
    assert any(
        "not a regular file" in item.message for item in parse_claude_plugin(plugin).diagnostics
    )


def test_include_hardlink_is_rejected(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path, ["shared/data.txt"])
    (plugin / "shared").mkdir()
    original = plugin / "shared/original.txt"
    original.write_text("data")
    os.link(original, plugin / "shared/data.txt")
    assert any("hardlink" in item.message for item in parse_claude_plugin(plugin).diagnostics)


def test_component_absolute_traversal_and_malformed_paths_are_rejected(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    for value in ("../outside", "/tmp/outside", "skills/bad\0name", 7):
        (plugin / ".claude-plugin/plugin.json").write_text(
            json.dumps({"name": "unsafe", "commands": value})
        )
        ir = parse_claude_plugin(plugin)
        assert ir.has_errors()
        assert not ir.commands()


def test_final_and_ancestor_symlinks_are_not_read(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("---\nname: bad\ndescription: bad\n---\noutside")
    plugin = _plugin(tmp_path, [])
    (plugin / "skills/bad/SKILL.md").unlink()
    (plugin / "skills/bad/SKILL.md").symlink_to(outside)
    ir = parse_claude_plugin(plugin)
    assert ir.has_errors()
    assert [skill.name for skill in ir.skills()] == ["good"]

    shutil.rmtree(plugin / "skills/bad")
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    (external_dir / "SKILL.md").write_text("---\nname: bad\ndescription: bad\n---\noutside")
    (plugin / "skills/bad").symlink_to(external_dir, target_is_directory=True)
    ir = parse_claude_plugin(plugin)
    assert ir.has_errors()
    assert [skill.name for skill in ir.skills()] == ["good"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unavailable")
def test_special_file_in_skill_is_rejected(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path, [])
    os.mkfifo(plugin / "skills/bad/pipe")
    ir = parse_claude_plugin(plugin)
    assert ir.has_errors()
    assert [skill.name for skill in ir.skills()] == ["good"]


def test_hash_includes_shared_bytes_and_fails_closed_on_symlink(tmp_path: Path) -> None:
    plugin = _plugin(tmp_path, ["shared/data.txt"])
    (plugin / "shared").mkdir()
    shared = plugin / "shared/data.txt"
    shared.write_text("one")
    before = compute_plugin_hash(plugin)
    shared.write_text("two")
    assert compute_plugin_hash(plugin) != before
    (plugin / "unsafe").symlink_to(tmp_path / "outside")
    assert compute_plugin_hash(plugin) is None


def test_cache_v7_is_invalidated_for_complete_source_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    cache = tmp_path / ".ai-config/cache/conversion-hashes.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        json.dumps(
            {
                "version": 7,
                "entries": {"old": {}},
                "codex_output_dirs": ["/custom/codex"],
                "pi_output_dirs": ["/custom/pi"],
            }
        )
    )
    loaded = load_conversion_cache()
    assert loaded == {
        "version": 8,
        "entries": {},
        "codex_output_dirs": ["/custom/codex"],
        "pi_output_dirs": ["/custom/pi"],
    }


def test_cache_v7_rejects_invalid_preserved_output_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    cache = tmp_path / ".ai-config/cache/conversion-hashes.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        json.dumps(
            {
                "version": 7,
                "entries": {},
                "codex_output_dirs": ["/valid"],
                "pi_output_dirs": ["bad\0root"],
            }
        )
    )
    with pytest.raises(ValueError, match="Invalid conversion cache Pi output roots"):
        load_conversion_cache()


def test_codex_support_file_rejects_ancestor_symlink(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "run.sh").write_text("#!/bin/sh\n")
    (plugin / "scripts").symlink_to(outside, target_is_directory=True)
    ir = PluginIR(
        identity=PluginIdentity(plugin_id="unsafe", name="unsafe"),
        source_path=plugin,
        components=[
            McpServer(
                name="unsafe",
                command="sh",
                args=["${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"],
            )
        ],
    )
    result = CodexEmitter().emit(ir)
    assert result.has_errors()
    assert not any(item.path.as_posix().endswith("scripts/run.sh") for item in result.files)


def test_pi_ledger_owns_copies_and_preserves_tampered_stale_include(tmp_path: Path) -> None:
    plugin = tmp_path / "source"
    shutil.copytree(FIXTURE, plugin)
    output = tmp_path / "output"
    convert_plugin(plugin, [TargetTool.PI], output_dir=output)
    alpha, beta = _skill_roots(TargetTool.PI)
    alpha_copy = alpha / "_shared/shared/data.txt"
    beta_copy = beta / "_shared/shared/data.txt"
    ownership = load_pi_ownership(output)
    assert alpha_copy in ownership
    assert beta_copy in ownership

    (output / alpha_copy).write_text("local edit")
    _remove_include_metadata(plugin)
    convert_plugin(plugin, [TargetTool.PI], output_dir=output)
    assert (output / alpha_copy).read_text() == "local edit"
    assert not (output / beta_copy).exists()


@pytest.mark.parametrize("target", [TargetTool.CURSOR, TargetTool.OPENCODE])
def test_unowned_targets_do_not_delete_removed_include_copies(
    target: TargetTool, tmp_path: Path
) -> None:
    plugin = tmp_path / "source"
    shutil.copytree(FIXTURE, plugin)
    output = tmp_path / "output"
    convert_plugin(plugin, [target], output_dir=output)
    alpha, _beta = _skill_roots(target)
    old_copy = output / alpha / "_shared/shared/data.txt"
    assert old_copy.is_file()
    _remove_include_metadata(plugin)
    convert_plugin(plugin, [target], output_dir=output)
    assert old_copy.is_file()


def test_codex_removed_include_copy_stays_within_rebuilt_package_root(tmp_path: Path) -> None:
    plugin = tmp_path / "source"
    shutil.copytree(FIXTURE, plugin)
    output = tmp_path / "output"
    unrelated = output / "keep.txt"
    unrelated.parent.mkdir()
    unrelated.write_text("keep")
    convert_plugin(plugin, [TargetTool.CODEX], output_dir=output)
    alpha, _beta = _skill_roots(TargetTool.CODEX)
    old_copy = output / alpha / "_shared/shared/data.txt"
    assert old_copy.is_file()
    _remove_include_metadata(plugin)
    convert_plugin(plugin, [TargetTool.CODEX], output_dir=output)
    assert not old_copy.exists()
    assert unrelated.read_text() == "keep"


def test_report_contains_additive_relative_include_evidence(tmp_path: Path) -> None:
    report = convert_plugin(FIXTURE, [TargetTool.CURSOR], output_dir=tmp_path)[TargetTool.CURSOR]
    assert len(report.includes) == 8
    payload = report.to_dict()["includes"]
    assert payload[0]["source"] == "shared/data.txt"
    assert not Path(payload[0]["source"]).is_absolute()
    assert payload[0]["copy_count"] == 1
    assert payload[0]["duplicated_bytes"] == len((FIXTURE / "shared/data.txt").read_bytes())
    markdown = report.to_markdown()
    assert f"{payload[0]['copy_count']} copy" in markdown
    assert f"{payload[0]['duplicated_bytes']:,} bytes" in markdown
    assert f"{payload[0]['direct_rewrite_count']} direct rewrites" in markdown


def test_target_validator_invariants_reject_build_metadata_and_root_placeholder(
    tmp_path: Path,
) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("`${CLAUDE_PLUGIN_ROOT}/shared/data.txt`")
    errors = generated_skill_invariant_errors(
        skill, {"name": "skill", "x-ai-config-includes": ["shared/data.txt"]}
    )
    assert any("build metadata" in message for message in errors)
    assert any("CLAUDE_PLUGIN_ROOT" in message for message in errors)


@pytest.mark.parametrize(
    ("target", "validator"),
    [
        (TargetTool.CODEX, CodexOutputValidator()),
        (TargetTool.CURSOR, CursorOutputValidator()),
        (TargetTool.OPENCODE, OpenCodeOutputValidator()),
        (TargetTool.PI, PiOutputValidator()),
    ],
)
def test_shared_resource_output_passes_each_target_validator(
    target: TargetTool, validator: object, tmp_path: Path
) -> None:
    report = convert_plugin(FIXTURE, [target], output_dir=tmp_path)[target]
    assert not report.errors
    results = validator.validate_all(tmp_path)  # type: ignore[union-attr]
    assert not [result for result in results if result.status == "fail"]


def test_skill_without_include_metadata_retains_native_projection() -> None:
    ir = parse_claude_plugin(Path(__file__).parents[2] / "fixtures/sample-plugins/complete-plugin")
    result = CursorEmitter().emit(ir)
    assert not result.include_evidence
    assert all("_shared" not in item.path.parts for item in result.files)
    assert all(
        item.status == MappingStatus.NATIVE
        for item in result.mappings
        if item.component_kind == "skill"
    )
