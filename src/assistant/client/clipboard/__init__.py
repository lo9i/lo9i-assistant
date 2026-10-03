"""The clipboard of the machine the terminal app runs on.

Pasting (Ctrl+V): terminals pass pasted text to the app but never images or files, so the client
reads the clipboard itself. Clients check `available()` at start. One module per platform:
`macos` and `linux`.

Copying: with the system's clipboard command. Over SSH there's none worth using, so clients also
copy through the terminal (OSC 52), which reaches the clipboard of the computer in front of the
user, in terminals that support it.
"""

import asyncio
import sys

from assistant.client.clipboard import linux, macos
from assistant.client.clipboard.process import ClipboardError
from assistant.core.attachments import Attachment

__all__ = ["ClipboardError", "available", "copy", "paste"]


def available() -> bool:
    if sys.platform == "darwin":
        return macos.available()
    return linux.find_reader() is not None


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
    return macos.copy_command() if sys.platform == "darwin" else linux.copy_command()


async def paste() -> Attachment | str:
    """A copied file or image as an attachment, else the clipboard's text.
    Raises ClipboardError, or FileNotFoundError for a copied folder."""
    if sys.platform == "darwin":
        return await macos.paste()
    reader = linux.find_reader()
    if reader is None:
        raise ClipboardError("There's no clipboard to read: install wl-clipboard or xclip.")
    return await linux.paste(reader)
