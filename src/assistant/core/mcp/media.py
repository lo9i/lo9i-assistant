"""Images and audio in MCP tool results, kept out of checkpoints like attachments: images are saved
as uploads and referred to (core/attachments.py loads them for each model call); audio is saved
and transcribed once, since models don't take audio."""

import asyncio
import base64
import binascii
import mimetypes

from langgraph.store.base import BaseStore
from mcp.types import AudioContent, ImageContent

from assistant.core.attachments import Attachment, Block, reference
from assistant.core.speech import preferences
from assistant.core.speech.transcriber import Transcriber
from assistant.core.speech.voice import transcribe_tool_audio


class ToolMedia:
    def __init__(self, transcriber: Transcriber, store: BaseStore) -> None:
        self._transcriber = transcriber
        self._store = store

    async def block(self, content: ImageContent | AudioContent, tool: str) -> Block:
        """The block that stands for an image or audio the tool returned."""
        try:
            attachment = _attachment(content, tool)
        except binascii.Error:
            return {"type": "text", "text": f"[{content.type} from the tool that couldn't be read]"}
        if isinstance(content, ImageContent):
            return await asyncio.to_thread(reference, attachment)
        speech = await preferences.in_use(self._store)
        return await transcribe_tool_audio(self._transcriber, attachment, speech)


def _attachment(content: ImageContent | AudioContent, tool: str) -> Attachment:
    extension = mimetypes.guess_extension(content.mime_type) or ""
    data = base64.b64decode(content.data, validate=True)
    return Attachment(name=f"{tool}-{content.type}{extension}", media_type=content.mime_type, data=data)
