"""The Linux desktop clipboard: `wl-paste` and `wl-copy` on Wayland, `xclip` on X11."""

import os
import shutil
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from assistant.client.clipboard import process
from assistant.client.files import load_attachment
from assistant.core.attachments import Attachment

# File managers put copied files on the clipboard as a list of file:// URIs.
_URI_LIST = "text/uri-list"
_PNG = "image/png"


@dataclass(frozen=True)
class Reader:
    """The commands that list the clipboard's types and read it, and the flag that picks one type."""

    list_types: tuple[str, ...]
    read: tuple[str, ...]
    type_flag: str

    def read_as(self, media_type: str) -> tuple[str, ...]:
        return (*self.read, self.type_flag, media_type)


_XCLIP = ("xclip", "-selection", "clipboard", "-out")
_WAYLAND = Reader(("wl-paste", "--list-types"), ("wl-paste", "--no-newline"), "--type")
# xclip lists the types when asked for the TARGETS type.
_X11 = Reader((*_XCLIP, "-target", "TARGETS"), _XCLIP, "-target")


def find_reader() -> Reader | None:
    """None on a machine without a desktop, such as a server reached over SSH."""
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        return _WAYLAND
    if os.environ.get("DISPLAY") and shutil.which("xclip"):
        return _X11
    return None


def copy_command() -> list[str] | None:
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        return ["wl-copy"]
    if os.environ.get("DISPLAY") and shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    return None


async def paste(reader: Reader) -> Attachment | str:
    """Files come first, as on a Mac: a copied file can also bring its icon as an image."""
    types = (await process.text(*reader.list_types)).split()
    path = await _file_path(reader) if _URI_LIST in types else None
    if path is not None:
        return load_attachment(path)
    if _PNG in types:
        return process.png(await process.run(*reader.read_as(_PNG)))
    return await process.text(*reader.read)


async def _file_path(reader: Reader) -> str | None:
    """The first local file in the list. A copied link is a URI too, but no file."""
    for line in (await process.text(*reader.read_as(_URI_LIST))).splitlines():
        url = urlparse(line.strip())
        if url.scheme == "file":
            return unquote(url.path)
    return None
