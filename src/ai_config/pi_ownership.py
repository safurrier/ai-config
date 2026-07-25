"""Fail-closed ownership ledger and crash-safe reconciliation for generated Pi output."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from ai_config.output_safety import validated_output_path

_PI_STATE = Path(".ai-config") / "pi-ownership.json"
_PI_PENDING = Path(".ai-config") / "pi-ownership.pending.json"
_VERSION = 3
PiOwnershipDomain = Literal["standalone", "sync"]
_STANDALONE_SOURCE = re.compile(r"standalone:([^:\s]+):([0-9a-f]{64})$")


@dataclass(frozen=True)
class PiOwnedFile:
    source_plugin: str
    relative_path: Path
    digest: str
    executable: bool = False


@dataclass(frozen=True)
class PiDesiredFile:
    source_plugin: str
    relative_path: Path
    content: bytes
    executable: bool = False

    @property
    def digest(self) -> str:
        return digest_content(self.content)


@dataclass(frozen=True)
class PiAction:
    action: Literal[
        "create_pi_output",
        "update_pi_output",
        "remove_pi_output",
        "noop_pi_output",
        "preserve_pi_output",
    ]
    path: Path
    reason: str


@dataclass(frozen=True)
class _DiskState:
    exists: bool
    digest: str | None = None
    executable: bool | None = None


def digest_content(content: bytes | str) -> str:
    return hashlib.sha256(content.encode() if isinstance(content, str) else content).hexdigest()


def standalone_pi_source_identity(plugin_path: Path, plugin_id: str) -> str:
    """Return a path-stable ledger owner for one standalone plugin source."""
    if not plugin_id or any(char.isspace() or char == ":" for char in plugin_id):
        raise ValueError(f"Invalid standalone Pi source plugin identity: {plugin_id!r}")
    resolved_path = plugin_path.expanduser().resolve()
    path_digest = hashlib.sha256(str(resolved_path).encode()).hexdigest()
    return f"standalone:{plugin_id}:{path_digest}"


def pi_ownership_domain(source_plugin: str) -> PiOwnershipDomain:
    """Classify and strictly validate one Pi ledger source identity."""
    if _STANDALONE_SOURCE.fullmatch(source_plugin):
        return "standalone"
    if source_plugin.startswith("standalone:"):
        raise ValueError(f"Invalid standalone Pi ownership identity: {source_plugin!r}")
    if (
        not source_plugin
        or source_plugin.count("@") > 1
        or source_plugin.startswith("@")
        or source_plugin.endswith("@")
        or any(char.isspace() or char == ":" for char in source_plugin)
    ):
        raise ValueError(f"Invalid sync Pi ownership identity: {source_plugin!r}")
    return "sync"


def _validate_ownership_domain(
    entries: dict[Path, PiOwnedFile],
    desired: dict[Path, PiDesiredFile],
    requested_domain: PiOwnershipDomain | None,
) -> None:
    existing_domains = {pi_ownership_domain(entry.source_plugin) for entry in entries.values()}
    desired_domains = {pi_ownership_domain(item.source_plugin) for item in desired.values()}
    if len(existing_domains) > 1 or len(desired_domains) > 1:
        raise ValueError(
            "Mixed Pi ownership domains are invalid; refusing ambiguous reconciliation"
        )
    expected = requested_domain or next(iter(desired_domains), None)
    if expected is not None and existing_domains and existing_domains != {expected}:
        existing = next(iter(existing_domains))
        raise ValueError(
            f"Pi output ownership domain conflict: this root is {existing}-managed, not "
            f"{expected}-managed. Use a separate root or remove/reconcile the standalone "
            "projection deliberately before retrying."
        )
    if requested_domain is not None and desired_domains and desired_domains != {requested_domain}:
        raise ValueError("Pi desired output ownership domain does not match reconciliation mode")


def _safe_relative(path: Path) -> Path:
    # Path normalizes harmless ``.`` components; reject lexical traversal before it can escape.
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Invalid Pi owned relative path: {path}")
    return Path(*[part for part in path.parts if part not in {"", "."}])


def _state_path(root: Path) -> Path:
    return validated_output_path(root, _PI_STATE)


def _pending_path(root: Path) -> Path:
    return validated_output_path(root, _PI_PENDING)


def _decode_entries(
    raw_files: object, path: Path, root: Path, *, allow_v1: bool = False
) -> dict[Path, PiOwnedFile]:
    if not isinstance(raw_files, list):
        raise ValueError(f"Invalid Pi ownership files at {path}")
    owned: dict[Path, PiOwnedFile] = {}
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid Pi ownership entry at {path}")
        raw = cast(dict[str, object], raw)
        source, relative, digest = raw.get("source_plugin"), raw.get("path"), raw.get("digest")
        executable = raw.get("executable", False if allow_v1 else None)
        if not all(
            isinstance(value, str) and value for value in (source, relative, digest)
        ) or not isinstance(executable, bool):
            raise ValueError(f"Incomplete Pi ownership entry at {path}")
        pi_ownership_domain(cast(str, source))
        if len(cast(str, digest)) != 64 or any(
            char not in "0123456789abcdef" for char in cast(str, digest)
        ):
            raise ValueError(f"Incomplete Pi ownership entry at {path}")
        relative_path = _safe_relative(Path(cast(str, relative)))
        validated_output_path(root, relative_path)
        if relative_path in owned:
            raise ValueError(f"Ambiguous Pi ownership entry at {path}")
        owned[relative_path] = PiOwnedFile(
            cast(str, source), relative_path, cast(str, digest), executable
        )
    return owned


def _load_json(path: Path, label: str) -> dict[str, object] | None:
    if path.is_symlink():
        raise ValueError(f"Refusing symlinked Pi {label}: {path}")
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid Pi {label} at {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid Pi {label} at {path}")
    return payload


def load_pi_ownership(root: Path) -> dict[Path, PiOwnedFile]:
    root = root.expanduser().resolve()
    path = _state_path(root)
    payload = _load_json(path, "ownership state")
    if payload is None:
        return {}
    version = payload.get("version")
    if version not in {1, 2, _VERSION} or payload.get("root") != str(root):
        raise ValueError(f"Invalid Pi ownership state at {path}; refusing ambiguous cleanup")
    # Version 1 predates executable-mode ownership. Later schemas must carry it
    # explicitly so malformed state never makes cleanup decisions for us.
    return _decode_entries(payload.get("files"), path, root, allow_v1=version == 1)


def _entry_payload(entries: dict[Path, PiOwnedFile]) -> list[dict[str, object]]:
    return [
        {
            "source_plugin": e.source_plugin,
            "path": e.relative_path.as_posix(),
            "digest": e.digest,
            "executable": e.executable,
        }
        for _, e in sorted(entries.items(), key=lambda p: p[0].as_posix())
    ]


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        # Only this process-created name is ever cleaned up.
        temporary.unlink(missing_ok=True)


def _write_state(root: Path, entries: dict[Path, PiOwnedFile]) -> None:
    _atomic_write(
        _state_path(root),
        {"version": _VERSION, "root": str(root), "files": _entry_payload(entries)},
    )


def _disk_state(root: Path, relative: Path) -> _DiskState:
    path = validated_output_path(root, relative)
    if path.is_symlink():
        raise ValueError(f"Refusing symlinked Pi output: {path}")
    if not path.exists():
        return _DiskState(False)
    if not path.is_file():
        raise ValueError(f"Pi output is not a regular file: {path}")
    return _DiskState(True, digest_content(path.read_bytes()), _is_executable(path))


def _state_payload(state: _DiskState) -> dict[str, object]:
    return {"exists": state.exists, "digest": state.digest, "executable": state.executable}


def _decode_disk_state(raw: object, path: Path) -> _DiskState:
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
    payload = cast(dict[str, object], raw)
    if not isinstance(payload.get("exists"), bool):
        raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
    exists = cast(bool, payload["exists"])
    digest, executable = payload.get("digest"), payload.get("executable")
    if not exists:
        if digest is not None or executable is not None:
            raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
        return _DiskState(False)
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
        or not isinstance(executable, bool)
    ):
        raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
    return _DiskState(True, digest, executable)


def _normalize_desired(root: Path, desired: list[PiDesiredFile]) -> dict[Path, PiDesiredFile]:
    result: dict[Path, PiDesiredFile] = {}
    for item in desired:
        relative = _safe_relative(item.relative_path)
        validated_output_path(root, relative)
        if relative in result:
            raise ValueError(f"Pi generated path collision: {relative}")
        result[relative] = PiDesiredFile(
            item.source_plugin, relative, item.content, item.executable
        )
    return result


def _write_pending(
    root: Path,
    actions: list[PiAction],
    next_state: dict[Path, PiOwnedFile],
    desired: dict[Path, PiDesiredFile],
    previous: dict[Path, PiOwnedFile],
) -> None:
    records = []
    for action in actions:
        # Record what was actually on disk, not merely what an older ledger claims.
        pre = _disk_state(root, action.path)
        post = (
            _DiskState(False)
            if action.path not in next_state
            else _DiskState(
                True, next_state[action.path].digest, next_state[action.path].executable
            )
        )
        # Preserve actions intentionally retain the observed local content, not ledger digest.
        if action.action == "preserve_pi_output":
            pre = post = _disk_state(root, action.path)
        records.append(
            {
                "action": action.action,
                "path": action.path.as_posix(),
                "reason": action.reason,
                "pre": _state_payload(pre),
                "post": _state_payload(post),
            }
        )
    _atomic_write(
        _pending_path(root),
        {
            "version": _VERSION,
            "root": str(root),
            "files": _entry_payload(next_state),
            "desired": _entry_payload(
                {
                    p: PiOwnedFile(d.source_plugin, p, d.digest, d.executable)
                    for p, d in desired.items()
                }
            ),
            "actions": records,
        },
    )


def _load_pending(
    root: Path,
) -> (
    tuple[
        list[PiAction],
        dict[Path, PiOwnedFile],
        dict[Path, PiOwnedFile],
        dict[Path, tuple[_DiskState, _DiskState]],
    ]
    | None
):
    path = _pending_path(root)
    payload = _load_json(path, "ownership pending transaction")
    if payload is None:
        return None
    if payload.get("version") != _VERSION or payload.get("root") != str(root):
        raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
    entries = _decode_entries(payload.get("files"), path, root)
    wanted = _decode_entries(payload.get("desired"), path, root)
    raw_actions = payload.get("actions")
    valid = {
        "create_pi_output",
        "update_pi_output",
        "remove_pi_output",
        "noop_pi_output",
        "preserve_pi_output",
    }
    if not isinstance(raw_actions, list):
        raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
    actions: list[PiAction] = []
    states: dict[Path, tuple[_DiskState, _DiskState]] = {}
    for raw in raw_actions:
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
        raw = cast(dict[str, object], raw)
        action, relative, reason = raw.get("action"), raw.get("path"), raw.get("reason")
        if (
            not isinstance(action, str)
            or action not in valid
            or not isinstance(relative, str)
            or not isinstance(reason, str)
        ):
            raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
        relative_path = _safe_relative(Path(relative))
        validated_output_path(root, relative_path)
        if relative_path in states:
            raise ValueError(f"Ambiguous Pi ownership pending transaction at {path}")
        states[relative_path] = (
            _decode_disk_state(raw.get("pre"), path),
            _decode_disk_state(raw.get("post"), path),
        )
        actions.append(
            PiAction(
                cast(
                    Literal[
                        "create_pi_output",
                        "update_pi_output",
                        "remove_pi_output",
                        "noop_pi_output",
                        "preserve_pi_output",
                    ],
                    action,
                ),
                relative_path,
                reason,
            )
        )
    # A journal is a complete, unambiguous state transition, not a bag of actions.
    if set(entries) != {a.path for a in actions if states[a.path][1].exists}:
        raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
    if not set(wanted).issubset(states) or any(
        action.action == "remove_pi_output" for action in actions if action.path in wanted
    ):
        raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
    return actions, entries, wanted, states


def _is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o111)


def plan_pi_reconciliation(
    root: Path,
    desired: list[PiDesiredFile],
    *,
    retained_sources: set[str] | None = None,
    ownership_domain: PiOwnershipDomain | None = None,
) -> tuple[list[PiAction], dict[Path, PiOwnedFile]]:
    root = root.expanduser().resolve()
    previous = load_pi_ownership(root)
    desired_by_path = _normalize_desired(root, desired)
    _validate_ownership_domain(previous, desired_by_path, ownership_domain)
    retained_sources = retained_sources or set()
    actions: list[PiAction] = []
    next_state: dict[Path, PiOwnedFile] = {}
    for relative, item in sorted(desired_by_path.items(), key=lambda p: p[0].as_posix()):
        path = validated_output_path(root, relative)
        old = previous.get(relative)
        if old is not None and old.source_plugin != item.source_plugin:
            raise ValueError(
                f"Pi output ownership collision at {path}; existing owner "
                f"'{old.source_plugin}' conflicts with requested owner '{item.source_plugin}'"
            )
        current = _disk_state(root, relative)
        if old is None and current.exists:
            raise ValueError(
                f"Unowned Pi output collision at {path}; refusing overwrite or ownership claim. Historical unowned output is untouched (see issue #22 migration)."
            )
        if old is not None and current.exists and current.digest != old.digest:
            actions.append(
                PiAction("preserve_pi_output", relative, "Locally modified owned output")
            )
            next_state[relative] = old
        elif (
            old is not None
            and current.exists
            and old.digest == item.digest
            and current.executable == item.executable
        ):
            actions.append(PiAction("noop_pi_output", relative, "Owned output already matches"))
            next_state[relative] = PiOwnedFile(
                item.source_plugin, relative, item.digest, item.executable
            )
        else:
            actions.append(
                PiAction(
                    "update_pi_output" if old else "create_pi_output",
                    relative,
                    "Generated Pi output changed",
                )
            )
            next_state[relative] = PiOwnedFile(
                item.source_plugin, relative, item.digest, item.executable
            )
    for relative, old in sorted(previous.items(), key=lambda p: p[0].as_posix()):
        if relative in desired_by_path:
            continue
        current = _disk_state(root, relative)
        if old.source_plugin in retained_sources:
            actions.append(
                PiAction("preserve_pi_output", relative, "Pi source is temporarily unavailable")
            )
            next_state[relative] = old
        elif current.exists and current.digest != old.digest:
            actions.append(
                PiAction("preserve_pi_output", relative, "Locally modified owned output")
            )
            next_state[relative] = old
        else:
            actions.append(
                PiAction("remove_pi_output", relative, "Pi source or target was removed")
            )
    return actions, next_state


def _prune_empty_owned_ancestors(root: Path, relative: Path) -> None:
    """Remove empty generated parents without crossing Pi's managed root boundary."""
    # User output lives below .pi/agent; project output lives directly below .pi.
    boundary = root / ".pi" / "agent" if relative.parts[:2] == (".pi", "agent") else root / ".pi"
    directory = validated_output_path(root, relative).parent
    while directory != boundary:
        if directory.is_symlink():
            raise ValueError(f"Refusing symlinked Pi output directory: {directory}")
        try:
            directory.rmdir()
        except FileNotFoundError:
            directory = directory.parent
        except OSError:
            # A user file (or another owned file) remains; never remove its directory.
            break
        else:
            directory = directory.parent


