"""JSON settings file manipulation with key preservation."""

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file, returning empty dict if file doesn't exist.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed JSON as a dict, or empty dict if file doesn't exist.

    Raises:
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    if not path.exists():
        return {}

    with open(path) as f:
        content = f.read()
        if not content.strip():
            return {}
        return json.loads(content)


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write a dict to a JSON file, preserving formatting.

    Args:
        path: Path to the JSON file.
        data: Dict to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def merge_settings(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Merge updates into base settings, preserving unknown keys.

    Does a shallow merge at the top level, deep merge for nested dicts.

    Args:
        base: The base settings dict.
        updates: The updates to apply.

    Returns:
        New dict with updates merged in.
    """
    result = base.copy()

    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = value

    return result
