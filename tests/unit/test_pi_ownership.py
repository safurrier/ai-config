import json
from pathlib import Path
from typing import Literal

import pytest

import ai_config.pi_ownership as ownership
from ai_config.pi_ownership import (
    PiDesiredFile,
    apply_pi_reconciliation,
    digest_content,
    load_pi_ownership,
    plan_pi_reconciliation,
    standalone_pi_source_identity,
)


def desired(path: str, content: str = "one", owner: str = "demo@local") -> PiDesiredFile:
    return PiDesiredFile(owner, Path(path), content.encode())


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


def test_current_state_persists_explicit_domain(tmp_path: Path) -> None:
    apply_pi_reconciliation(tmp_path, [desired(".pi/a")], ownership_domain="sync")
    state = json.loads((tmp_path / ".ai-config/pi-ownership.json").read_text())
    assert state["version"] == 4
    assert state["domain"] == "sync"


def test_tampered_state_domain_is_rejected(tmp_path: Path) -> None:
    apply_pi_reconciliation(tmp_path, [desired(".pi/a")], ownership_domain="sync")
    state_path = tmp_path / ".ai-config/pi-ownership.json"
    state = json.loads(state_path.read_text())
    state["domain"] = "standalone"
    state_path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="domain does not match entry identity"):
        apply_pi_reconciliation(tmp_path, [], ownership_domain="standalone")


def test_non_overlapping_ownership_domains_reject_in_both_directions(tmp_path: Path) -> None:
    standalone_owner = standalone_pi_source_identity(tmp_path / "plugin", "standalone")
    apply_pi_reconciliation(
        tmp_path,
        [desired(".pi/standalone", owner=standalone_owner)],
        ownership_domain="standalone",
    )
    with pytest.raises(ValueError, match="ownership domain conflict.*separate root"):
        apply_pi_reconciliation(
            tmp_path,
            [desired(".pi/sync", owner="sync@local")],
            ownership_domain="sync",
        )

    other = tmp_path / "other"
    apply_pi_reconciliation(
        other, [desired(".pi/sync", owner="sync@local")], ownership_domain="sync"
    )
    with pytest.raises(ValueError, match="ownership domain conflict.*separate root"):
        apply_pi_reconciliation(
            other,
            [desired(".pi/standalone", owner=standalone_owner)],
            ownership_domain="standalone",
        )


def test_same_ownership_domain_allows_multiple_standalone_sources(tmp_path: Path) -> None:
    first = standalone_pi_source_identity(tmp_path / "first", "first")
    second = standalone_pi_source_identity(tmp_path / "second", "second")
    apply_pi_reconciliation(
        tmp_path, [desired(".pi/first", owner=first)], ownership_domain="standalone"
    )
    apply_pi_reconciliation(
        tmp_path,
        [desired(".pi/second", owner=second)],
        retained_sources={first},
        ownership_domain="standalone",
    )
    assert {entry.source_plugin for entry in load_pi_ownership(tmp_path).values()} == {
        first,
        second,
    }


