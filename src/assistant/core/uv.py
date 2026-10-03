"""Finding uv, which runs MCP servers in their own environments and installs model providers'
packages. A systemd service has a short PATH, so the usual install locations are tried too."""

import os
import shutil
from pathlib import Path

_PLACES = ("~/.local/bin/uv", "~/.cargo/bin/uv", "/opt/homebrew/bin/uv", "/usr/local/bin/uv", "/snap/bin/uv")


def find() -> str | None:
    found = shutil.which("uv")
    if found:
        return found
    places = (Path(p).expanduser() for p in _PLACES)
    return next((str(p) for p in places if p.is_file() and os.access(p, os.X_OK)), None)
