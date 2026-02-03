"""Tests for ai_config.validators.component.hook module.

Tests hook configuration validation per the official Claude Code schema:
https://code.claude.com/docs/en/hooks
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_config.adapters.claude import InstalledPlugin
from ai_config.types import (
    AIConfig,
    ClaudeTargetConfig,
    PluginConfig,
    TargetConfig,
)
from ai_config.validators.component.hook import HookValidator

# Valid event names per official Claude Code hooks documentation
VALID_EVENTS = [
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

# Valid hook types
VALID_HOOK_TYPES = ["command", "prompt", "agent"]


@pytest.fixture
def mock_context(tmp_path: Path) -> MagicMock:
    """Create a mock validation context."""
    context = MagicMock()
    context.config_path = tmp_path / ".ai-config" / "config.yaml"
    return context


@pytest.fixture
def plugin_with_hooks(tmp_path: Path) -> tuple[Path, AIConfig]:
    """Create a plugin directory with hooks directory."""
    plugin_dir = tmp_path / "test-plugin"
    plugin_dir.mkdir()
    hooks_dir = plugin_dir / "hooks"
    hooks_dir.mkdir()

    config = AIConfig(
        version=1,
        targets=(
            TargetConfig(
                type="claude",
                config=ClaudeTargetConfig(
                    plugins=(PluginConfig(id="test-plugin"),),
                ),
            ),
        ),
    )
    return plugin_dir, config


class TestHookValidatorEvents:
    """Tests for hook event name validation."""

    @pytest.fixture
    def validator(self) -> HookValidator:
        return HookValidator()

    @pytest.mark.parametrize("event_name", VALID_EVENTS)
    @pytest.mark.asyncio
    async def test_valid_event_names(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
        event_name: str,
    ) -> None:
        """Valid event names should pass validation."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        # Create hooks.json with valid event
        hooks_config = {"hooks": {event_name: []}}
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        event_errors = [f for f in failures if "event" in f.message.lower()]
        assert event_errors == [], f"Event '{event_name}' should be valid"

    @pytest.mark.parametrize(
        "invalid_event",
        [
            "InvalidEvent",
            "pretooluse",  # case-sensitive
            "POSTTOOLUSE",  # uppercase
            "session_start",  # underscores
            "random",
            "",
        ],
    )
    @pytest.mark.asyncio
    async def test_invalid_event_names(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
        invalid_event: str,
    ) -> None:
        """Invalid event names should fail validation."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        # Create hooks.json with invalid event
        hooks_config = {"hooks": {invalid_event: []}}
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1, f"Event '{invalid_event}' should be invalid"
        assert any("event" in f.message.lower() or "invalid" in f.message.lower() for f in failures)


class TestHookValidatorTypes:
    """Tests for hook type validation."""

    @pytest.fixture
    def validator(self) -> HookValidator:
        return HookValidator()

    @pytest.mark.parametrize("hook_type", VALID_HOOK_TYPES)
    @pytest.mark.asyncio
    async def test_valid_hook_types(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
        hook_type: str,
    ) -> None:
        """Valid hook types should pass validation."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        # Create hooks.json with valid hook type
        hook_entry: dict = {"type": hook_type}
        if hook_type == "command":
            hook_entry["command"] = "echo test"
        else:  # prompt or agent
            hook_entry["prompt"] = "Test prompt"

        hooks_config = {"hooks": {"Stop": [{"hooks": [hook_entry]}]}}
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        type_errors = [
            f for f in failures if "type" in f.message.lower() and "invalid" in f.message.lower()
        ]
        assert type_errors == [], f"Hook type '{hook_type}' should be valid"

    @pytest.mark.asyncio
    async def test_invalid_hook_type(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """Invalid hook type should fail validation."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        hooks_config = {
            "hooks": {"Stop": [{"hooks": [{"type": "invalid_type", "command": "echo"}]}]}
        }
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("type" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_missing_type_field(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """Missing type field should fail validation."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        # Hook without type field
        hooks_config = {"hooks": {"Stop": [{"hooks": [{"command": "echo test"}]}]}}
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("type" in f.message.lower() for f in failures)


class TestHookValidatorRequiredFields:
    """Tests for required fields per hook type."""

    @pytest.fixture
    def validator(self) -> HookValidator:
        return HookValidator()

    @pytest.mark.asyncio
    async def test_command_hook_missing_command(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """Command hook without command field should fail."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        hooks_config = {"hooks": {"Stop": [{"hooks": [{"type": "command"}]}]}}
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("command" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_prompt_hook_missing_prompt(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """Prompt hook without prompt field should fail."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        hooks_config = {"hooks": {"Stop": [{"hooks": [{"type": "prompt"}]}]}}
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("prompt" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_agent_hook_missing_prompt(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """Agent hook without prompt field should fail."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        hooks_config = {"hooks": {"Stop": [{"hooks": [{"type": "agent"}]}]}}
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("prompt" in f.message.lower() for f in failures)


class TestHookValidatorStructure:
    """Tests for overall hooks.json structure validation."""

    @pytest.fixture
    def validator(self) -> HookValidator:
        return HookValidator()

    @pytest.mark.asyncio
    async def test_empty_hooks_object_valid(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """Empty hooks object should be valid."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        hooks_config = {"hooks": {}}
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_hooks_must_be_object(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """hooks field must be an object, not an array."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        # Old/incorrect format with hooks as array
        hooks_config = {"hooks": [{"command": "echo test"}]}
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("object" in f.message.lower() or "dict" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_event_handlers_must_be_array(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """Event handlers must be an array."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        hooks_config = {"hooks": {"Stop": {"hooks": []}}}  # Should be array
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("array" in f.message.lower() or "list" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_complex_valid_hooks_config(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """Complex but valid hooks configuration should pass."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        hooks_config = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Write|Edit",
                        "hooks": [
                            {"type": "command", "command": "echo 'file changed'"},
                        ],
                    }
                ],
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "prompt", "prompt": "Review command: $ARGUMENTS"},
                        ],
                    }
                ],
                "SessionStart": [
                    {
                        "hooks": [
                            {"type": "command", "command": "echo 'session started'"},
                        ],
                    }
                ],
            }
        }
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []


class TestHookValidatorMatcher:
    """Tests for optional matcher field validation."""

    @pytest.fixture
    def validator(self) -> HookValidator:
        return HookValidator()

    @pytest.mark.asyncio
    async def test_matcher_is_optional(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """Matcher field should be optional."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        # No matcher field
        hooks_config = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo"}]}]}}
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_matcher_as_string(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        plugin_with_hooks: tuple[Path, AIConfig],
    ) -> None:
        """Matcher as string should be valid."""
        plugin_dir, config = plugin_with_hooks
        hooks_dir = plugin_dir / "hooks"

        hooks_config = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "echo"}],
                    }
                ]
            }
        }
        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []


class TestHookValidatorNoHooks:
    """Tests for plugins without hooks."""

    @pytest.fixture
    def validator(self) -> HookValidator:
        return HookValidator()

    @pytest.mark.asyncio
    async def test_no_hooks_directory(
        self,
        validator: HookValidator,
        mock_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Plugin without hooks directory should pass (hooks are optional)."""
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()
        # No hooks directory created

        config = AIConfig(
            version=1,
            targets=(
                TargetConfig(
                    type="claude",
                    config=ClaudeTargetConfig(
                        plugins=(PluginConfig(id="test-plugin"),),
                    ),
                ),
            ),
        )

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_dir),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []
