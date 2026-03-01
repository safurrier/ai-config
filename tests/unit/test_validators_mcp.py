"""Tests for ai_config.validators.component.mcp module.

Tests MCP server configuration validation per the official Claude Code schema:
https://code.claude.com/docs/en/plugins-reference#mcp-servers
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
from ai_config.validators.component.mcp import MCPValidator


@pytest.fixture
def mock_context(tmp_path: Path) -> MagicMock:
    """Create a mock validation context."""
    context = MagicMock()
    context.config_path = tmp_path / ".ai-config" / "config.yaml"
    return context


@pytest.fixture
def plugin_dir(tmp_path: Path) -> tuple[Path, AIConfig]:
    """Create a plugin directory."""
    plugin_path = tmp_path / "test-plugin"
    plugin_path.mkdir()

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
    return plugin_path, config


class TestMCPValidatorRequiredFields:
    """Tests for required fields in MCP server configuration."""

    @pytest.fixture
    def validator(self) -> MCPValidator:
        return MCPValidator()

    @pytest.mark.asyncio
    async def test_valid_mcp_config(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """Valid MCP config with command should pass."""
        plugin_path, config = plugin_dir

        mcp_config = {"mcpServers": {"test-server": {"command": "node", "args": ["server.js"]}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_missing_command_fails(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """MCP server without command field should fail."""
        plugin_path, config = plugin_dir

        # Missing command field
        mcp_config = {"mcpServers": {"test-server": {"args": ["--port", "3000"]}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any(
            "command" in f.message.lower()
            or "transport" in f.message.lower()
            or "url" in f.message.lower()
            for f in failures
        )

    @pytest.mark.asyncio
    async def test_empty_server_config_fails(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """MCP server with empty config should fail (missing command)."""
        plugin_path, config = plugin_dir

        mcp_config = {"mcpServers": {"test-server": {}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any(
            "command" in f.message.lower()
            or "transport" in f.message.lower()
            or "url" in f.message.lower()
            for f in failures
        )

    @pytest.mark.asyncio
    async def test_command_must_be_string(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """MCP server command must be a string, not a number or array."""
        plugin_path, config = plugin_dir

        mcp_config = {"mcpServers": {"test-server": {"command": 123}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any(
            "string" in f.message.lower() or "command" in f.message.lower() for f in failures
        )

    @pytest.mark.asyncio
    async def test_command_as_array_fails(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """MCP server command as array should fail."""
        plugin_path, config = plugin_dir

        mcp_config = {"mcpServers": {"test-server": {"command": ["node", "server.js"]}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any(
            "string" in f.message.lower() or "command" in f.message.lower() for f in failures
        )


class TestMCPValidatorOptionalFields:
    """Tests for optional fields in MCP server configuration."""

    @pytest.fixture
    def validator(self) -> MCPValidator:
        return MCPValidator()

    @pytest.mark.asyncio
    async def test_args_is_optional(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """args field should be optional."""
        plugin_path, config = plugin_dir

        mcp_config = {"mcpServers": {"test-server": {"command": "node"}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_args_must_be_array(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """args field must be an array if provided."""
        plugin_path, config = plugin_dir

        mcp_config = {"mcpServers": {"test-server": {"command": "node", "args": "--help"}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("args" in f.message.lower() or "array" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_env_is_optional(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """env field should be optional."""
        plugin_path, config = plugin_dir

        mcp_config = {"mcpServers": {"test-server": {"command": "node", "args": ["server.js"]}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_env_must_be_object(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """env field must be an object if provided."""
        plugin_path, config = plugin_dir

        mcp_config = {"mcpServers": {"test-server": {"command": "node", "env": ["VAR=value"]}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("env" in f.message.lower() or "object" in f.message.lower() for f in failures)


class TestMCPValidatorEmptyConfig:
    """Tests for empty/missing MCP configuration."""

    @pytest.fixture
    def validator(self) -> MCPValidator:
        return MCPValidator()

    @pytest.mark.asyncio
    async def test_no_mcp_file(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """Plugin without .mcp.json should pass (MCP is optional)."""
        plugin_path, config = plugin_dir
        # No .mcp.json created

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_empty_mcp_servers(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """Empty mcpServers object should be valid."""
        plugin_path, config = plugin_dir

        mcp_config = {"mcpServers": {}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []


class TestMCPValidatorPathVariable:
    """Tests for CLAUDE_PLUGIN_ROOT variable in paths."""

    @pytest.fixture
    def validator(self) -> MCPValidator:
        return MCPValidator()

    @pytest.mark.asyncio
    async def test_plugin_root_variable(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """Command with ${CLAUDE_PLUGIN_ROOT} variable should be valid."""
        plugin_path, config = plugin_dir

        mcp_config = {
            "mcpServers": {
                "test-server": {
                    "command": "${CLAUDE_PLUGIN_ROOT}/bin/server",
                    "args": ["--port", "3000"],
                }
            }
        }
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []


class TestMCPValidatorMultipleServers:
    """Tests for multiple MCP servers."""

    @pytest.fixture
    def validator(self) -> MCPValidator:
        return MCPValidator()

    @pytest.mark.asyncio
    async def test_multiple_servers_valid(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """Multiple valid servers should all pass."""
        plugin_path, config = plugin_dir

        mcp_config = {
            "mcpServers": {
                "server1": {"command": "node", "args": ["server1.js"]},
                "server2": {"command": "python", "args": ["-m", "server2"]},
            }
        }
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_one_invalid_server_fails(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """If one server is invalid, validation should fail."""
        plugin_path, config = plugin_dir

        mcp_config = {
            "mcpServers": {
                "server1": {"command": "node"},  # valid
                "server2": {},  # invalid - missing command
            }
        }
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))

        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]

        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("server2" in f.message.lower() for f in failures)


class TestMCPValidatorHTTPTransport:
    """Tests for HTTP/streamable-http transport validation."""

    @pytest.fixture
    def validator(self) -> MCPValidator:
        return MCPValidator()

    @pytest.mark.asyncio
    async def test_valid_http_server(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """HTTP server with url should pass."""
        plugin_path, config = plugin_dir
        mcp_config = {
            "mcpServers": {
                "api-server": {
                    "type": "streamable-http",
                    "url": "https://api.example.com/mcp",
                }
            }
        }
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_implicit_http_from_url(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """Server with only url field should be detected as HTTP."""
        plugin_path, config = plugin_dir
        mcp_config = {"mcpServers": {"api-server": {"url": "https://api.example.com/mcp"}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []

    @pytest.mark.asyncio
    async def test_http_missing_url_fails(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """HTTP server without url should fail."""
        plugin_path, config = plugin_dir
        mcp_config = {
            "mcpServers": {
                "api-server": {
                    "type": "streamable-http",
                    "headers": {"Authorization": "Bearer token"},
                }
            }
        }
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("url" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_url_must_be_string(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """URL field must be a string."""
        plugin_path, config = plugin_dir
        mcp_config = {"mcpServers": {"api-server": {"url": 12345}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any(
            "url" in f.message.lower() and "string" in f.message.lower() for f in failures
        )

    @pytest.mark.asyncio
    async def test_headers_must_be_dict(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """Headers field must be a dict if present."""
        plugin_path, config = plugin_dir
        mcp_config = {
            "mcpServers": {
                "api-server": {"url": "https://api.example.com/mcp", "headers": "invalid"}
            }
        }
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("headers" in f.message.lower() for f in failures)

    @pytest.mark.asyncio
    async def test_url_format_warning(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """Non-http(s) URL should produce a warning."""
        plugin_path, config = plugin_dir
        mcp_config = {"mcpServers": {"api-server": {"url": "ftp://example.com/mcp"}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]
        results = await validator.validate(mock_context)
        warnings = [r for r in results if r.status == "warn"]
        assert len(warnings) >= 1
        assert any("url" in w.message.lower() for w in warnings)


class TestMCPValidatorSSETransport:
    """Tests for SSE transport validation."""

    @pytest.fixture
    def validator(self) -> MCPValidator:
        return MCPValidator()

    @pytest.mark.asyncio
    async def test_valid_sse_server_with_deprecation_warning(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """SSE server should pass but produce a deprecation warning."""
        plugin_path, config = plugin_dir
        mcp_config = {
            "mcpServers": {
                "sse-server": {"type": "sse", "url": "https://api.example.com/sse"}
            }
        }
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []
        warnings = [r for r in results if r.status == "warn"]
        assert any(
            "sse" in w.message.lower() or "deprecat" in w.message.lower() for w in warnings
        )

    @pytest.mark.asyncio
    async def test_sse_missing_url_fails(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """SSE server without url should fail."""
        plugin_path, config = plugin_dir
        mcp_config = {"mcpServers": {"sse-server": {"type": "sse"}}}
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert len(failures) >= 1
        assert any("url" in f.message.lower() for f in failures)


class TestMCPValidatorTransportDetection:
    """Tests for transport type detection."""

    def test_explicit_stdio(self) -> None:
        v = MCPValidator()
        assert v._detect_transport({"type": "stdio", "command": "node"}) == "stdio"

    def test_explicit_http(self) -> None:
        v = MCPValidator()
        assert v._detect_transport({"type": "streamable-http", "url": "https://example.com"}) == "http"

    def test_explicit_sse(self) -> None:
        v = MCPValidator()
        assert v._detect_transport({"type": "sse", "url": "https://example.com"}) == "sse"

    def test_implicit_stdio_from_command(self) -> None:
        v = MCPValidator()
        assert v._detect_transport({"command": "node"}) == "stdio"

    def test_implicit_http_from_url(self) -> None:
        v = MCPValidator()
        assert v._detect_transport({"url": "https://example.com"}) == "http"

    def test_unknown_transport(self) -> None:
        v = MCPValidator()
        assert v._detect_transport({}) is None

    def test_explicit_unknown_type(self) -> None:
        v = MCPValidator()
        assert v._detect_transport({"type": "grpc"}) is None


class TestMCPValidatorMixedTransports:
    """Tests for plugins with mixed transport types."""

    @pytest.fixture
    def validator(self) -> MCPValidator:
        return MCPValidator()

    @pytest.mark.asyncio
    async def test_mixed_stdio_and_http_servers(
        self,
        validator: MCPValidator,
        mock_context: MagicMock,
        plugin_dir: tuple[Path, AIConfig],
    ) -> None:
        """Plugin with both stdio and HTTP servers should pass."""
        plugin_path, config = plugin_dir
        mcp_config = {
            "mcpServers": {
                "local-server": {"command": "node", "args": ["server.js"]},
                "remote-server": {"url": "https://api.example.com/mcp"},
            }
        }
        (plugin_path / ".mcp.json").write_text(json.dumps(mcp_config))
        mock_context.config = config
        mock_context.installed_plugins = [
            InstalledPlugin(
                id="test-plugin",
                version="1.0.0",
                scope="user",
                enabled=True,
                install_path=str(plugin_path),
            )
        ]
        results = await validator.validate(mock_context)
        failures = [r for r in results if r.status == "fail"]
        assert failures == []
