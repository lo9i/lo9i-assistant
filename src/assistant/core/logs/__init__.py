"""The daemon's own log: the files it writes (files.py, writer.py), its records read back as entries
(entries.py) with the area of the assistant each comes from (components.py), and reading the latest
ones (reader.py) or following a file live (LogWriter.follow)."""

from assistant.core.logs.components import COMPONENTS, OTHER, component_of
from assistant.core.logs.entries import FORMAT, LEVELS, LogEntry, LogLevel, parse
from assistant.core.logs.files import LOG_FILES, LogFile, LogFileInfo, info, output_path
from assistant.core.logs.options import LogOptions, log_options
from assistant.core.logs.reader import MAX_LINES, LogPage, LogQuery, LogQueryError, read_page
from assistant.core.logs.writer import LogWriter, configure

__all__ = [
    "COMPONENTS",
    "FORMAT",
    "LEVELS",
    "LOG_FILES",
    "MAX_LINES",
    "OTHER",
    "LogEntry",
    "LogFile",
    "LogFileInfo",
    "LogLevel",
    "LogOptions",
    "LogPage",
    "LogQuery",
    "LogQueryError",
    "LogWriter",
    "component_of",
    "configure",
    "info",
    "log_options",
    "output_path",
    "parse",
    "read_page",
]
