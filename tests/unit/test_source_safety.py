"""Direct hostile-path tests for descriptor-contained plugin source reads."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

import pytest

import ai_config.source_safety as source_safety
from ai_config.path_policy import (
    GENERATED_PYTHON_ENVIRONMENT_DIRECTORY_NAMES,
    is_generated_python_artifact,
)
from ai_config.source_safety import ContainedSource, SourceSafetyError, normalize_source_relative


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (PurePosixPath("package/__pycache__/module.py"), True),
        (PurePosixPath("package/module.pyc"), True),
        (PurePosixPath("legacy.pyo"), True),
        (PurePosixPath("package/module.so"), False),
        (PurePosixPath("package/module.py"), False),
    ],
)
def test_generated_python_artifact_policy(path: PurePosixPath, expected: bool) -> None:
    assert is_generated_python_artifact(path) is expected


def test_normalization_rejects_nul_before_filesystem_use() -> None:
    with pytest.raises(SourceSafetyError, match="embedded NUL"):
        normalize_source_relative("shared/bad\0name", context="manifest")


def test_root_nul_is_translated_to_source_safety_error() -> None:
    with pytest.raises(SourceSafetyError, match="NUL|invalid"):
        ContainedSource(Path("bad\0root"))


@pytest.mark.parametrize(
    "invalid",
    [
        PurePosixPath("/outside"),
        PurePosixPath("../outside"),
        PurePosixPath("."),
        PurePosixPath(),
        PurePosixPath("bad\0name"),
    ],
)
@pytest.mark.parametrize("operation", ["kind", "read_file", "walk_files", "scan_files"])
def test_public_source_methods_reject_direct_unsafe_paths(
    invalid: PurePosixPath, operation: str, tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    with ContainedSource(root) as source:
        method = getattr(source, operation)
        with pytest.raises(SourceSafetyError):
            result = method(invalid, context="direct hostile path")
            if operation == "walk_files":
                list(result)


def test_close_is_idempotent_and_context_manager_closes_descriptor(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "payload").write_bytes(b"inside")
    source = ContainedSource(root)
    with source as opened:
        assert opened.kind(PurePosixPath("payload"), context="lifecycle") == "file"
    source.close()
    with pytest.raises(SourceSafetyError, match="closed"):
        source.kind(PurePosixPath("payload"), context="lifecycle")


def test_static_final_and_ancestor_symlinks_and_special_files_fail_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_bytes(b"outside")
    (root / "final").symlink_to(outside / "secret")
    (root / "ancestor").symlink_to(outside, target_is_directory=True)
    source = ContainedSource(root)

    for relative in (PurePosixPath("final"), PurePosixPath("ancestor/secret")):
        with pytest.raises(SourceSafetyError, match="symlink"):
            source.read_file(relative, context="hostile")

    if hasattr(os, "mkfifo"):
        os.mkfifo(root / "pipe")
        with pytest.raises(SourceSafetyError, match="regular"):
            source.read_file(PurePosixPath("pipe"), context="hostile")


def test_generated_environment_exclusion_only_skips_real_directories(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "payload").write_bytes(b"inside")
    venv = root / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin/python").symlink_to(tmp_path / "outside-python")

    with ContainedSource(root) as source:
        files, _mirrors = source.snapshot_files_and_context_mirrors(
            context="snapshot",
            excluded_directory_names=GENERATED_PYTHON_ENVIRONMENT_DIRECTORY_NAMES,
        )
    assert files == (PurePosixPath("payload"),)

    (venv / "bin/python").unlink()
    (venv / "bin").rmdir()
    venv.rmdir()
    # A same-named symlink is not generated content and must fail closed.
    venv.symlink_to(tmp_path / "outside", target_is_directory=True)
    with ContainedSource(root) as source, pytest.raises(SourceSafetyError, match="symlink: .venv"):
        source.snapshot_files_and_context_mirrors(
            context="snapshot",
            excluded_directory_names=GENERATED_PYTHON_ENVIRONMENT_DIRECTORY_NAMES,
        )

    venv.unlink()
    venv.write_bytes(b"ordinary file")
    with ContainedSource(root) as source:
        files, _mirrors = source.snapshot_files_and_context_mirrors(
            context="snapshot",
            excluded_directory_names=GENERATED_PYTHON_ENVIRONMENT_DIRECTORY_NAMES,
        )
    assert PurePosixPath(".venv") in files
    with ContainedSource(
        root, excluded_directory_names=GENERATED_PYTHON_ENVIRONMENT_DIRECTORY_NAMES
    ) as source:
        assert (
            source.read_file(PurePosixPath(".venv"), context="direct").content == b"ordinary file"
        )
    with (
        ContainedSource(
            root, excluded_directory_names=GENERATED_PYTHON_ENVIRONMENT_DIRECTORY_NAMES
        ) as source,
        pytest.raises(SourceSafetyError, match="non-directory ancestor"),
    ):
        source.read_file(PurePosixPath(".venv/child"), context="direct")

    if hasattr(os, "mkfifo"):
        venv.unlink()
        os.mkfifo(venv)
        with ContainedSource(root) as source, pytest.raises(SourceSafetyError, match="non-regular"):
            source.snapshot_files_and_context_mirrors(
                context="snapshot",
                excluded_directory_names=GENERATED_PYTHON_ENVIRONMENT_DIRECTORY_NAMES,
            )
        with (
            ContainedSource(
                root, excluded_directory_names=GENERATED_PYTHON_ENVIRONMENT_DIRECTORY_NAMES
            ) as source,
            pytest.raises(SourceSafetyError, match="regular"),
        ):
            source.read_file(PurePosixPath(".venv"), context="direct")


def test_retained_root_descriptor_defeats_ancestor_swap(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    root = parent / "root"
    root.mkdir(parents=True)
    (root / "payload").write_bytes(b"inside")
    source = ContainedSource(root)

    moved = tmp_path / "moved"
    parent.rename(moved)
    outside_parent = tmp_path / "outside-parent"
    (outside_parent / "root").mkdir(parents=True)
    (outside_parent / "root/payload").write_bytes(b"outside")
    parent.symlink_to(outside_parent, target_is_directory=True)

    assert source.read_file(PurePosixPath("payload"), context="swap").content == b"inside"
    assert list(source.walk_all_files(context="swap")) == [PurePosixPath("payload")]


def test_final_file_swap_after_open_never_reads_outside_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    payload = root / "payload"
    payload.write_bytes(b"inside")
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    source = ContainedSource(root)
    real_read = source_safety.os.read
    swapped = False

    def swap_then_read(fd: int, size: int) -> bytes:
        nonlocal swapped
        if not swapped:
            swapped = True
            payload.rename(root / "original")
            payload.symlink_to(outside)
        return real_read(fd, size)

    monkeypatch.setattr(source_safety.os, "read", swap_then_read)
    try:
        result = source.read_file(PurePosixPath("payload"), context="swap")
    except SourceSafetyError:
        return
    assert result.content == b"inside"
    assert result.content != b"outside"
