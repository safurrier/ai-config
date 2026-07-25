import json
from pathlib import Path

import pytest

import ai_config.pi_ownership as ownership
from ai_config.pi_ownership import (
    PiDesiredFile,
    apply_pi_reconciliation,
    digest_content,
    load_pi_ownership,
    plan_pi_reconciliation,
)


def desired(path: str, content: str = "one") -> PiDesiredFile:
    return PiDesiredFile("demo@local", Path(path), content.encode())


def test_create_update_remove_and_noop_are_owned(tmp_path: Path) -> None:
    assert [a.action for a in apply_pi_reconciliation(tmp_path, [desired(".pi/a")])] == [
        "create_pi_output"
    ]
    assert load_pi_ownership(tmp_path)[Path(".pi/a")].digest == digest_content("one")
    assert [a.action for a in apply_pi_reconciliation(tmp_path, [desired(".pi/a")])] == [
        "noop_pi_output"
    ]
    assert [a.action for a in apply_pi_reconciliation(tmp_path, [desired(".pi/a", "two")])] == [
        "update_pi_output"
    ]
    assert [a.action for a in apply_pi_reconciliation(tmp_path, [])] == ["remove_pi_output"]


def test_unowned_collision_and_local_change_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / ".pi/a"
    path.parent.mkdir()
    path.write_text("manual")
    with pytest.raises(ValueError, match="Unowned Pi output collision"):
        plan_pi_reconciliation(tmp_path, [desired(".pi/a")])


def test_modified_owned_file_is_not_removed(tmp_path: Path) -> None:
    apply_pi_reconciliation(tmp_path, [desired(".pi/a")])
    (tmp_path / ".pi/a").write_text("manual")
    actions, state = plan_pi_reconciliation(tmp_path, [])
    assert actions[0].action == "preserve_pi_output"
    assert Path(".pi/a") in state


def test_rejects_traversal_and_symlink(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid Pi owned"):
        plan_pi_reconciliation(tmp_path, [desired("../outside")])
    (tmp_path / ".pi").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"):
        plan_pi_reconciliation(tmp_path, [desired(".pi/a")])


def test_rejects_dangling_final_symlinks_for_desired_and_obsolete(tmp_path: Path) -> None:
    path = tmp_path / ".pi/a"
    path.parent.mkdir()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="symlink"):
        plan_pi_reconciliation(tmp_path, [desired(".pi/a")])
    path.unlink()
    apply_pi_reconciliation(tmp_path, [desired(".pi/a")])
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError, match="symlink"):
        plan_pi_reconciliation(tmp_path, [])


@pytest.mark.parametrize("before, after", [(None, "one"), ("one", "two"), ("one", None)])
def test_checkpoint_failure_recovers_on_normal_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    before: str | None,
    after: str | None,
) -> None:
    if before is not None:
        apply_pi_reconciliation(tmp_path, [desired(".pi/a", before)])
    target = [] if after is None else [desired(".pi/a", after)]
    original_write_state = ownership._write_state
    monkeypatch.setattr(
        ownership, "_write_state", lambda root, entries: (_ for _ in ()).throw(OSError("nope"))
    )
    with pytest.raises(OSError, match="nope"):
        apply_pi_reconciliation(tmp_path, target)
    assert (tmp_path / ".ai-config/pi-ownership.pending.json").exists()
    monkeypatch.setattr(ownership, "_write_state", original_write_state)
    assert apply_pi_reconciliation(tmp_path, target)
    owned = load_pi_ownership(tmp_path)
    if after is None:
        assert Path(".pi/a") not in owned
        assert not (tmp_path / ".pi/a").exists()
    else:
        assert owned[Path(".pi/a")].digest == digest_content(after)
        assert (tmp_path / ".pi/a").read_text() == after


def test_pending_recovery_preserves_post_crash_user_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    apply_pi_reconciliation(tmp_path, [desired(".pi/update", "old"), desired(".pi/remove", "old")])
    original_write_state = ownership._write_state
    monkeypatch.setattr(
        ownership, "_write_state", lambda *_: (_ for _ in ()).throw(OSError("checkpoint"))
    )
    with pytest.raises(OSError, match="checkpoint"):
        apply_pi_reconciliation(
            tmp_path, [desired(".pi/create", "new"), desired(".pi/update", "new")]
        )
    monkeypatch.setattr(ownership, "_write_state", original_write_state)
    (tmp_path / ".pi/create").write_text("user create")
    (tmp_path / ".pi/update").write_text("user update")
    (tmp_path / ".pi/remove").write_text("user remove")
    with pytest.raises(ValueError, match="diverged"):
        apply_pi_reconciliation(
            tmp_path, [desired(".pi/create", "new"), desired(".pi/update", "new")]
        )
    with pytest.raises(ValueError, match="diverged"):
        apply_pi_reconciliation(
            tmp_path, [desired(".pi/create", "new"), desired(".pi/update", "new")], dry_run=True
        )
    assert (tmp_path / ".pi/create").read_text() == "user create"
    assert (tmp_path / ".pi/update").read_text() == "user update"
    assert (tmp_path / ".pi/remove").read_text() == "user remove"


