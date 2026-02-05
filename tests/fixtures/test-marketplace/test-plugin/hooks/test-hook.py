#!/usr/bin/env python3
"""Test hook for E2E validation.

This hook does nothing but print a message and exit successfully.
It exists to validate that hooks are properly synced.
"""

import sys


def main():
    print("test-hook executed successfully")
    sys.exit(0)


if __name__ == "__main__":
    main()
