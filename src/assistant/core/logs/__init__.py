"""The daemon's own log: the files it writes (files.py, writer.py), its records read back as entries
(entries.py) with the area of the assistant each comes from (components.py), and reading the latest
ones (reader.py) or following a file live (LogWriter.follow). Its process output, what isn't a record,
is read alongside them (output.py), and the level it records at is a setting (level.py)."""

from assistant.core.logs import level
from assistant.core.logs.components import COMPONENTS, OTHER, component_of
from assistant.core.logs.entries import FORMAT, LEVELS, LogEntry, LogLevel, parse
from assistant.core.logs.files import LOG_FILES, LogFile, LogFileInfo, info, output_path
from assistant.core.logs.journal import Journal
from assistant.core.logs.level import LogLevelError
from assistant.core.logs.options import LogOptions, log_options
from assistant.core.logs.output import process_output
from assistant.core.logs.output_file import OutputFile
from assistant.core.logs.reader import MAX_LINES, LogPage, LogQuery, LogQueryError, read_page
from assistant.core.logs.sources import LogSource, WrittenLog, log_sources
from assistant.core.logs.writer import LogWriter, configure

__all__ = [
    "COMPONENTS",
    "FORMAT",
    "LEVELS",
    "LOG_FILES",
    "MAX_LINES",
    "OTHER",
    "Journal",
    "LogEntry",
    "LogFile",
    "LogFileInfo",
    "LogLevel",
    "LogLevelError",
    "LogOptions",
    "LogPage",
    "LogQuery",
    "LogQueryError",
    "LogSource",
    "LogWriter",
    "OutputFile",
    "WrittenLog",
    "component_of",
    "configure",
    "info",
    "level",
    "log_options",
    "log_sources",
    "output_path",
    "parse",
    "process_output",
    "read_page",
]
