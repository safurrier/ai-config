"""Fail-closed reads for files contained by a plugin source root."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class SourceSafetyError(ValueError):
    """A source path is malformed, escapes its root, or is unsafe to read."""


class SourceMissingError(SourceSafetyError):
    """A syntactically safe source path does not exist."""


@dataclass(frozen=True)
class SourceFile:
    """Bytes and mode read from one validated regular source file."""

    relative_path: PurePosixPath
    content: bytes
    executable: bool


def normalize_source_relative(value: object, *, context: str) -> PurePosixPath:
    """Validate one portable plugin-root-relative path value."""
    if not isinstance(value, str):
        raise SourceSafetyError(f"{context} path must be a string")
    if not value or "\\" in value:
        raise SourceSafetyError(
            f"{context} path must be a non-empty POSIX relative path: {value!r}"
        )
    while value.startswith("./"):
        value = value[2:]
    raw_parts = value.split("/")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or path == PurePosixPath(".") or ".." in raw_parts:
        raise SourceSafetyError(f"{context} path must stay within the plugin root: {value!r}")
    if any(part in {"", "."} for part in raw_parts):
        raise SourceSafetyError(f"{context} path contains an empty or dot component: {value!r}")
    return path


class ContainedSource:
    """Resolve and read source entries without following in-root symlinks."""

    def __init__(self, root: Path) -> None:
        supplied = root.expanduser().absolute()
        try:
            root_stat = supplied.lstat()
        except OSError as error:
            raise SourceSafetyError(
                f"Plugin source root is unreadable: {supplied}: {error}"
            ) from error
        if stat.S_ISLNK(root_stat.st_mode):
            raise SourceSafetyError(f"Plugin source root must not be a symlink: {supplied}")
        if not stat.S_ISDIR(root_stat.st_mode):
            raise SourceSafetyError(f"Plugin source root is not a directory: {supplied}")
        self.root = supplied.resolve(strict=True)

    def relative(self, value: object, *, context: str) -> PurePosixPath:
        return normalize_source_relative(value, context=context)

    def _lstat(self, relative: PurePosixPath, *, context: str) -> os.stat_result:
        current = self.root
        for index, part in enumerate(relative.parts):
            current = current / part
            try:
                item_stat = current.lstat()
            except FileNotFoundError as error:
                raise SourceMissingError(
                    f"{context} path does not exist: {relative.as_posix()}"
                ) from error
            except OSError as error:
                raise SourceSafetyError(
                    f"{context} path is unreadable: {relative.as_posix()}: {error}"
                ) from error
            if stat.S_ISLNK(item_stat.st_mode):
                raise SourceSafetyError(f"{context} path contains a symlink: {relative.as_posix()}")
            if index < len(relative.parts) - 1 and not stat.S_ISDIR(item_stat.st_mode):
                raise SourceSafetyError(
                    f"{context} path has a non-directory ancestor: {relative.as_posix()}"
                )
        return item_stat

    def kind(self, relative: PurePosixPath, *, context: str) -> str:
        """Return ``file`` or ``directory`` after validating every component."""
        item_stat = self._lstat(relative, context=context)
        if stat.S_ISREG(item_stat.st_mode):
            return "file"
        if stat.S_ISDIR(item_stat.st_mode):
            return "directory"
        raise SourceSafetyError(f"{context} path is not a regular file or directory: {relative}")

    def read_file(
        self,
        relative: PurePosixPath,
        *,
        context: str,
        reject_hardlinks: bool = False,
    ) -> SourceFile:
        """Read one validated regular file without accepting links or special files."""
        item_stat = self._lstat(relative, context=context)
        if not stat.S_ISREG(item_stat.st_mode):
            raise SourceSafetyError(f"{context} path is not a regular file: {relative}")
        if reject_hardlinks and item_stat.st_nlink != 1:
            raise SourceSafetyError(f"{context} path must not be a hardlink: {relative}")
        path = self.root.joinpath(*relative.parts)
        try:
            content = path.read_bytes()
            after = path.lstat()
        except OSError as error:
            raise SourceSafetyError(f"{context} path is unreadable: {relative}: {error}") from error
        if stat.S_ISLNK(after.st_mode) or not stat.S_ISREG(after.st_mode):
            raise SourceSafetyError(f"{context} path changed while being read: {relative}")
        if (item_stat.st_dev, item_stat.st_ino, item_stat.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ):
            raise SourceSafetyError(f"{context} path changed while being read: {relative}")
        return SourceFile(relative, content, bool(after.st_mode & 0o111))

    def walk_files(self, relative: PurePosixPath, *, context: str) -> Iterator[PurePosixPath]:
        """Yield regular files below a validated directory, rejecting unsafe entries."""
        if self.kind(relative, context=context) != "directory":
            raise SourceSafetyError(f"{context} path is not a directory: {relative}")

        def walk(directory: PurePosixPath) -> Iterator[PurePosixPath]:
            disk_dir = self.root.joinpath(*directory.parts)
            try:
                entries = sorted(os.scandir(disk_dir), key=lambda entry: entry.name)
            except OSError as error:
                raise SourceSafetyError(
                    f"{context} directory is unreadable: {directory}: {error}"
                ) from error
            for entry in entries:
                child = directory / entry.name
                try:
                    child_stat = entry.stat(follow_symlinks=False)
                except OSError as error:
                    raise SourceSafetyError(
                        f"{context} entry is unreadable: {child}: {error}"
                    ) from error
                if stat.S_ISLNK(child_stat.st_mode):
                    raise SourceSafetyError(f"{context} contains a symlink: {child}")
                if stat.S_ISDIR(child_stat.st_mode):
                    yield from walk(child)
                elif stat.S_ISREG(child_stat.st_mode):
                    yield child
                else:
                    raise SourceSafetyError(f"{context} contains a non-regular file: {child}")

        yield from walk(relative)

    def scan_files(
        self, relative: PurePosixPath, *, context: str
    ) -> tuple[list[PurePosixPath], list[str]]:
        """Collect safe files while isolating unsafe sibling entries."""
        if self.kind(relative, context=context) != "directory":
            raise SourceSafetyError(f"{context} path is not a directory: {relative}")
        files: list[PurePosixPath] = []
        errors: list[str] = []

        def scan(directory: PurePosixPath) -> None:
            disk_dir = self.root.joinpath(*directory.parts)
            try:
                entries = sorted(os.scandir(disk_dir), key=lambda entry: entry.name)
            except OSError as error:
                errors.append(f"{context} directory is unreadable: {directory}: {error}")
                return
            for entry in entries:
                child = directory / entry.name
                try:
                    child_stat = entry.stat(follow_symlinks=False)
                except OSError as error:
                    errors.append(f"{context} entry is unreadable: {child}: {error}")
                    continue
                if stat.S_ISLNK(child_stat.st_mode):
                    errors.append(f"{context} contains a symlink: {child}")
                elif stat.S_ISDIR(child_stat.st_mode):
                    scan(child)
                elif stat.S_ISREG(child_stat.st_mode):
                    files.append(child)
                else:
                    errors.append(f"{context} contains a non-regular file: {child}")

        scan(relative)
        return files, errors

    def walk_all_files(self, *, context: str) -> Iterator[PurePosixPath]:
        """Yield every regular file in the source root with the same safety rules."""
        for entry in sorted(os.scandir(self.root), key=lambda item: item.name):
            child = PurePosixPath(entry.name)
            item_stat = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(item_stat.st_mode):
                raise SourceSafetyError(f"{context} contains a symlink: {child}")
            if stat.S_ISDIR(item_stat.st_mode):
                yield from self.walk_files(child, context=context)
            elif stat.S_ISREG(item_stat.st_mode):
                yield child
            else:
                raise SourceSafetyError(f"{context} contains a non-regular file: {child}")
