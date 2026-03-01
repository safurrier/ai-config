"""Base types and protocol for ai-config validators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ai_config.validators.context import ValidationContext


@dataclass
class ValidationResult:
    """Single validation check result."""

    check_name: str
    status: Literal["pass", "warn", "fail"]
    message: str
    details: str | None = None
    fix_hint: str | None = None


@dataclass
class ValidationReport:
    """Aggregated results from multiple validators."""

    target: str
    results: list[ValidationResult]

    @property
    def passed(self) -> bool:
        """Return True if no failures in results."""
        return not any(r.status == "fail" for r in self.results)

    @property
    def has_warnings(self) -> bool:
        """Return True if any warnings in results."""
        return any(r.status == "warn" for r in self.results)


@runtime_checkable
class Validator(Protocol):
    """Base protocol for all validators."""

    name: str
    description: str

    async def validate(self, context: ValidationContext) -> list[ValidationResult]:
        """Run validation checks and return results."""
        ...
