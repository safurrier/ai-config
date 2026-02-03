"""Validator framework for ai-config doctor command."""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from ai_config.validators.base import ValidationReport, ValidationResult, Validator
from ai_config.validators.component.hook import HookValidator
from ai_config.validators.component.mcp import MCPValidator
from ai_config.validators.component.skill import SkillValidator
from ai_config.validators.context import ValidationContext
from ai_config.validators.marketplace.validators import (
    MarketplaceManifestValidator,
    MarketplacePathValidator,
    PathDriftValidator,
)
from ai_config.validators.plugin.validators import (
    PluginInstalledValidator,
    PluginManifestValidator,
    PluginStateValidator,
)
from ai_config.validators.target.claude import (
    ClaudeCLIResponseValidator,
    ClaudeCLIValidator,
)

if TYPE_CHECKING:
    from ai_config.types import AIConfig

__all__ = [
    "ValidationContext",
    "ValidationReport",
    "ValidationResult",
    "Validator",
    "run_validators",
    "VALIDATORS",
]

# Registry of validators by category
VALIDATORS: dict[str, list[type]] = {
    "target": [ClaudeCLIValidator, ClaudeCLIResponseValidator],
    "marketplace": [
        MarketplacePathValidator,
        MarketplaceManifestValidator,
        PathDriftValidator,
    ],
    "plugin": [
        PluginInstalledValidator,
        PluginStateValidator,
        PluginManifestValidator,
    ],
    "component": [SkillValidator, HookValidator, MCPValidator],
}


async def _run_validator(
    validator_cls: type, context: ValidationContext
) -> tuple[str, list[ValidationResult]]:
    """Run a single validator and return results with validator name.

    Args:
        validator_cls: The validator class to instantiate and run.
        context: The validation context.

    Returns:
        Tuple of (validator_name, results).
    """
    validator = validator_cls()
    try:
        results = await validator.validate(context)
        return validator.name, results
    except Exception as e:
        return validator.name, [
            ValidationResult(
                check_name=f"{validator.name}_error",
                status="fail",
                message=f"Validator {validator.name} raised an exception",
                details=str(e),
            )
        ]


async def run_validators(
    config: "AIConfig",
    config_path: Path,
    categories: list[str] | None = None,
    target_type: str = "claude",
) -> dict[str, ValidationReport]:
    """Run validators for specified categories.

    Args:
        config: The loaded AIConfig.
        config_path: Path to the config file.
        categories: List of categories to run, or None for all.
        target_type: The target type to validate.

    Returns:
        Dict mapping category names to ValidationReports.
    """
    context = ValidationContext(
        config=config,
        config_path=config_path,
        target_type=target_type,
    )

    categories_to_run = categories or list(VALIDATORS.keys())
    reports: dict[str, ValidationReport] = {}

    for category in categories_to_run:
        if category not in VALIDATORS:
            continue

        validator_classes = VALIDATORS[category]

        # Run all validators in this category concurrently
        tasks = [_run_validator(validator_cls, context) for validator_cls in validator_classes]
        validator_results = await asyncio.gather(*tasks)

        # Collect all results for this category
        all_results: list[ValidationResult] = []
        for _validator_name, results in validator_results:
            all_results.extend(results)

        reports[category] = ValidationReport(
            target=f"{target_type}:{category}",
            results=all_results,
        )

    return reports


def run_validators_sync(
    config: "AIConfig",
    config_path: Path,
    categories: list[str] | None = None,
    target_type: str = "claude",
) -> dict[str, ValidationReport]:
    """Synchronous wrapper for run_validators.

    Args:
        config: The loaded AIConfig.
        config_path: Path to the config file.
        categories: List of categories to run, or None for all.
        target_type: The target type to validate.

    Returns:
        Dict mapping category names to ValidationReports.
    """
    return asyncio.run(run_validators(config, config_path, categories, target_type))