def _apply_actions(root: Path, actions: list[PiAction], desired: dict[Path, PiDesiredFile]) -> None:
    for action in actions:
        path = validated_output_path(root, action.path)
        if path.is_symlink():
            raise ValueError(f"Refusing symlinked Pi output: {path}")
        if action.action in {"create_pi_output", "update_pi_output"}:
            item = desired[action.path]
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".ai-config-tmp", dir=path.parent
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(item.content)
                temporary.chmod(0o755 if item.executable else 0o644)
                os.replace(temporary, path)
            finally:
                # Only this process-created name is ever cleaned up.
                temporary.unlink(missing_ok=True)
        elif action.action == "remove_pi_output":
            # State validation before this call proves this is the exact old owned file.
            path.unlink(missing_ok=True)
            _prune_empty_owned_ancestors(root, action.path)


def _recover_pending(
    root: Path, desired: dict[Path, PiDesiredFile], retained_sources: set[str]
) -> list[PiAction] | None:
    pending = _load_pending(root)
    if pending is None:
        return None
    actions, next_state, wanted, states = pending
    if set(desired) != set(wanted) or any(
        (d.source_plugin, d.digest, d.executable) != (w.source_plugin, w.digest, w.executable)
        for p, d in desired.items()
        for w in [wanted[p]]
    ):
        raise ValueError(
            "Pending Pi ownership transaction does not match current desired output; refusing unsafe recovery"
        )
    for action in actions:
        if action.action == "remove_pi_output" and action.path in desired:
            raise ValueError(
                "Pending Pi ownership transaction does not match current desired output; refusing unsafe recovery"
            )
        if action.action == "remove_pi_output":
            # Source id is encoded in the pre-state only in prior ledger semantics; a retained source
            # cannot be inferred safely, so callers with any unavailable source fail closed.
            if retained_sources:
                raise ValueError(
                    "Pending Pi ownership transaction has unavailable sources; refusing stale removal"
                )
        current = _disk_state(root, action.path)
        pre, post = states[action.path]
        if current != pre and current != post:
            raise ValueError(
                f"Pending Pi ownership transaction diverged at {action.path}; preserving user changes"
            )
    apply_now = [
        a
        for a in actions
        if _disk_state(root, a.path) == states[a.path][0] and states[a.path][0] != states[a.path][1]
    ]
    _apply_actions(root, apply_now, desired)
    _write_state(root, next_state)
    _pending_path(root).unlink()
    return actions


