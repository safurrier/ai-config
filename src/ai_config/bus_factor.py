"""Read-only Git history analysis for change-concentration risk."""

from __future__ import annotations

import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

DEFAULT_THRESHOLD = 0.5
DEFAULT_LIMIT = 20
MAX_LIMIT = 1_000
_RECORD_SEPARATOR = "\x1e"
_FIELD_SEPARATOR = "\x1f"


class GitHistoryError(RuntimeError):
    """Raised when Git history cannot be inspected."""


@dataclass(frozen=True)
class CommitTouch:
    """A contributor and the files touched by one non-merge commit."""

    contributor: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class FileConcentration:
    """Change concentration for one file, without exposing contributor identity."""

    path: str
    total_touches: int
    dominant_share: float

    def to_dict(self) -> dict[str, str | int | float]:
        """Return stable machine-readable output."""
        return {
            "path": self.path,
            "total_touches": self.total_touches,
            "dominant_share": self.dominant_share,
        }


@dataclass(frozen=True)
class BusFactorReport:
    """Aggregated historical change concentration for one repository."""

    repository: Path
    since: str | None
    threshold: float
    commits_analyzed: int
    total_contributors: int
    top_contributor_share: float
    contributors_for_threshold: int
    files: tuple[FileConcentration, ...]
    high_risk_files: tuple[FileConcentration, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a privacy-preserving, stable machine-readable report."""
        return {
            "repository": str(self.repository),
            "since": self.since,
            "threshold": self.threshold,
            "commits_analyzed": self.commits_analyzed,
            "total_contributors": self.total_contributors,
            "top_contributor_share": self.top_contributor_share,
            "contributors_for_threshold": self.contributors_for_threshold,
            "files": [file.to_dict() for file in self.files],
            "high_risk_files": [file.to_dict() for file in self.high_risk_files],
        }


def normalize_contributor(email: str) -> str:
    """Normalize a Git email address into a stable contributor key."""
    return email.strip().lower()


def parse_git_log(output: str) -> tuple[CommitTouch, ...]:
    """Parse output from :func:`read_commit_touches`'s Git command."""
    commits: list[CommitTouch] = []
    for record in output.split(_RECORD_SEPARATOR):
        if not record:
            continue
        header, separator, file_text = record.partition("\n")
        fields = header.split(_FIELD_SEPARATOR)
        if not separator or len(fields) != 2:
            continue
        contributor = normalize_contributor(fields[1])
        if not contributor:
            continue
        files = tuple(path for path in file_text.splitlines() if path)
        commits.append(CommitTouch(contributor=contributor, files=files))
    return tuple(commits)


def _run_git(repository: Path, arguments: list[str]) -> str:
    """Run Git without a shell and translate failures into actionable errors."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except FileNotFoundError as error:
        raise GitHistoryError("Git is required to analyze history but was not found.") from error

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Git returned no details."
        raise GitHistoryError(f"Unable to read Git history: {detail}")
    return result.stdout


def read_commit_touches(repository: Path, since: str | None = None) -> tuple[CommitTouch, ...]:
    """Read non-merge commits and changed file names from a Git worktree."""
    if not repository.exists() or not repository.is_dir():
        raise GitHistoryError(f"Repository path does not exist or is not a directory: {repository}")
    is_worktree = _run_git(repository, ["rev-parse", "--is-inside-work-tree"]).strip()
    if is_worktree != "true":
        raise GitHistoryError(f"Not a Git worktree: {repository}")

    arguments = ["log", "--no-merges", f"--format={_RECORD_SEPARATOR}%an{_FIELD_SEPARATOR}%ae"]
    if since:
        arguments.append(f"--since={since}")
    arguments.append("--name-only")
    return parse_git_log(_run_git(repository, arguments))


def _share(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _contributors_for_threshold(counts: Counter[str], total: int, threshold: float) -> int:
    covered = 0
    for index, count in enumerate(sorted(counts.values(), reverse=True), start=1):
        covered += count
        if covered / total >= threshold:
            return index
    return 0


def analyze_commit_touches(
    commits: tuple[CommitTouch, ...],
    threshold: float = DEFAULT_THRESHOLD,
    limit: int = DEFAULT_LIMIT,
) -> BusFactorReport:
    """Calculate repository and file concentration metrics from commit touches."""
    contributor_touches: Counter[str] = Counter()
    file_touches: dict[str, Counter[str]] = defaultdict(Counter)
    for commit in commits:
        contributor_touches[commit.contributor] += 1
        for path in set(commit.files):
            file_touches[path][commit.contributor] += 1

    total_commits = len(commits)
    top_count = max(contributor_touches.values(), default=0)
    files = tuple(
        sorted(
            (
                FileConcentration(
                    path=path,
                    total_touches=sum(contributors.values()),
                    dominant_share=_share(max(contributors.values()), sum(contributors.values())),
                )
                for path, contributors in file_touches.items()
            ),
            key=lambda file: (-file.dominant_share, -file.total_touches, file.path),
        )[:limit]
    )
    high_risk_files = tuple(file for file in files if file.dominant_share > threshold)
    return BusFactorReport(
        repository=Path(),
        since=None,
        threshold=threshold,
        commits_analyzed=total_commits,
        total_contributors=len(contributor_touches),
        top_contributor_share=_share(top_count, total_commits),
        contributors_for_threshold=_contributors_for_threshold(
            contributor_touches, total_commits, threshold
        )
        if total_commits
        else 0,
        files=files,
        high_risk_files=high_risk_files,
    )


def analyze_repository(
    repository: Path,
    since: str | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    limit: int = DEFAULT_LIMIT,
) -> BusFactorReport:
    """Analyze historical change concentration for a Git worktree."""
    if not 0 < threshold <= 1:
        raise ValueError("Threshold must be greater than 0 and no greater than 1.")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"Limit must be between 1 and {MAX_LIMIT}.")
    resolved_repository = repository.resolve()
    analysis = analyze_commit_touches(
        read_commit_touches(resolved_repository, since), threshold, limit
    )
    return BusFactorReport(
        repository=resolved_repository,
        since=since,
        threshold=analysis.threshold,
        commits_analyzed=analysis.commits_analyzed,
        total_contributors=analysis.total_contributors,
        top_contributor_share=analysis.top_contributor_share,
        contributors_for_threshold=analysis.contributors_for_threshold,
        files=analysis.files,
        high_risk_files=analysis.high_risk_files,
    )
