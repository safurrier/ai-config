"""Docker fixtures for E2E testing.

This module provides pytest fixtures for running E2E tests in Docker containers.
It handles Docker daemon detection (colima, Docker Desktop, native Linux),
image building, and container lifecycle management.

Supports multiple Docker images:
- claude-only: Fast image with just Claude Code (default for CI)
- all-tools: Full image with all 4 AI coding tools (Claude, Codex, OpenCode, Cursor)
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import docker
    from docker.models.containers import Container
    from docker.models.images import Image


# Image configurations
@dataclass
class ImageConfig:
    """Configuration for a Docker test image."""

    tag: str
    dockerfile: str
    description: str


IMAGES = {
    "claude-only": ImageConfig(
        tag="ai-config-test:claude-only",
        dockerfile="Dockerfile.claude-only",
        description="Claude Code only (fast builds)",
    ),
    "all-tools": ImageConfig(
        tag="ai-config-test:all-tools",
        dockerfile="Dockerfile.all-tools",
        description="All AI coding tools (Claude, Codex, OpenCode, Cursor)",
    ),
}

# Default image for tests
DEFAULT_IMAGE = "claude-only"


def _get_docker_host() -> str | None:
    """Detect Docker host URL based on available daemon.

    Checks for:
    1. DOCKER_HOST environment variable (explicit override)
    2. Colima socket (macOS with colima)
    3. Docker Desktop socket (macOS/Windows with Docker Desktop)
    4. Default socket (Linux native Docker)

    Returns:
        Docker host URL or None for default
    """
    # Check explicit override first
    if docker_host := os.environ.get("DOCKER_HOST"):
        return docker_host

    # Colima socket (common on macOS)
    colima_socket = Path.home() / ".colima" / "default" / "docker.sock"
    if colima_socket.exists():
        return f"unix://{colima_socket}"

    # Docker Desktop socket (macOS)
    desktop_socket = Path.home() / ".docker" / "run" / "docker.sock"
    if desktop_socket.exists():
        return f"unix://{desktop_socket}"

    # Default socket (Linux, or let Docker SDK figure it out)
    return None


def _is_docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _image_exists(tag: str) -> bool:
    """Check if a Docker image with the given tag exists."""
    result = subprocess.run(
        ["docker", "images", "-q", tag],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _build_image(project_root: Path, image_config: ImageConfig) -> bool:
    """Build the Docker image using subprocess (avoids credential helper issues)."""
    dockerfile = project_root / "tests" / "docker" / image_config.dockerfile
    result = subprocess.run(
        ["docker", "build", "-t", image_config.tag, "-f", str(dockerfile), str(project_root)],
        capture_output=True,
        text=True,
        timeout=900,  # 15 minute timeout for all-tools image
    )
    if result.returncode != 0:
        print(f"Docker build failed:\n{result.stderr}")  # noqa: T201
    return result.returncode == 0


@pytest.fixture(scope="session")
def docker_available() -> bool:
    """Check if Docker is available for testing."""
    return _is_docker_available()


@pytest.fixture(scope="session")
def docker_client(docker_available: bool) -> Generator[docker.DockerClient, None, None]:
    """Create a Docker client for the session.

    This fixture is session-scoped to avoid reconnection overhead.
    """
    if not docker_available:
        pytest.skip("Docker not available")

    import docker

    host = _get_docker_host()
    if host:
        client = docker.DockerClient(base_url=host)
    else:
        client = docker.from_env()

    yield client
    client.close()


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Get the project root directory."""
    # Navigate up from tests/e2e/conftest.py to project root
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="session")
def claude_image(
    docker_client: docker.DockerClient,
    project_root: Path,
) -> Generator[Image, None, None]:
    """Get or build the Claude-only Docker image for testing.

    This fixture is session-scoped to avoid rebuilding for each test class.
    The image is tagged and cached for reuse across test runs.

    Uses subprocess for building to avoid Docker credential helper issues
    that can occur with the Python SDK on some systems.
    """
    image_config = IMAGES["claude-only"]

    # Check if image already exists
    if not _image_exists(image_config.tag):
        print(f"Building Docker image {image_config.tag}...")  # noqa: T201
        if not _build_image(project_root, image_config):
            pytest.skip(f"Failed to build Docker image {image_config.tag}")

    # Get the image using the SDK
    try:
        image = docker_client.images.get(image_config.tag)
    except Exception as e:
        pytest.skip(f"Failed to get Docker image: {e}")

    yield image


