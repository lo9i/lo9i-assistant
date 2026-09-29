"""Terminal colors. Disabled when output isn't a terminal or NO_COLOR is set."""

import os
import sys

GREEN = "\033[32m"
GRAY = "\033[38;5;250m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"

_ENABLED = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def paint(color: str, text: str) -> str:
    return f"{color}{text}{RESET}" if _ENABLED else text


def code(color: str) -> str:
    """The raw escape code, for text written in several pieces (typed input, streamed replies)."""
    return color if _ENABLED else ""
