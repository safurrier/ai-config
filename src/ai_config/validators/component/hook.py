"""Hook validators for ai-config.

Validates hooks.json configuration per the official Claude Code schema:
https://code.claude.com/docs/en/hooks
"""

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ai_config.validators.base import ValidationResult

if TYPE_CHECKING:
    from ai_config.validators.context import ValidationContext

# Valid event names per official Claude Code hooks documentation
VALID_EVENTS = frozenset(
    [
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PermissionRequest",
        "Notification",
        "SubagentStart",
        "SubagentStop",
        "Stop",
        "PreCompact",
        "SessionEnd",
    ]
)

# Valid hook types
VALID_HOOK_TYPES = frozenset(["command", "prompt", "agent"])


class HookValidator:
    """Validates hooks.json configuration for plugins."""

    name = "hook_validator"
    description = "Validates hooks.json files per official Claude Code schema"

    async def validate(self, context: "ValidationContext") -> list[ValidationResult]:
        """Validate hooks for all configured plugins.

        Args:
            context: The validation context.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        # Create lookup map for installed plugins
        installed_map = {p.id: p for p in context.installed_plugins}

        for target in context.config.targets:
            if target.type != "claude":
                continue

            for plugin in target.config.plugins:
                installed = installed_map.get(plugin.id)
                if not installed:
                    continue

                install_path = Path(installed.install_path)
                if not install_path.exists():
                    continue

                # Check for hooks directory and hooks.json
                hooks_dir = install_path / "hooks"
                hooks_json = hooks_dir / "hooks.json"

                if not hooks_dir.exists():
                    # No hooks directory is fine
                    continue

                if not hooks_json.exists():
                    # Hooks directory exists but no hooks.json
                    results.append(
                        ValidationResult(
                            check_name="hooks_json_exists",
                            status="warn",
                            message=f"Plugin '{plugin.id}' has hooks directory but no hooks.json",
                            details=f"Expected at: {hooks_json}",
                        )
                    )
                    continue

                # Validate hooks.json
                try:
                    with open(hooks_json) as f:
                        hooks_config = json.load(f)
                except json.JSONDecodeError as e:
                    results.append(
                        ValidationResult(
                            check_name="hooks_json_valid",
                            status="fail",
                            message=f"Plugin '{plugin.id}' has invalid JSON in hooks.json",
                            details=str(e),
                        )
                    )
                    continue
                except OSError as e:
                    results.append(
                        ValidationResult(
                            check_name="hooks_json_readable",
                            status="fail",
                            message=f"Failed to read hooks.json for '{plugin.id}'",
                            details=str(e),
                        )
                    )
                    continue

                if not isinstance(hooks_config, dict):
                    results.append(
                        ValidationResult(
                            check_name="hooks_json_valid",
                            status="fail",
                            message=f"Plugin '{plugin.id}' hooks.json is not a JSON object",
                        )
                    )
                    continue

                # Validate hook entries
                hook_results = self._validate_hooks(plugin.id, hooks_dir, hooks_config)
                results.extend(hook_results)

                if not any(r.status == "fail" for r in hook_results):
                    results.append(
                        ValidationResult(
                            check_name="hooks_valid",
                            status="pass",
                            message=f"Plugin '{plugin.id}' hooks are valid",
                        )
                    )

        return results

    def _validate_hooks(
        self, plugin_id: str, hooks_dir: Path, hooks_config: dict
    ) -> list[ValidationResult]:
        """Validate hook configuration per official Claude Code schema.

        Official schema structure:
        {
          "hooks": {
            "EventName": [
              {
                "matcher": "regex-pattern",  // optional
                "hooks": [
                  { "type": "command|prompt|agent", ... }
                ]
              }
            ]
          }
        }

        Args:
            plugin_id: The plugin identifier.
            hooks_dir: Path to the hooks directory.
            hooks_config: The parsed hooks.json content.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []

        # Check hooks field exists and is object
        hooks_obj = hooks_config.get("hooks")
        if hooks_obj is None:
            # No hooks field is fine (empty config)
            return results

        if not isinstance(hooks_obj, dict):
            results.append(
                ValidationResult(
                    check_name="hooks_format",
                    status="fail",
                    message=f"Plugin '{plugin_id}' hooks.json 'hooks' must be an object (dict)",
                    details="The 'hooks' field should map event names to handler arrays",
                    fix_hint='Use format: {"hooks": {"EventName": [...]}}',
                )
            )
            return results

        # Validate each event
        for event_name, handlers in hooks_obj.items():
            # Validate event name
            if event_name not in VALID_EVENTS:
                results.append(
                    ValidationResult(
                        check_name="hooks_event_name",
                        status="fail",
                        message=f"Plugin '{plugin_id}' has invalid event name: '{event_name}'",
                        details=f"Valid events: {', '.join(sorted(VALID_EVENTS))}",
                    )
                )
                continue

            # Validate handlers is array
            if not isinstance(handlers, list):
                results.append(
                    ValidationResult(
                        check_name="hooks_handlers_format",
                        status="fail",
                        message=(
                            f"Plugin '{plugin_id}' event '{event_name}' "
                            "handlers must be an array (list)"
                        ),
                    )
                )
                continue

            # Validate each handler group
            for i, handler_group in enumerate(handlers):
                if not isinstance(handler_group, dict):
                    results.append(
                        ValidationResult(
                            check_name="hooks_handler_format",
                            status="fail",
                            message=f"Plugin '{plugin_id}' {event_name}[{i}] must be an object",
                        )
                    )
                    continue

                # Validate matcher if present (optional string)
                matcher = handler_group.get("matcher")
                if matcher is not None and not isinstance(matcher, str):
                    results.append(
                        ValidationResult(
                            check_name="hooks_matcher_format",
                            status="fail",
                            message=(
                                f"Plugin '{plugin_id}' {event_name}[{i}] matcher must be a string"
                            ),
                        )
                    )

                # Validate hooks array within handler group
                hooks_array = handler_group.get("hooks", [])
                if not isinstance(hooks_array, list):
                    results.append(
                        ValidationResult(
                            check_name="hooks_array_format",
                            status="fail",
                            message=(
                                f"Plugin '{plugin_id}' {event_name}[{i}].hooks must be an array"
                            ),
                        )
                    )
                    continue

                # Validate each hook in the array
                for j, hook in enumerate(hooks_array):
                    hook_results = self._validate_hook_entry(
                        plugin_id, event_name, i, j, hooks_dir, hook
                    )
                    results.extend(hook_results)

        return results

    def _validate_hook_entry(
        self,
        plugin_id: str,
        event_name: str,
        handler_idx: int,
        hook_idx: int,
        hooks_dir: Path,
        hook: dict,
    ) -> list[ValidationResult]:
        """Validate a single hook entry.

        Args:
            plugin_id: The plugin identifier.
            event_name: The event name.
            handler_idx: Index of the handler group.
            hook_idx: Index of the hook within hooks array.
            hooks_dir: Path to the hooks directory.
            hook: The hook configuration dict.

        Returns:
            List of validation results.
        """
        results: list[ValidationResult] = []
        location = f"{event_name}[{handler_idx}].hooks[{hook_idx}]"

        if not isinstance(hook, dict):
            results.append(
                ValidationResult(
                    check_name="hook_format",
                    status="fail",
                    message=f"Plugin '{plugin_id}' {location} must be an object",
                )
            )
            return results

        # Validate type field (required)
        hook_type = hook.get("type")
        if not hook_type:
            results.append(
                ValidationResult(
                    check_name="hook_type_required",
                    status="fail",
                    message=f"Plugin '{plugin_id}' {location} is missing required 'type' field",
                    fix_hint="Add 'type': 'command', 'prompt', or 'agent'",
                )
            )
            return results

        if hook_type not in VALID_HOOK_TYPES:
            results.append(
                ValidationResult(
                    check_name="hook_type_valid",
                    status="fail",
                    message=f"Plugin '{plugin_id}' {location} has invalid type: '{hook_type}'",
                    details=f"Valid types: {', '.join(sorted(VALID_HOOK_TYPES))}",
                )
            )
            return results

        # Validate required fields per type
        if hook_type == "command":
            command = hook.get("command")
            if not command:
                results.append(
                    ValidationResult(
                        check_name="hook_command_required",
                        status="fail",
                        message=(
                            f"Plugin '{plugin_id}' {location} command hook "
                            "is missing 'command' field"
                        ),
                    )
                )
            elif isinstance(command, str):
                # Check if command is a relative path to a script
                script_path = hooks_dir / command
                if script_path.exists():
                    if not os.access(script_path, os.X_OK):
                        results.append(
                            ValidationResult(
                                check_name="hook_executable",
                                status="warn",
                                message=f"Plugin '{plugin_id}' hook script not executable",
                                details=f"Script: {command}",
                                fix_hint=f"Run: chmod +x {script_path}",
                            )
                        )
        else:  # prompt or agent
            prompt = hook.get("prompt")
            if not prompt:
                results.append(
                    ValidationResult(
                        check_name="hook_prompt_required",
                        status="fail",
                        message=(
                            f"Plugin '{plugin_id}' {location} {hook_type} hook "
                            "is missing 'prompt' field"
                        ),
                    )
                )

        return results
