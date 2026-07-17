"""Release metadata stays truthful until a release is actually published."""

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]


def test_pending_release_stays_under_unreleased_heading() -> None:
    changelog = (_REPO_ROOT / "CHANGELOG.md").read_text()

    assert "## [0.6.0]" not in changelog
    assert "[Unreleased]: https://github.com/safurrier/ai-config/compare/v0.5.0...HEAD" in changelog
    assert "[0.6.0]:" not in changelog


def test_release_checklist_assigns_date_at_release_time() -> None:
    instructions = (_REPO_ROOT / "AGENTS.md").read_text()

    assert (
        "Move `[Unreleased]` entries to a new version section with the actual release date"
        in instructions
    )
