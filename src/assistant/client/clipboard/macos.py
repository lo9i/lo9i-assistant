"""The Mac clipboard: pasting with `osascript` and `pbpaste`, copying with `pbcopy`."""

import shutil

from assistant.client.clipboard import process
from assistant.client.files import load_attachment
from assistant.core.attachments import Attachment

_FILE = "«class furl»"
_PNG = "«class PNGf»"
# Image types macOS converts to PNG on request. A screenshot copied to the clipboard has both.
_IMAGES = (_PNG, "TIFF picture")
_DATA_PREFIX = "«data PNGf"


def available() -> bool:
    return shutil.which("osascript") is not None


def copy_command() -> list[str]:
    return ["pbcopy"]


async def paste() -> Attachment | str:
    """Files come first: Finder also puts a copied file's icon on the clipboard as an image."""
    kinds = await _osascript("clipboard info")
    if _FILE in kinds:
        return load_attachment(await _osascript(f"POSIX path of (the clipboard as {_FILE})"))
    if any(kind in kinds for kind in _IMAGES):
        return _image(await _osascript(f"the clipboard as {_PNG}"))
    return await process.text("pbpaste")


def _image(printed: str) -> Attachment:
    """osascript prints the image as «data PNGf89504E47…»."""
    return process.png(bytes.fromhex(printed.removeprefix(_DATA_PREFIX).removesuffix("»")))


async def _osascript(script: str) -> str:
    return (await process.text("osascript", "-e", script)).strip()
