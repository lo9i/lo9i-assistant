"""Turns voice attachments into transcript text blocks before a message is stored."""

import asyncio
from collections.abc import Sequence

from assistant.core import uploads
from assistant.core.attachments import Attachment, Block
from assistant.core.speech.preferences import SpeechSettings
from assistant.core.speech.transcriber import Transcriber, Transcript

# Voice audio is kept apart from other uploads, under uploads/audio/.
_AUDIO_FOLDER = "audio"


def is_voice(attachment: Attachment) -> bool:
    return attachment.media_type.startswith("audio/")


async def transcribe_voice(
    transcriber: Transcriber, attachments: Sequence[Attachment], speech: SpeechSettings
) -> tuple[list[Transcript], list[Block]]:
    """Transcripts and their text blocks, in order. The audio is kept in the uploads folder."""
    transcripts = [await transcriber.transcribe(a.data, speech.model, speech.languages) for a in attachments]
    paths = [await asyncio.to_thread(uploads.save, a.name, a.data, _AUDIO_FOLDER) for a in attachments]
    blocks = [_block(t, uploads.absolute(p)) for t, p in zip(transcripts, paths, strict=True)]
    return transcripts, blocks


def _block(transcript: Transcript, path) -> Block:
    header = f"[Voice message, {transcript.seconds}s, {transcript.language}, transcribed; audio at {path}]"
    return {"type": "text", "text": f"{header}\n{transcript.text or '(no speech detected)'}"}
