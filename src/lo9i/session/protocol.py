"""What the session helper and those it serves say to each other: one JSON object per line on its Unix socket, one
request per connection, answered with one object (docs/login-session.md).

- `{"op": "open", "url": "tel:+5491112345678"}`, with `"app": "Phone"` to open it with that app, or only `app`:
  opens it on the screen. `{"ok": true}`, or `{"error": "..."}` saying why it didn't.
- `{"op": "version"}`: `{"version": "<digest>"}`, of the helper's code when it started (`code_digest`), so the daemon
  can tell when an update changed it.
- `{"op": "quit"}`: `{"ok": true}`, and the helper exits; launchd starts it again, with the code installed now."""

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any

# Long enough for the Mac to open an app, short enough that a helper that hangs doesn't hold a call.
ANSWER_SECONDS = 15
# A link's scheme, as `open` reads one: never a file, which could run a script, nor an option.
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_APP = re.compile(r"^[\w][\w .&'()-]*$")
_MAX_URL = 2048


class HelperUnavailableError(Exception):
    """Nothing answers on the socket: nobody is logged in on the Mac, or the helper is starting."""


class OpenRefusedError(ValueError):
    pass


def open_arguments(url: str, app: str) -> list[str]:
    """What `open` is run with for a request. Raises OpenRefusedError for a link or app it doesn't take."""
    if not url and not app:
        raise OpenRefusedError("Say what to open: a url, an app or both.")
    if url and (len(url) > _MAX_URL or not _SCHEME.match(url) or url.lower().startswith("file:")):
        raise OpenRefusedError(f"{url[:80]!r} isn't a link the helper opens: it takes links with a scheme, not files.")
    if app and not _APP.match(app):
        raise OpenRefusedError(f"{app[:80]!r} isn't an app's name.")
    return [*(["-a", app] if app else []), *([url] if url else [])]


def code_digest() -> str:
    """A digest of the helper's code as installed now."""
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()[:16]


async def ask(socket: Path, request: dict[str, Any]) -> dict[str, Any]:
    """The helper's answer. Raises HelperUnavailableError when nothing answers."""
    try:
        reader, writer = await asyncio.open_unix_connection(str(socket))
    except OSError as e:
        raise HelperUnavailableError(str(e)) from e
    try:
        writer.write(json.dumps(request).encode() + b"\n")
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), ANSWER_SECONDS)
    except (OSError, TimeoutError) as e:
        raise HelperUnavailableError(str(e) or "No answer in time.") from e
    finally:
        writer.close()
    if not line:
        raise HelperUnavailableError("It closed the connection without answering.")
    return json.loads(line)
