"""What a move takes from the data home (`home()`, the folder lo9i.db is in: ~/.lo9i, a temporary one in tests), and
what it leaves for each computer to make again."""

from pathlib import Path

from lo9i.core.config import settings

DATABASE = "lo9i.db"
# The browser page rendering downloads for this system (core/internet/browser.py): taken only to the same system.
BROWSERS = "browsers"
# Taken whole, but for what's left out below. What isn't listed stays: models/ (downloaded again on first use), logs,
# sockets, claude-workspace/, old backups.
TAKEN = (
    DATABASE,
    "keys",
    "SOUL.md",
    "prompts",
    "skills",
    "mcp",
    "data",
    "uploads",
    "workspace",
    "arca",
    BROWSERS,
    "cli_preferences.json",
    "cli_history",
)
# Plugins' code is taken without what installing it builds (core/mcp/environment.py), which the import builds again.
CODE = "mcp"
BUILT = frozenset({".venv", "node_modules", "__pycache__"})
# Plugins write their SQLite databases while the daemon runs: each is taken through SQLite's backup, without the
# journal and write-ahead log beside it.
PLUGIN_DATA = "data"
SIDECARS = ("-wal", "-shm", "-journal")
# Where paths of the old computer are written as data, and changed to this one's on import (moved_paths.py): not the
# user's files (uploads, workspace), plugins' code or binaries.
WITH_PATHS = (DATABASE, PLUGIN_DATA, "skills", "prompts", "SOUL.md", "cli_preferences.json")
# Tables of lo9i.db that hold conversations' checkpoints, which are never changed (history is append-only).
CHECKPOINTS = frozenset({"checkpoints", "writes"})


def home() -> Path:
    return Path(settings.database_path).expanduser().parent
