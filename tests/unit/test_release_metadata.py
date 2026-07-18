"""Release metadata stays truthful until a release is actually published."""

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]


def test_0_6_0_release_metadata_is_finalized() -> None:
    changelog = (_REPO_ROOT / "CHANGELOG.md").read_text()

    assert "## [0.6.0] - 2026-07-17" in changelog
    assert "[Unreleased]: https://github.com/safurrier/ai-config/compare/v0.6.0...HEAD" in changelog
    assert "[0.6.0]: https://github.com/safurrier/ai-config/compare/v0.5.0...v0.6.0" in changelog


def test_release_checklist_assigns_date_at_release_time() -> None:
    instructions = (_REPO_ROOT / "AGENTS.md").read_text()

    assert (
        "Move `[Unreleased]` entries to a new version section with the actual release date"
        in instructions
    )