def test_invalid_ledger_source_identity_is_rejected(tmp_path: Path) -> None:
    state = tmp_path / ".ai-config/pi-ownership.json"
    state.parent.mkdir()
    state.write_text(
        json.dumps(
            {
                "version": 4,
                "root": str(tmp_path.resolve()),
                "domain": "sync",
                "files": [
                    {
                        "source_plugin": "standalone:bad",
                        "path": ".pi/a",
                        "digest": digest_content("a"),
                        "executable": False,
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="Invalid standalone Pi ownership identity"):
        load_pi_ownership(tmp_path)


def test_ledger_owner_collision_rejects_same_domain_owner_reassignment(tmp_path: Path) -> None:
    first_owner = "first@marketplace"
    second_owner = "second@marketplace"
    apply_pi_reconciliation(
        tmp_path,
        [
            desired(".pi/first", owner=first_owner),
            desired(".pi/second", owner=second_owner),
        ],
        ownership_domain="sync",
    )

    for path, existing, requested in (
        (".pi/first", first_owner, second_owner),
        (".pi/second", second_owner, first_owner),
    ):
        with pytest.raises(ValueError, match="existing owner.*requested owner") as error:
            apply_pi_reconciliation(tmp_path, [desired(path, owner=requested)])
        assert existing in str(error.value)
        assert requested in str(error.value)


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
        ownership, "_write_state", lambda *_: (_ for _ in ()).throw(OSError("nope"))
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


@pytest.mark.parametrize("version", [1, 2, 3])
def test_old_pending_schema_refuses_recovery_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: int
) -> None:
    original_write_state = ownership._write_state
    monkeypatch.setattr(
        ownership, "_write_state", lambda *_: (_ for _ in ()).throw(OSError("checkpoint"))
    )
    with pytest.raises(OSError, match="checkpoint"):
        apply_pi_reconciliation(tmp_path, [desired(".pi/a")], ownership_domain="sync")
    monkeypatch.setattr(ownership, "_write_state", original_write_state)
    pending_path = tmp_path / ".ai-config/pi-ownership.pending.json"
    pending = json.loads(pending_path.read_text())
    pending["version"] = version
    pending_path.write_text(json.dumps(pending))
    with pytest.raises(ValueError, match="automatic cleanup is refused.*issue #22"):
        apply_pi_reconciliation(tmp_path, [desired(".pi/a")], ownership_domain="sync")
    assert (tmp_path / ".pi/a").read_text() == "one"


def test_pending_domain_mismatch_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_write_state = ownership._write_state
    monkeypatch.setattr(
        ownership, "_write_state", lambda *_: (_ for _ in ()).throw(OSError("checkpoint"))
    )
    with pytest.raises(OSError, match="checkpoint"):
        apply_pi_reconciliation(tmp_path, [desired(".pi/a")], ownership_domain="sync")
    monkeypatch.setattr(ownership, "_write_state", original_write_state)
    pending_path = tmp_path / ".ai-config/pi-ownership.pending.json"
    pending = json.loads(pending_path.read_text())
    pending["domain"] = "standalone"
    pending_path.write_text(json.dumps(pending))
    with pytest.raises(ValueError, match="domain does not match entry identity"):
        apply_pi_reconciliation(tmp_path, [desired(".pi/a")], ownership_domain="sync")


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
                "version": 4,
                "root": str(tmp_path.resolve()),
                "domain": "sync",
                "files": [
                    {
                        "source_plugin": "demo@local",
                        "path": ".pi/a",
                        "digest": digest,
                        "executable": False,
                    }
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


@pytest.mark.parametrize("version", [1, 2, 3])
@pytest.mark.parametrize(
    ("domain", "owner"),
    [("sync", "demo@local"), ("standalone", "standalone:demo:" + "a" * 64)],
)
def test_old_ledger_schema_refuses_cleanup_without_mutation(
    tmp_path: Path, version: int, domain: Literal["sync", "standalone"], owner: str
) -> None:
    state = tmp_path / ".ai-config/pi-ownership.json"
    output = tmp_path / ".pi/a"
    output.parent.mkdir(parents=True)
    output.write_text("historical")
    state.parent.mkdir()
    state.write_text(
        json.dumps(
            {
                "version": version,
                "root": str(tmp_path.resolve()),
                "files": [
                    {
                        "source_plugin": owner,
                        "path": ".pi/a",
                        "digest": digest_content("historical"),
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="automatic cleanup is refused.*issue #22"):
        apply_pi_reconciliation(tmp_path, [], ownership_domain=domain)
    assert output.read_text() == "historical"
    assert json.loads(state.read_text())["version"] == version


def test_final_removal_deletes_state_and_allows_new_domain(tmp_path: Path) -> None:
    apply_pi_reconciliation(tmp_path, [desired(".pi/a")], ownership_domain="sync")
    apply_pi_reconciliation(tmp_path, [], ownership_domain="sync")
    assert not (tmp_path / ".ai-config/pi-ownership.json").exists()
    standalone_owner = standalone_pi_source_identity(tmp_path / "plugin", "demo")
    apply_pi_reconciliation(
        tmp_path,
        [desired(".pi/standalone", owner=standalone_owner)],
        ownership_domain="standalone",
    )


def test_final_removal_checkpoint_failure_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    apply_pi_reconciliation(tmp_path, [desired(".pi/a")], ownership_domain="sync")
    original_write_state = ownership._write_state
    monkeypatch.setattr(
        ownership, "_write_state", lambda *_: (_ for _ in ()).throw(OSError("checkpoint"))
    )
    with pytest.raises(OSError, match="checkpoint"):
        apply_pi_reconciliation(tmp_path, [], ownership_domain="sync")
    assert (tmp_path / ".ai-config/pi-ownership.pending.json").exists()
    monkeypatch.setattr(ownership, "_write_state", original_write_state)
    apply_pi_reconciliation(tmp_path, [], ownership_domain="sync")
    assert not (tmp_path / ".ai-config/pi-ownership.json").exists()
    assert not (tmp_path / ".ai-config/pi-ownership.pending.json").exists()


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
