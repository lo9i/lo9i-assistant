"""Turns Telegram photos, documents, voice notes and audio files into attachments."""

from telegram import Message

from assistant.core.attachments import Attachment


class UnsupportedMedia(Exception):
    pass


async def attachments_from(message: Message) -> list[Attachment]:
    if message.video_note:
        raise UnsupportedMedia("Video messages aren't supported.")
    if message.voice:
        return [await _voice(message)]
    if message.audio:
        return [await _audio(message)]
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


async def _voice(message: Message) -> Attachment:
    voice = message.voice
    data = await (await voice.get_file()).download_as_bytearray()
    return Attachment(name=f"voice-{voice.file_unique_id}.ogg", media_type=voice.mime_type or "audio/ogg", data=bytes(data))


async def _audio(message: Message) -> Attachment:
    audio = message.audio
    data = await (await audio.get_file()).download_as_bytearray()
    name = audio.file_name or f"audio-{audio.file_unique_id}"
    return Attachment(name=name, media_type=audio.mime_type or "audio/mpeg", data=bytes(data))
