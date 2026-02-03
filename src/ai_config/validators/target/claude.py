"""Claude CLI target validators for ai-config."""

import subprocess
from typing import TYPE_CHECKING

from ai_config.validators.base import ValidationResult

if TYPE_CHECKING:
    from ai_config.validators.context import ValidationContext


class ClaudeCLIValidator:
    """Validates that Claude CLI is available and functioning."""

    name = "claude_cli"
    description = "Validates Claude CLI availability"

    async def validate(self, context: "ValidationContext") -> list[ValidationResult]:
        """Validate Claude CLI is available.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                version = result.stdout.strip()
                results.append(
                    ValidationResult(
                        check_name="claude_cli_available",
                        status="pass",
                        message=f"Claude CLI available ({version})",
                    )
                )
            else:
                results.append(
                    ValidationResult(
                        check_name="claude_cli_available",
                        status="fail",
                        message="Claude CLI returned error",
                        details=result.stderr,
                        fix_hint="Reinstall Claude Code: npm install -g @anthropic-ai/claude-code",
                    )
                )

        except FileNotFoundError:
            results.append(
                ValidationResult(
                    check_name="claude_cli_available",
                    status="fail",
                    message="Claude CLI not found",
                    fix_hint="Install Claude Code: npm install -g @anthropic-ai/claude-code",
                )
            )
        except subprocess.TimeoutExpired:
            results.append(
                ValidationResult(
                    check_name="claude_cli_available",
                    status="fail",
                    message="Claude CLI timed out",
                    details="The claude --version command took too long to respond",
                )
            )
        except OSError as e:
            results.append(
                ValidationResult(
                    check_name="claude_cli_available",
                    status="fail",
                    message="Failed to run Claude CLI",
                    details=str(e),
                )
            )

        return results


class ClaudeCLIResponseValidator:
    """Validates that Claude CLI responds to commands."""

    name = "claude_cli_response"
    description = "Validates Claude CLI responds to plugin commands"

    async def validate(self, context: "ValidationContext") -> list[ValidationResult]:
        """Validate Claude CLI responds to commands.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        # Try a simple plugin list command to verify CLI is working
        try:
            result = subprocess.run(
                ["claude", "plugin", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                results.append(
                    ValidationResult(
                        check_name="claude_cli_responds",
                        status="pass",
                        message="Claude CLI responds to commands",
                    )
                )
            else:
                results.append(
                    ValidationResult(
                        check_name="claude_cli_responds",
                        status="fail",
                        message="Claude CLI plugin command failed",
                        details=result.stderr,
                    )
                )

        except FileNotFoundError:
            # Already caught by ClaudeCLIValidator
            pass
        except subprocess.TimeoutExpired:
            results.append(
                ValidationResult(
                    check_name="claude_cli_responds",
                    status="fail",
                    message="Claude CLI command timed out",
                    details="The plugin list command took too long",
                )
            )
        except OSError as e:
            results.append(
                ValidationResult(
                    check_name="claude_cli_responds",
                    status="fail",
                    message="Failed to run Claude CLI command",
                    details=str(e),
                )
            )

        return results
