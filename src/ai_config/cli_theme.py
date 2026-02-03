"""Theme and styling constants for ai-config CLI.

This module centralizes all Rich styling to ensure consistent appearance
across commands and to keep rendering logic separate from business logic.
"""

from rich.console import Console
from rich.theme import Theme

# Unified theme for ai-config CLI
AI_CONFIG_THEME = Theme(
    {
        "header": "bold cyan",
        "subheader": "bold",
        "success": "green",
        "warning": "yellow",
        "error": "red bold",
        "info": "dim",
        "hint": "cyan italic",
        "key": "cyan",
        "value": "white",
    }
)

# Status symbols for consistent display
SYMBOLS = {
    "pass": "\u2713",  # ✓
    "fail": "\u2717",  # ✗
    "warn": "\u26a0",  # ⚠
    "arrow": "\u2192",  # →
    "bullet": "\u2022",  # •
}


def create_console(stderr: bool = False) -> Console:
    """Create a themed console instance.

    Args:
        stderr: If True, write to stderr instead of stdout.

    Returns:
        Configured Console with AI_CONFIG_THEME applied.
    """
    return Console(theme=AI_CONFIG_THEME, stderr=stderr)
