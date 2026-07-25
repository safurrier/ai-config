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


def test_checkpoint_is_atomic_on_state_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    apply_pi_reconciliation(tmp_path, [desired(".pi/a")])
    import ai_config.pi_ownership as ownership

    monkeypatch.setattr(
        ownership, "_write_state", lambda root, entries: (_ for _ in ()).throw(OSError("nope"))
    )
    with pytest.raises(OSError, match="nope"):
        apply_pi_reconciliation(tmp_path, [desired(".pi/a", "two")])
    # The old checkpoint remains, so a later run detects rather than falsely claiming convergence.
    assert load_pi_ownership(tmp_path)[Path(".pi/a")].digest == digest_content("one")