def test_pending_recovery_rejects_changed_desired_and_unavailable_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_write_state = ownership._write_state
    monkeypatch.setattr(
        ownership, "_write_state", lambda *_: (_ for _ in ()).throw(OSError("checkpoint"))
    )
    with pytest.raises(OSError):
        apply_pi_reconciliation(tmp_path, [desired(".pi/a", "one")])
    monkeypatch.setattr(ownership, "_write_state", original_write_state)
    with pytest.raises(ValueError, match="does not match"):
        apply_pi_reconciliation(tmp_path, [desired(".pi/a", "changed")])
    with pytest.raises(ValueError, match="does not match"):
        apply_pi_reconciliation(tmp_path, [], retained_sources={"demo@local"})


def test_pending_and_ledger_entries_validate_root_and_temp_collisions_are_preserved(
    tmp_path: Path,
) -> None:
    state = tmp_path / ".ai-config/pi-ownership.json"
    state.parent.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".pi").symlink_to(outside)
    digest = digest_content("one")
    state.write_text(
        json.dumps(
            {
                "version": 3,
                "root": str(tmp_path.resolve()),
                "files": [
                    {"source_plugin": "x", "path": ".pi/a", "digest": digest, "executable": False}
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="symlink"):
        load_pi_ownership(tmp_path)
    (tmp_path / ".pi").unlink()
    reserved = tmp_path / ".ai-config/pi-ownership.json.tmp"
    reserved.write_text("user")
    apply_pi_reconciliation(tmp_path, [desired(".pi/a")])
    assert reserved.read_text() == "user"


@pytest.mark.parametrize("version", [2, 3])
def test_newer_ledger_versions_require_explicit_executable_mode(
    tmp_path: Path, version: int
) -> None:
    state = tmp_path / ".ai-config/pi-ownership.json"
    state.parent.mkdir()
    state.write_text(
        json.dumps(
            {
                "version": version,
                "root": str(tmp_path.resolve()),
                "files": [
                    {"source_plugin": "demo@local", "path": ".pi/a", "digest": digest_content("a")}
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="Incomplete Pi ownership entry"):
        load_pi_ownership(tmp_path)


def test_v1_ledger_defaults_missing_executable_mode(tmp_path: Path) -> None:
    state = tmp_path / ".ai-config/pi-ownership.json"
    state.parent.mkdir()
    state.write_text(
        json.dumps(
            {
                "version": 1,
                "root": str(tmp_path.resolve()),
                "files": [
                    {"source_plugin": "demo@local", "path": ".pi/a", "digest": digest_content("a")}
                ],
            }
        )
    )
    assert not load_pi_ownership(tmp_path)[Path(".pi/a")].executable


@pytest.mark.parametrize("base", [Path(".pi"), Path(".pi/agent")])
def test_removing_owned_files_prunes_empty_parents_but_keeps_pi_boundary_and_user_content(
    tmp_path: Path, base: Path
) -> None:
    owned = [
        desired((base / "skills/plugin-old/resources/reference.md").as_posix()),
        desired((base / "prompts/plugin-old.md").as_posix()),
        desired((base / "extensions/plugin-old/hook.ts").as_posix()),
    ]
    apply_pi_reconciliation(tmp_path, owned)
    user_file = tmp_path / base / "extensions/plugin-old/manual.txt"
    user_file.write_text("keep")
    apply_pi_reconciliation(tmp_path, [])

    assert not (tmp_path / base / "skills/plugin-old").exists()
    assert not (tmp_path / base / "prompts").exists()
    assert not (tmp_path / base / "extensions/plugin-old/hook.ts").exists()
    assert user_file.read_text() == "keep"
    assert (tmp_path / base / "extensions/plugin-old").is_dir()
    assert (tmp_path / base).is_dir()


def test_executable_mode_is_reconciled(tmp_path: Path) -> None:
    executable = PiDesiredFile("demo@local", Path(".pi/run"), b"echo ok", executable=True)
    apply_pi_reconciliation(tmp_path, [executable])
    assert (tmp_path / ".pi/run").stat().st_mode & 0o111
    (tmp_path / ".pi/run").chmod(0o644)
    assert apply_pi_reconciliation(tmp_path, [executable])[0].action == "update_pi_output"
    assert (tmp_path / ".pi/run").stat().st_mode & 0o111
