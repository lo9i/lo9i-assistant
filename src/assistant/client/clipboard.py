"""The clipboard of the machine the terminal app runs on.

Pasting (Ctrl+V): terminals pass pasted text to the app but never images or files, so the client
reads the clipboard itself with `osascript`. Only on a Mac; clients check `available()` at start.

Copying: with the system's clipboard command (`pbcopy`, `wl-copy`, `xclip`). Over SSH there's
none worth using, so clients also copy through the terminal (OSC 52), which reaches the clipboard
of the computer in front of the user, in terminals that support it.
"""

import asyncio
import os
import shutil
import sys
from datetime import datetime

from assistant.client.files import load_attachment
from assistant.core.attachments import Attachment

_FILE = "«class furl»"
_PNG = "«class PNGf»"
# Image types macOS converts to PNG on request. A screenshot copied to the clipboard has both.
_IMAGES = (_PNG, "TIFF picture")
_DATA_PREFIX = "«data PNGf"


class ClipboardError(Exception):
    pass


def available() -> bool:
    return sys.platform == "darwin" and shutil.which("osascript") is not None


async def copy(text: str) -> bool:
    """Whether a clipboard command took the text. False without one, or when it failed."""
    command = _copy_command()
    if command is None:
        return False
    process = await asyncio.create_subprocess_exec(
        *command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    await process.communicate(text.encode())
    return process.returncode == 0


def _copy_command() -> list[str] | None:
    if sys.platform == "darwin":
        return ["pbcopy"]
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        return ["wl-copy"]
    if os.environ.get("DISPLAY") and shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    return None


async def paste() -> Attachment | str:
    """A copied file or image as an attachment, else the clipboard's text ("" when empty).
    Files come first: Finder also puts a copied file's icon on the clipboard as an image.
    Raises ClipboardError, or FileNotFoundError for a copied folder."""
    kinds = await _osascript("clipboard info")
    if _FILE in kinds:
        return load_attachment(await _osascript(f"POSIX path of (the clipboard as {_FILE})"))
    if any(kind in kinds for kind in _IMAGES):
        return _image(await _osascript(f"the clipboard as {_PNG}"))
    return await _run("pbpaste")


def _image(printed: str) -> Attachment:
    """osascript prints the image as «data PNGf89504E47…»."""
    data = bytes.fromhex(printed.strip().removeprefix(_DATA_PREFIX).removesuffix("»"))
    return Attachment(name=f"pasted-{datetime.now():%H%M%S}.png", media_type="image/png", data=data)


async def _osascript(script: str) -> str:
    return (await _run("osascript", "-e", script)).strip()


async def _run(*command: str) -> str:
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await process.communicate()
    if process.returncode != 0:
        raise ClipboardError(f"Couldn't read the clipboard: {err.decode(errors='replace').strip()}")
    return out.decode()