@pytest.fixture(scope="session")
def all_tools_image(
    docker_client: docker.DockerClient,
    project_root: Path,
) -> Generator[Image, None, None]:
    """Get or build the all-tools Docker image for testing.

    This image includes all supported AI coding tools:
    - Claude Code
    - OpenAI Codex
    - OpenCode
    - Cursor CLI

    Note: Some tools may not install successfully if their installers
    aren't publicly available yet.
    """
    image_config = IMAGES["all-tools"]

    # Check if image already exists
    if not _image_exists(image_config.tag):
        print(f"Building Docker image {image_config.tag} (this may take a while)...")  # noqa: T201
        if not _build_image(project_root, image_config):
            pytest.skip(f"Failed to build Docker image {image_config.tag}")

    # Get the image using the SDK
    try:
        image = docker_client.images.get(image_config.tag)
    except Exception as e:
        pytest.skip(f"Failed to get Docker image: {e}")

    yield image


@pytest.fixture(scope="class")
def claude_container(
    docker_client: docker.DockerClient,
    claude_image: Image,
) -> Generator[Container, None, None]:
    """Create a container with Claude Code for testing.

    This fixture is class-scoped so tests within a class share the same container,
    but different test classes get fresh containers.
    """
    container = docker_client.containers.run(
        image=claude_image.id,
        command="sleep infinity",  # Keep container running
        detach=True,
        user="testuser",
        working_dir="/home/testuser/ai-config",
        remove=True,  # Auto-remove when stopped
    )

    yield container

    # Stop and remove container
    container.stop(timeout=5)


@pytest.fixture(scope="class")
def all_tools_container(
    docker_client: docker.DockerClient,
    all_tools_image: Image,
) -> Generator[Container, None, None]:
    """Create a container with all AI coding tools for testing.

    This fixture is class-scoped so tests within a class share the same container,
    but different test classes get fresh containers.
    """
    container = docker_client.containers.run(
        image=all_tools_image.id,
        command="sleep infinity",  # Keep container running
        detach=True,
        user="testuser",
        working_dir="/home/testuser/ai-config",
        remove=True,  # Auto-remove when stopped
    )

    yield container

    # Stop and remove container
    container.stop(timeout=5)


def exec_in_container(
    container: Container, command: str, user: str = "testuser"
) -> tuple[int, str]:
    """Execute a command in the container and return exit code and output.

    Args:
        container: Docker container to execute in
        command: Shell command to run
        user: User to run command as (default: testuser)

    Returns:
        Tuple of (exit_code, output_string)
    """
    result = container.exec_run(
        cmd=["bash", "-c", command],
        user=user,
        workdir="/home/testuser/ai-config",
    )
    return result.exit_code, result.output.decode("utf-8")


def check_tool_installed(container: Container, tool_name: str, version_cmd: str) -> tuple[bool, str]:
    """Check if a tool is installed and get its version.

    Args:
        container: Docker container to check in
        tool_name: Human-readable tool name
        version_cmd: Command to get version (e.g., "claude --version")

    Returns:
        Tuple of (is_installed, version_or_error_message)
    """
    exit_code, output = exec_in_container(container, version_cmd)
    if exit_code == 0:
        return True, output.strip()
    return False, f"{tool_name} not installed or not in PATH"
