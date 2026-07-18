"""Semantic Versioning 2.0.0 precedence regressions."""

from __future__ import annotations

import pytest

from ai_config.semver import SemanticVersion


@pytest.mark.parametrize(
    ("lower", "higher"),
    [
        ("1.0.0-alpha", "1.0.0-alpha.1"),
        ("1.0.0-alpha.1", "1.0.0-alpha.beta"),
        ("1.0.0-alpha.beta", "1.0.0-beta"),
        ("1.0.0-beta", "1.0.0-beta.2"),
        ("1.0.0-beta.2", "1.0.0-beta.11"),
        ("1.0.0-beta.11", "1.0.0-rc.1"),
        ("1.0.0-rc.1", "1.0.0"),
    ],
)
def test_semver_precedence_matches_spec(lower: str, higher: str) -> None:
    left = SemanticVersion.parse(lower)
    right = SemanticVersion.parse(higher)

    assert left < right
    assert not right < left
    assert right > left


def test_build_metadata_does_not_affect_precedence_equality_or_hashing() -> None:
    plain = SemanticVersion.parse("1.2.3")
    first = SemanticVersion.parse("1.2.3+build.1")
    second = SemanticVersion.parse("1.2.3+build.2")

    assert plain == first == second
    assert hash(plain) == hash(first) == hash(second)
    assert len({plain, first, second}) == 1
    assert {plain: "plain", first: "first", second: "second"} == {plain: "second"}
    assert not plain < first
    assert not first < plain
