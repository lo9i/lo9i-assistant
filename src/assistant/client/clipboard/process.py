"""Running the commands that read the clipboard."""

import asyncio
from datetime import datetime

from assistant.core.attachments import Attachment


class ClipboardError(Exception):
    pass


async def run(*command: str) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await process.communicate()
    if process.returncode != 0:
        raise ClipboardError(f"Couldn't read the clipboard: {err.decode(errors='replace').strip()}")
    return out


async def text(*command: str) -> str:
    return (await run(*command)).decode()


def png(data: bytes) -> Attachment:
    return Attachment(name=f"pasted-{datetime.now():%H%M%S}.png", media_type="image/png", data=data)
