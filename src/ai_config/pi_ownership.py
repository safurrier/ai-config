"""Fail-closed ownership ledger and reconciliation for generated Pi output."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ai_config.output_safety import validated_output_path

_PI_STATE = Path(".ai-config") / "pi-ownership.json"
_VERSION = 1


@dataclass(frozen=True)
class PiOwnedFile:
    source_plugin: str
    relative_path: Path
    digest: str


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


def load_pi_ownership(root: Path) -> dict[Path, PiOwnedFile]:
    """Load a ledger only when it proves ownership of this exact target root."""
    root = root.expanduser().resolve()
    path = _state_path(root)
    if not path.exists():
        return {}
    if path.is_symlink():
        raise ValueError(f"Refusing symlinked Pi ownership state: {path}")
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid Pi ownership state at {path}: {error}") from error
    if (
        not isinstance(payload, dict)
        or payload.get("version") != _VERSION
        or payload.get("root") != str(root)
    ):
        raise ValueError(f"Invalid Pi ownership state at {path}; refusing ambiguous cleanup")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        raise ValueError(f"Invalid Pi ownership files at {path}")
    owned: dict[Path, PiOwnedFile] = {}
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid Pi ownership entry at {path}")
        source, relative, digest = raw.get("source_plugin"), raw.get("path"), raw.get("digest")
        if not all(isinstance(value, str) and value for value in (source, relative, digest)):
            raise ValueError(f"Incomplete Pi ownership entry at {path}")
        relative_path = _safe_relative(Path(relative))
        if relative_path in owned or len(digest) != 64:
            raise ValueError(f"Ambiguous Pi ownership entry at {path}")
        validated_output_path(root, relative_path)
        owned[relative_path] = PiOwnedFile(source, relative_path, digest)
    return owned


def plan_pi_reconciliation(
    root: Path, desired: list[PiDesiredFile]
) -> tuple[list[PiAction], dict[Path, PiOwnedFile]]:
    """Plan Pi changes without modifying disk; never adopt unowned output."""
    root = root.expanduser().resolve()
    previous = load_pi_ownership(root)
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
        if path.exists() and path.is_symlink():
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
        elif old is not None and path.exists() and old.digest == item.digest:
            actions.append(PiAction("noop_pi_output", relative, "Owned output already matches"))
            next_state[relative] = PiOwnedFile(item.source_plugin, relative, item.digest)
        else:
            actions.append(
                PiAction(
                    "update_pi_output" if old else "create_pi_output",
                    relative,
                    "Generated Pi output changed",
                )
            )
            next_state[relative] = PiOwnedFile(item.source_plugin, relative, item.digest)
    for relative, old in sorted(previous.items(), key=lambda pair: pair[0].as_posix()):
        if relative in desired_by_path:
            continue
        path = validated_output_path(root, relative)
        if path.exists() and (path.is_symlink() or digest_content(path.read_bytes()) != old.digest):
            actions.append(
                PiAction("preserve_pi_output", relative, "Locally modified owned output")
            )
            next_state[relative] = old
        else:
            actions.append(
                PiAction("remove_pi_output", relative, "Pi source or target was removed")
            )
    return actions, next_state


def _write_state(root: Path, entries: dict[Path, PiOwnedFile]) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _VERSION,
        "root": str(root.expanduser().resolve()),
        "files": [
            {
                "source_plugin": entry.source_plugin,
                "path": entry.relative_path.as_posix(),
                "digest": entry.digest,
            }
            for _, entry in sorted(entries.items(), key=lambda pair: pair[0].as_posix())
        ],
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def apply_pi_reconciliation(
    root: Path, desired: list[PiDesiredFile], *, dry_run: bool = False
) -> list[PiAction]:
    """Reconcile and checkpoint only after all planned filesystem mutations succeed."""
    root = root.expanduser().resolve()
    actions, next_state = plan_pi_reconciliation(root, desired)
    if dry_run:
        return actions
    desired_by_path = {item.relative_path: item for item in desired}
    for action in actions:
        path = validated_output_path(root, action.path)
        if action.action in {"create_pi_output", "update_pi_output"}:
            item = desired_by_path[action.path]
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".ai-config-tmp")
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()
            temporary.write_bytes(item.content)
            if item.executable:
                temporary.chmod(temporary.stat().st_mode | 0o111)
            os.replace(temporary, path)
        elif action.action == "remove_pi_output":
            path.unlink(missing_ok=True)
    _write_state(root, next_state)
    return actions
