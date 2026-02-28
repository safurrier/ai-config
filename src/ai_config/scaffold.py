"""Plugin scaffolding for ai-config."""

from __future__ import annotations

from pathlib import Path

MANIFEST_TEMPLATE = """name: {name}
version: 0.1.0
description: A Claude Code plugin

# Optional: Define MCP servers
# mcpServers:
#   my-server:
#     type: stdio
#     command: npx
#     args:
#       - -y
#       - my-mcp-server

# Optional: Define skills
# skills:
#   - name: my-skill
#     description: Does something useful

# Optional: Define hooks
# hooks:
#   PreToolUse:
#     - command: python3
#       args:
#         - hooks/pre_tool_use.py
"""

SKILL_TEMPLATE = """---
name: {name}
description: A skill that does something useful
---

# {name}

## When to Activate

- When the user asks about...
- When working with...

## Quickstart

1. Check existing patterns
2. Follow the conventions

## Guardrails

- Do not...
- Always...
"""


def create_plugin(name: str, path: Path | None = None) -> Path:
    """Create a new plugin scaffold.

    Args:
        name: Name of the plugin.
        path: Base path for the plugin directory. Defaults to ~/.claude-plugins/

    Returns:
        Path to the created plugin directory.
    """
    if path is None:
        path = Path.home() / ".claude-plugins"

    plugin_dir = path / name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest
    manifest_path = plugin_dir / "manifest.yaml"
    if not manifest_path.exists():
        manifest_path.write_text(MANIFEST_TEMPLATE.format(name=name))

    # Create directories
    (plugin_dir / "skills").mkdir(exist_ok=True)
    (plugin_dir / "hooks").mkdir(exist_ok=True)

    # Create example skill
    skill_dir = plugin_dir / "skills" / "example"
    skill_dir.mkdir(exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        skill_file.write_text(SKILL_TEMPLATE.format(name="example"))

    return plugin_dir
