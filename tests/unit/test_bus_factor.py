"""Tests for read-only Git-history concentration analysis."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_config.bus_factor import (
    CommitTouch,
    GitHistoryError,
    analyze_commit_touches,
    analyze_repository,
    normalize_contributor,
    parse_git_log,
    read_commit_touches,
)


def test_normalize_contributor_uses_lowercase_trimmed_email() -> None:
    assert normalize_contributor("  Ada@Example.COM ") == "ada@example.com"


def test_parse_git_log_reads_non_merge_commit_files() -> None:
    output = "\x1eAda\x1fADA@example.com\nsrc/app.py\nREADME.md\n\x1eBob\x1fbob@example.com\nsrc/app.py\n"

    assert parse_git_log(output) == (
        CommitTouch("ada@example.com", ("src/app.py", "README.md")),
        CommitTouch("bob@example.com", ("src/app.py",)),
    )


def test_parse_git_log_ignores_malformed_or_identityless_records() -> None:
    assert parse_git_log("\x1ebad\nfile.py\n\x1eName\x1f\nfile.py\n") == ()


def test_analysis_calculates_concentration_and_deterministic_file_order() -> None:
    report = analyze_commit_touches(
        (
            CommitTouch("ada@example.com", ("b.py", "a.py", "a.py")),
            CommitTouch("ada@example.com", ("b.py",)),
            CommitTouch("bob@example.com", ("a.py",)),
        ),
        threshold=0.5,
        limit=10,
    )

    assert report.commits_analyzed == 3
    assert report.total_contributors == 2
    assert report.top_contributor_share == 0.6667
    assert report.contributors_for_threshold == 1
    assert [(file.path, file.total_touches, file.dominant_share) for file in report.files] == [
        ("b.py", 2, 1.0),
        ("a.py", 2, 0.5),
    ]
    assert [file.path for file in report.high_risk_files] == ["b.py"]


def test_analysis_handles_empty_and_binary_file_histories() -> None:
    empty = analyze_commit_touches((), threshold=0.5, limit=10)
    binary = analyze_commit_touches(
        (CommitTouch("ada@example.com", ("assets/logo.png",)),), threshold=0.5, limit=10
    )

    assert empty.total_contributors == empty.contributors_for_threshold == 0
    assert empty.files == ()
    assert binary.files[0].path == "assets/logo.png"
    assert binary.files[0].dominant_share == 1.0


def test_read_commit_touches_uses_git_without_shell_and_since(tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(["git"], 0, stdout="true\n", stderr="")
    log = subprocess.CompletedProcess(
        ["git"], 0, stdout="\x1eAda\x1fada@example.com\na.py\n", stderr=""
    )
    with patch("ai_config.bus_factor.subprocess.run", side_effect=[completed, log]) as run:
        commits = read_commit_touches(tmp_path, "2026-01-01")

    assert commits == (CommitTouch("ada@example.com", ("a.py",)),)
    command = run.call_args_list[1].args[0]
    assert command[:3] == ["git", "-C", str(tmp_path)]
    assert "--since=2026-01-01" in command
    assert run.call_args_list[1].kwargs["shell"] is False


def test_subprocess_failure_has_actionable_error(tmp_path: Path) -> None:
    failed = subprocess.CompletedProcess(["git"], 128, stdout="", stderr="not a repository")
    with patch("ai_config.bus_factor.subprocess.run", return_value=failed):
        with pytest.raises(GitHistoryError, match="Unable to read Git history: not a repository"):
            read_commit_touches(tmp_path)


def test_analyze_repository_rejects_invalid_bounds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Threshold"):
        analyze_repository(tmp_path, threshold=0)
    with pytest.raises(ValueError, match="Limit"):
        analyze_repository(tmp_path, limit=0)
