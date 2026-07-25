from pathlib import Path

import pytest

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
    import ai_config.pi_ownership as ownership

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


def test_executable_mode_is_reconciled(tmp_path: Path) -> None:
    executable = PiDesiredFile("demo@local", Path(".pi/run"), b"echo ok", executable=True)
    apply_pi_reconciliation(tmp_path, [executable])
    assert (tmp_path / ".pi/run").stat().st_mode & 0o111
    (tmp_path / ".pi/run").chmod(0o644)
    assert apply_pi_reconciliation(tmp_path, [executable])[0].action == "update_pi_output"
    assert (tmp_path / ".pi/run").stat().st_mode & 0o111
