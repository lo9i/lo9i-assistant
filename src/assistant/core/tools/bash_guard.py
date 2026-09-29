"""Detects bash commands that need user approval.

Patterns are a Linux subset adapted from Hermes Agent `tools/approval_detection.py`
(MIT License, Copyright (c) 2025 Nous Research), plus git and database-client rules.
"""

import re

_SHELLS = r"(?:ba|z|k|da)?sh"

_DANGEROUS_PATTERNS = [
    (r"\brm\s+(-[^\s]*\s+)*/", "delete in root path"),
    (r"\brm\s+-[^\s]*r", "recursive delete"),
    (r"\brm\s+--recursive\b", "recursive delete"),
    (r"\bxargs\s+.*\brm\b", "xargs with rm"),
    (r"\bfind\b.*(-exec(dir)?\s+(/\S*/)?rm\b|-delete\b)", "find with delete"),
    (r"\bchmod\s+(-[^\s]*\s+)*(777|666|o\+[rwx]*w|a\+[rwx]*w)\b", "world-writable permissions"),
    (r"\bchown\s+(-[^\s]*)?R\s+root", "recursive chown to root"),
    (r"(?:^|[;&|]\s*)mkfs\b", "format filesystem"),
    (r"(?:^|[;&|]\s*)dd\s+.*if=", "disk copy"),
    (r">\s*/dev/(sd|nvme|hd|vd|xvd)", "write to block device"),
    (r"\bkill\s+-9\s+-1\b", "kill all processes"),
    (r"\bpkill\s+-9\b", "force kill processes"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "fork bomb"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "shutdown or reboot"),
    (r"\bsudo\b", "sudo"),
    (rf"\b(curl|wget)\b.*\|\s*(?:[/\w]*/)?{_SHELLS}\b", "pipe remote content to shell"),
    (rf"\b(base64|base32)\s+(-d|--decode)\b.*\|\s*{_SHELLS}\b", "pipe decoded content to shell"),
    (r"(?<![\d.])169\.254\.169\.254(?![\d.])", "cloud metadata endpoint"),
    (r"\bDROP\s+(TABLE|DATABASE)\b", "SQL DROP"),
    (r"\bDELETE\s+FROM\b(?![^\n]*\bWHERE\b)", "SQL DELETE without WHERE"),
    (r"\bTRUNCATE\s+(TABLE)?\s*\w", "SQL TRUNCATE"),
    (r"\b(psql|pg_dump|pg_restore)\b", "database client"),
    (r"\bgit\s+push\b.*(--force\b|\s-f\b)", "git force push"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+clean\s+-[^\s]*f", "git clean"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), reason) for p, reason in _DANGEROUS_PATTERNS]


def find_danger(command: str) -> str | None:
    """Reason the command is dangerous, or None if no pattern matches."""
    for pattern, reason in _COMPILED:
        if pattern.search(command):
            return reason
    return None