def apply_pi_reconciliation(
    root: Path,
    desired: list[PiDesiredFile],
    *,
    dry_run: bool = False,
    retained_sources: set[str] | None = None,
    ownership_domain: PiOwnershipDomain | None = None,
) -> list[PiAction]:
    root = root.expanduser().resolve()
    desired_by_path = _normalize_desired(root, desired)
    previous = load_pi_ownership(root)
    _validate_ownership_domain(previous, desired_by_path, ownership_domain)
    retained_sources = retained_sources or set()
    pending = _load_pending(root)
    if pending is not None:
        # Recovery validation is deliberately identical for preview and apply.
        if dry_run:
            _recover_pending_plan(root, desired_by_path, retained_sources, pending)
            return pending[0]
        recovered = _recover_pending(root, desired_by_path, retained_sources)
        if recovered is not None:
            return recovered
    actions, next_state = plan_pi_reconciliation(
        root,
        list(desired_by_path.values()),
        retained_sources=retained_sources,
        ownership_domain=ownership_domain,
    )
    if dry_run:
        return actions
    _write_pending(root, actions, next_state, desired_by_path, previous)
    _apply_actions(root, actions, desired_by_path)
    _write_state(root, next_state)
    _pending_path(root).unlink()
    return actions


def _recover_pending_plan(
    root: Path,
    desired: dict[Path, PiDesiredFile],
    retained_sources: set[str],
    pending: tuple[
        list[PiAction],
        dict[Path, PiOwnedFile],
        dict[Path, PiOwnedFile],
        dict[Path, tuple[_DiskState, _DiskState]],
    ],
) -> None:
    actions, _next, wanted, states = pending
    if set(desired) != set(wanted) or any(
        (d.source_plugin, d.digest, d.executable)
        != (wanted[p].source_plugin, wanted[p].digest, wanted[p].executable)
        for p, d in desired.items()
    ):
        raise ValueError(
            "Pending Pi ownership transaction does not match current desired output; refusing unsafe recovery"
        )
    for action in actions:
        if action.action == "remove_pi_output" and retained_sources:
            raise ValueError(
                "Pending Pi ownership transaction has unavailable sources; refusing stale removal"
            )
        current = _disk_state(root, action.path)
        if current != states[action.path][0] and current != states[action.path][1]:
            raise ValueError(
                f"Pending Pi ownership transaction diverged at {action.path}; preserving user changes"
            )
