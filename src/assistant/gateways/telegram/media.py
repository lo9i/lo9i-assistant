"""Turns Telegram photos and documents into attachments."""

from telegram import Message

from assistant.core.attachments import Attachment


class UnsupportedMedia(Exception):
    pass


async def attachments_from(message: Message) -> list[Attachment]:
    if message.voice or message.audio or message.video_note:
        raise UnsupportedMedia("Voice and audio messages aren't supported yet.")
    if message.photo:
        return [await _photo(message)]
    if message.document:
        return [await _document(message)]
    return []


async def _photo(message: Message) -> Attachment:
    largest = message.photo[-1]
    data = await (await largest.get_file()).download_as_bytearray()
    return Attachment(name=f"photo-{largest.file_unique_id}.jpg", media_type="image/jpeg", data=bytes(data))


async def _document(message: Message) -> Attachment:
    document = message.document
    data = await (await document.get_file()).download_as_bytearray()
    name = document.file_name or f"file-{document.file_unique_id}"
    return Attachment(name=name, media_type=document.mime_type or "application/octet-stream", data=bytes(data))
