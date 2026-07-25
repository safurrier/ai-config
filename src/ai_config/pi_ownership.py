"""Fail-closed ownership ledger and reconciliation for generated Pi output."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from ai_config.output_safety import validated_output_path

_PI_STATE = Path(".ai-config") / "pi-ownership.json"
_PI_PENDING = Path(".ai-config") / "pi-ownership.pending.json"
_VERSION = 2


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


def digest_content(content: bytes | str) -> str:
    """Return the exact SHA-256 digest persisted for a generated file."""
    return hashlib.sha256(content.encode() if isinstance(content, str) else content).hexdigest()


def _safe_relative(path: Path) -> Path:
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Invalid Pi owned relative path: {path}")
    return path


def _state_path(root: Path) -> Path:
    return validated_output_path(root, _PI_STATE)


def _pending_path(root: Path) -> Path:
    return validated_output_path(root, _PI_PENDING)


def _decode_entries(
    raw_files: object, path: Path, *, allow_v1: bool = False
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
        source, relative, digest, executable = (
            cast(str, source),
            cast(str, relative),
            cast(str, digest),
            executable,
        )
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"Incomplete Pi ownership entry at {path}")
        relative_path = _safe_relative(Path(relative))
        if relative_path in owned:
            raise ValueError(f"Ambiguous Pi ownership entry at {path}")
        owned[relative_path] = PiOwnedFile(source, relative_path, digest, executable)
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
    """Load a ledger only when it proves ownership of this exact target root."""
    root = root.expanduser().resolve()
    path = _state_path(root)
    payload = _load_json(path, "ownership state")
    if payload is None:
        return {}
    version = payload.get("version")
    if version not in {1, _VERSION} or payload.get("root") != str(root):
        raise ValueError(f"Invalid Pi ownership state at {path}; refusing ambiguous cleanup")
    return _decode_entries(payload.get("files"), path, allow_v1=version == 1)


def _entry_payload(entries: dict[Path, PiOwnedFile]) -> list[dict[str, object]]:
    return [
        {
            "source_plugin": entry.source_plugin,
            "path": entry.relative_path.as_posix(),
            "digest": entry.digest,
            "executable": entry.executable,
        }
        for _, entry in sorted(entries.items(), key=lambda pair: pair[0].as_posix())
    ]


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _write_state(root: Path, entries: dict[Path, PiOwnedFile]) -> None:
    _atomic_write(
        _state_path(root),
        {
            "version": _VERSION,
            "root": str(root.expanduser().resolve()),
            "files": _entry_payload(entries),
        },
    )


def _write_pending(root: Path, actions: list[PiAction], entries: dict[Path, PiOwnedFile]) -> None:
    _atomic_write(
        _pending_path(root),
        {
            "version": _VERSION,
            "root": str(root),
            "files": _entry_payload(entries),
            "actions": [
                {"action": action.action, "path": action.path.as_posix(), "reason": action.reason}
                for action in actions
            ],
        },
    )


def _load_pending(root: Path) -> tuple[list[PiAction], dict[Path, PiOwnedFile]] | None:
    path = _pending_path(root)
    payload = _load_json(path, "ownership pending transaction")
    if payload is None:
        return None
    if payload.get("version") != _VERSION or payload.get("root") != str(root):
        raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
    entries = _decode_entries(payload.get("files"), path)
    raw_actions = payload.get("actions")
    valid_actions = {
        "create_pi_output",
        "update_pi_output",
        "remove_pi_output",
        "noop_pi_output",
        "preserve_pi_output",
    }
    if not isinstance(raw_actions, list):
        raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
    actions: list[PiAction] = []
    seen: set[Path] = set()
    for raw in raw_actions:
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
        raw = cast(dict[str, object], raw)
        action, relative, reason = raw.get("action"), raw.get("path"), raw.get("reason")
        if (
            not isinstance(action, str)
            or action not in valid_actions
            or not isinstance(relative, str)
            or not isinstance(reason, str)
        ):
            raise ValueError(f"Invalid Pi ownership pending transaction at {path}")
        safe = _safe_relative(Path(relative))
        validated_output_path(root, safe)
        if safe in seen:
            raise ValueError(f"Ambiguous Pi ownership pending transaction at {path}")
        seen.add(safe)
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
                safe,
                reason,
            )
        )
    return actions, entries


def _is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o111)


def plan_pi_reconciliation(
    root: Path, desired: list[PiDesiredFile], *, retained_sources: set[str] | None = None
) -> tuple[list[PiAction], dict[Path, PiOwnedFile]]:
    """Plan Pi changes without modifying disk; never adopt unowned output."""
    root = root.expanduser().resolve()
    previous = load_pi_ownership(root)
    retained_sources = retained_sources or set()
    desired_by_path: dict[Path, PiDesiredFile] = {}
    for item in desired:
        relative = _safe_relative(item.relative_path)
        validated_output_path(root, relative)
        if relative in desired_by_path:
            raise ValueError(f"Pi generated path collision: {relative}")
        desired_by_path[relative] = item
    actions: list[PiAction] = []
    next_state: dict[Path, PiOwnedFile] = {}
    for relative, item in sorted(desired_by_path.items(), key=lambda pair: pair[0].as_posix()):
        path = validated_output_path(root, relative)
        old = previous.get(relative)
        if path.is_symlink():
            raise ValueError(f"Refusing symlinked Pi output: {path}")
        if old is None and path.exists():
            raise ValueError(
                f"Unowned Pi output collision at {path}; refusing overwrite or ownership claim. "
                "Historical unowned output is untouched (see issue #22 migration)."
            )
        if old is not None and path.exists() and digest_content(path.read_bytes()) != old.digest:
            actions.append(
                PiAction("preserve_pi_output", relative, "Locally modified owned output")
            )
            next_state[relative] = old
        elif (
            old is not None
            and path.exists()
            and old.digest == item.digest
            and _is_executable(path) == item.executable
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
    for relative, old in sorted(previous.items(), key=lambda pair: pair[0].as_posix()):
        if relative in desired_by_path:
            continue
        if old.source_plugin in retained_sources:
            actions.append(
                PiAction("preserve_pi_output", relative, "Pi source is temporarily unavailable")
            )
            next_state[relative] = old
            continue
        path = validated_output_path(root, relative)
        if path.is_symlink():
            raise ValueError(f"Refusing symlinked Pi output: {path}")
        if path.exists() and digest_content(path.read_bytes()) != old.digest:
            actions.append(
                PiAction("preserve_pi_output", relative, "Locally modified owned output")
            )
            next_state[relative] = old
        else:
            actions.append(
                PiAction("remove_pi_output", relative, "Pi source or target was removed")
            )
    return actions, next_state


def _apply_actions(
    root: Path, actions: list[PiAction], desired_by_path: dict[Path, PiDesiredFile]
) -> None:
    for action in actions:
        path = validated_output_path(root, action.path)
        if path.is_symlink():
            raise ValueError(f"Refusing symlinked Pi output: {path}")
        if action.action in {"create_pi_output", "update_pi_output"}:
            item = desired_by_path[action.path]
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".ai-config-tmp")
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()
            temporary.write_bytes(item.content)
            temporary.chmod(0o755 if item.executable else 0o644)
            os.replace(temporary, path)
        elif action.action == "remove_pi_output":
            path.unlink(missing_ok=True)


def _recover_pending(
    root: Path, desired_by_path: dict[Path, PiDesiredFile]
) -> list[PiAction] | None:
    pending = _load_pending(root)
    if pending is None:
        return None
    actions, next_state = pending
    for action in actions:
        if action.action in {"create_pi_output", "update_pi_output", "noop_pi_output"}:
            item = desired_by_path.get(action.path)
            entry = next_state.get(action.path)
            if (
                item is None
                or entry is None
                or (item.source_plugin, item.digest, item.executable)
                != (entry.source_plugin, entry.digest, entry.executable)
            ):
                raise ValueError(
                    "Pending Pi ownership transaction does not match current desired output; refusing unsafe recovery"
                )
    _apply_actions(root, actions, desired_by_path)
    _write_state(root, next_state)
    _pending_path(root).unlink()
    return actions


def apply_pi_reconciliation(
    root: Path,
    desired: list[PiDesiredFile],
    *,
    dry_run: bool = False,
    retained_sources: set[str] | None = None,
) -> list[PiAction]:
    """Reconcile Pi output with a durable retryable transaction journal."""
    root = root.expanduser().resolve()
    desired_by_path = {item.relative_path: item for item in desired}
    if not dry_run:
        recovered = _recover_pending(root, desired_by_path)
        if recovered is not None:
            return recovered
    actions, next_state = plan_pi_reconciliation(root, desired, retained_sources=retained_sources)
    if dry_run:
        return actions
    _write_pending(root, actions, next_state)
    _apply_actions(root, actions, desired_by_path)
    _write_state(root, next_state)
    _pending_path(root).unlink()
    return actions
