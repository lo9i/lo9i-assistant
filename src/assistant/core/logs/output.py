"""Where the daemon's process output is read from: the journal when systemd connected its stderr to
it, the output file (files.py::output_path) otherwise. In a terminal (`assistant daemon`) the output
shows there, and the file holds what daemons started in the background printed before."""

import os

from assistant.core.logs.files import output_path
from assistant.core.logs.journal import Journal
from assistant.core.logs.output_file import OutputFile
from assistant.core.logs.sources import LogSource


def process_output(unit: str) -> LogSource:
    """`unit` is the systemd service the daemon runs as there."""
    return Journal(unit) if stderr_is_journal() else OutputFile(output_path())


def stderr_is_journal() -> bool:
    """systemd sets JOURNAL_STREAM to the device and inode of the stream it connects to the journal.
    A process started from such a service inherits the variable but not the stream, so it's compared."""
    stream = os.environ.get("JOURNAL_STREAM", "")
    try:
        stat = os.fstat(2)
    except OSError:
        return False
    return stream == f"{stat.st_dev}:{stat.st_ino}"
