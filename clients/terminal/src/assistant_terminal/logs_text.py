"""A log entry as text (its traceback lines after it), shared by the /logs screen and the plain REPL."""

from assistant.core.logs import LogEntry


def log_line(entry: LogEntry) -> str:
    """Output that isn't a record has no time, level or logger."""
    head = f"{entry.time} {entry.level} {entry.logger}: " if entry.level else ""
    return head + entry.message
