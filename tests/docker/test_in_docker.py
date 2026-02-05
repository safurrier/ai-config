#!/usr/bin/env python3
"""CLI script for running E2E tests in Docker locally.

This script provides convenient commands for building Docker images,
running tests, and debugging test failures interactively.

Supports two Docker images:
- claude-only (default): Fast image with just Claude Code
- all-tools: Full image with all AI coding tools (Claude, Codex, OpenCode, Cursor)

Usage:
    python tests/docker/test_in_docker.py              # Run claude-only tests
    python tests/docker/test_in_docker.py --all-tools  # Run with all tools
    python tests/docker/test_in_docker.py --rebuild    # Rebuild image first
    python tests/docker/test_in_docker.py --shell      # Drop into shell
    python tests/docker/test_in_docker.py -k "fresh"   # Run tests matching pattern
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Image configurations
IMAGES = {
    "claude-only": {
        "tag": "ai-config-test:claude-only",
        "dockerfile": "Dockerfile.claude-only",
        "description": "Claude Code only (fast builds)",
        "marker": "e2e and docker and not slow",
    },
    "all-tools": {
        "tag": "ai-config-test:all-tools",
        "dockerfile": "Dockerfile.all-tools",
        "description": "All AI coding tools",
        "marker": "e2e and docker",  # includes slow tests
    },
}


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def check_docker() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def build_image(image_name: str = "claude-only", rebuild: bool = False) -> int:
    """Build the Docker image for testing."""
    project_root = get_project_root()
    image_config = IMAGES[image_name]
    dockerfile = project_root / "tests" / "docker" / image_config["dockerfile"]
    image_tag = image_config["tag"]

    print(f"Building Docker image: {image_tag}")
    print(f"Description: {image_config['description']}")
    print(f"Using Dockerfile: {dockerfile}")
    print(f"Context: {project_root}")
    print()

    cmd = [
        "docker",
        "build",
        "-t",
        image_tag,
        "-f",
        str(dockerfile),
        str(project_root),
    ]

    if rebuild:
        cmd.insert(2, "--no-cache")

    result = subprocess.run(cmd)
    return result.returncode


def run_tests(
    image_name: str = "claude-only",
    pattern: str | None = None,
    verbose: bool = True,
) -> int:
    """Run E2E tests using pytest."""
    project_root = get_project_root()
    image_config = IMAGES[image_name]

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(project_root / "tests" / "e2e"),
        "-m",
        image_config["marker"],
    ]

    if verbose:
        cmd.append("-v")

    if pattern:
        cmd.extend(["-k", pattern])

    print(f"Running tests for: {image_config['description']}")
    print(f"Marker: {image_config['marker']}")
    print(f"Command: {' '.join(cmd)}")
    print()
    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode


def run_shell(image_name: str = "claude-only") -> int:
    """Drop into an interactive shell in the Docker container."""
    project_root = get_project_root()
    image_config = IMAGES[image_name]
    image_tag = image_config["tag"]

    # First ensure image exists
    result = subprocess.run(
        ["docker", "images", "-q", image_tag],
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        print(f"Image {image_tag} not found. Building...")
        if build_image(image_name) != 0:
            print("Failed to build image")
            return 1

    print(f"Starting interactive shell in {image_tag}")
    print(f"Image: {image_config['description']}")
    print("Working directory: /home/testuser/ai-config")
    print("User: testuser")
    print()

    cmd = [
        "docker",
        "run",
        "-it",
        "--rm",
        "-v",
        f"{project_root}:/home/testuser/ai-config",
        "-w",
        "/home/testuser/ai-config",
        "-u",
        "testuser",
        image_tag,
        "/bin/bash",
    ]

    result = subprocess.run(cmd)
    return result.returncode


def list_images() -> None:
    """List available Docker images."""
    print("Available Docker images:")
    print()
    for name, config in IMAGES.items():
        print(f"  {name}")
        print(f"    Tag: {config['tag']}")
        print(f"    Description: {config['description']}")
        print(f"    Test marker: {config['marker']}")
        print()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run E2E tests in Docker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                    # Run claude-only tests (fast)
    %(prog)s --all-tools        # Run all tests with all tools
    %(prog)s --rebuild          # Rebuild image and run tests
    %(prog)s --shell            # Interactive debugging shell
    %(prog)s --shell --all-tools  # Shell with all tools
    %(prog)s -k "fresh"         # Run tests matching "fresh"
    %(prog)s --build-only       # Just build the image
    %(prog)s --list             # List available images
""",
    )

    parser.add_argument(
        "--all-tools",
        action="store_true",
        help="Use all-tools image instead of claude-only",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild Docker image from scratch (no cache)",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Drop into interactive shell instead of running tests",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Only build the Docker image, don't run tests",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available Docker images",
    )
    parser.add_argument(
        "-k",
        "--pattern",
        help="Only run tests matching the given pattern",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Less verbose output",
    )

    args = parser.parse_args()

    # List mode
    if args.list:
        list_images()
        return 0

    # Check Docker availability
    if not check_docker():
        print("Error: Docker is not available or not running")
        print("Please start Docker and try again")
        return 1

    # Determine which image to use
    image_name = "all-tools" if args.all_tools else "claude-only"

    # Shell mode
    if args.shell:
        return run_shell(image_name)

    # Build image if requested or if running tests
    if args.rebuild or args.build_only:
        ret = build_image(image_name, rebuild=args.rebuild)
        if ret != 0:
            return ret
        if args.build_only:
            print("Image built successfully")
            return 0

    # Run tests
    return run_tests(
        image_name=image_name,
        pattern=args.pattern,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    sys.exit(main())
