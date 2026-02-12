"""Tmux test session helper for E2E testing.

This module provides a TmuxTestSession class that manages tmux sessions
for testing AI CLI tools. Ported from dots repo.

Prior art: ~/git_repositories/dots/tests/e2e/ai_tools/test_ai_tools_e2e.py
"""

from __future__ import annotations

import subprocess
import time


class TmuxTestSession:
    """Manages a tmux test session for E2E testing.

    This class allows sending commands to and capturing output from
    a tmux session, useful for testing interactive CLI tools.
    """

    def __init__(self, session_name: str):
        """Initialize with a session name.

        Args:
            session_name: Unique name for the tmux session.
        """
        self.session_name = session_name
        self.session_active = False

    def create_session(self, working_dir: str | None = None) -> None:
        """Create a new tmux session.

        Args:
            working_dir: Optional working directory for the session.

        Raises:
            RuntimeError: If session creation fails.
        """
        cmd = ["tmux", "new-session", "-d", "-s", self.session_name]
        if working_dir:
            cmd.extend(["-c", working_dir])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create tmux session: {result.stderr}")

        self.session_active = True
        # Give session time to initialize
        time.sleep(0.5)

    def send_keys(self, keys: str, enter: bool = True) -> None:
        """Send keys to the tmux session.

        Args:
            keys: The keys/command to send.
            enter: If True, press Enter after sending keys.

        Raises:
            RuntimeError: If session is not active or send fails.
        """
        if not self.session_active:
            raise RuntimeError("Tmux session not active")

        cmd = ["tmux", "send-keys", "-t", self.session_name, keys]
        if enter:
            cmd.append("Enter")

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to send keys: {result.stderr}")

    def capture_pane(self, scrollback: int = 100) -> str:
        """Capture the current pane content.

        Args:
            scrollback: Number of lines of scrollback to include.

        Returns:
            The captured pane content.

        Raises:
            RuntimeError: If session is not active or capture fails.
        """
        if not self.session_active:
            raise RuntimeError("Tmux session not active")

        cmd = ["tmux", "capture-pane", "-t", self.session_name, "-p", "-S", f"-{scrollback}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to capture pane: {result.stderr}")

        return result.stdout

    def wait_for_output(
        self,
        expected: str,
        timeout: float = 10.0,
        interval: float = 0.5,
    ) -> bool:
        """Wait for expected output to appear in the pane.

        Args:
            expected: The string to wait for.
            timeout: Maximum time to wait in seconds.
            interval: Time between checks in seconds.

        Returns:
            True if expected output found, False if timeout.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            output = self.capture_pane()
            if expected in output:
                return True
            time.sleep(interval)

        # On failure, print the actual output for debugging
        final_output = self.capture_pane()
        print(f"DEBUG: Expected '{expected}' but got:\n{final_output}")  # noqa: T201
        return False

    def wait_for_prompt(self, prompt: str = "$", timeout: float = 10.0) -> bool:
        """Wait for shell prompt to appear (command finished).

        Args:
            prompt: The prompt character to wait for.
            timeout: Maximum time to wait in seconds.

        Returns:
            True if prompt found, False if timeout.
        """
        return self.wait_for_output(prompt, timeout=timeout)

    def cleanup(self) -> None:
        """Clean up the tmux session."""
        if self.session_active:
            subprocess.run(
                ["tmux", "kill-session", "-t", self.session_name],
                capture_output=True,
            )
            self.session_active = False

    def __enter__(self) -> TmuxTestSession:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup session."""
        self.cleanup()


def is_tmux_available() -> bool:
    """Check if tmux is available on the system.

    Returns:
        True if tmux is installed and accessible.
    """
    try:
        result = subprocess.run(
            ["tmux", "-V"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
