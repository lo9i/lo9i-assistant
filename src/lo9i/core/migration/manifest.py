"""What an export says about where it was made: the first entry of its archive. The import reads it to leave out what
only works on that system and to move the old computer's paths to this one's."""

import json
import platform
import socket
import sys
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from lo9i.core.i18n import said
from lo9i.core.migration.errors import MigrationError
from lo9i.core.repositories import platforms
from lo9i.core.uv import find as find_uv

NAME = "manifest.json"
# The folder the home's entries are under in the archive.
HOME = "home"
FORMAT = 1


@dataclass(frozen=True)
class Manifest:
    exported_at: str
    lo9i: str
    # platforms.current()'s name, and platform.machine()'s.
    system: str
    machine: str
    host: str
    # The user's home folder and lo9i's, as paths there, and the Python and uv plugins' commands were filled in with
    # (core/mcp/install.py).
    user_home: str
    data_home: str
    python: str
    uv: str
    taken: list[str] = field(default_factory=list)
    format: int = FORMAT

    def same_system(self) -> bool:
        return self.system == platforms.current() and self.machine == platform.machine()

    def to_json(self) -> bytes:
        return json.dumps(asdict(self), indent=2).encode()

    @classmethod
    def from_json(cls, data: bytes) -> "Manifest":
        try:
            values = json.loads(data)
            manifest = cls(**{f.name: values[f.name] for f in fields(cls) if f.name in values})
        except (ValueError, TypeError) as e:
            raise MigrationError(said("This file isn't a lo9i export.")) from e
        if manifest.format > FORMAT:
            raise MigrationError(said("This export was made by a newer lo9i: update lo9i here first."))
        return manifest


def made_here(home: Path, taken: list[str]) -> Manifest:
    return Manifest(
        exported_at=datetime.now(UTC).isoformat(timespec="seconds"),
        lo9i=version("lo9i"),
        system=platforms.current(),
        machine=platform.machine(),
        host=socket.gethostname(),
        user_home=str(Path.home()),
        data_home=str(home),
        python=sys.executable,
        uv=find_uv() or "",
        taken=taken,
    )
