"""Where lo9i keeps what it writes on disk, by category, from the settings: the data home and the folders the settings
may put elsewhere."""

from dataclasses import dataclass
from pathlib import Path

from lo9i.core.config import settings

# The categories disk use is told in, in the order the apps show them.
DATABASE = "database"
MODELS = "models"
PLUGINS = "plugins"
BROWSERS = "browsers"
PLUGIN_DATA = "plugin_data"
UPLOADS = "uploads"
LOGS = "logs"
WORKSPACE = "workspace"
BACKUPS = "backups"
DOWNLOADS = "downloads"
OTHER = "other"
CATEGORIES = (DATABASE, MODELS, PLUGINS, BROWSERS, PLUGIN_DATA, UPLOADS, LOGS, WORKSPACE, BACKUPS, DOWNLOADS, OTHER)

# What SQLite keeps beside a database while it's open.
SIDECARS = ("-wal", "-shm", "-journal")


@dataclass(frozen=True)
class Places:
    database: Path
    models: tuple[Path, ...]
    plugins: Path
    plugin_data: Path
    browsers: Path
    uploads: Path
    logs: Path
    workspaces: tuple[Path, ...]

    @property
    def home(self) -> Path:
        """The data home: the folder lo9i.db is in (~/.lo9i)."""
        return self.database.parent

    def database_files(self) -> list[Path]:
        return [self.database, *(self.database.with_name(self.database.name + s) for s in SIDECARS)]

    def roots(self) -> dict[Path, str]:
        """Each folder a category is, but the database's files and the backups, which are files in the home."""
        found = {path: MODELS for path in self.models}
        found |= {self.plugins: PLUGINS, self.plugin_data: PLUGIN_DATA, self.browsers: BROWSERS}
        found |= {self.uploads: UPLOADS, self.logs: LOGS}
        return found | {path: WORKSPACE for path in self.workspaces}


def from_settings() -> Places:
    def path(value: str) -> Path:
        return Path(value).expanduser()

    return Places(
        database=path(settings.database_path),
        models=tuple(dict.fromkeys([path(settings.stt_models_dir), path(settings.embedding_models_dir)])),
        plugins=path(settings.mcp_dir),
        plugin_data=path(settings.mcp_data_dir),
        browsers=path(settings.browsers_dir),
        uploads=path(settings.uploads_dir),
        logs=path(settings.logs_dir),
        workspaces=tuple(dict.fromkeys([path(settings.workspace_dir), path(settings.agent_workspace_dir)])),
    )
