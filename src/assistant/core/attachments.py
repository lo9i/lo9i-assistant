"""Converts gateway attachments into model content blocks."""

import base64
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

Block = dict[str, Any]


@dataclass
class Attachment:
    name: str
    media_type: str
    data: bytes


def to_content(text: str, attachments: Sequence[Attachment]) -> list[Block]:
    """Build message content: attachments first, then the text. Raises ValueError on unsupported types."""
    blocks = [_to_block(a) for a in attachments]
    return [*blocks, {"type": "text", "text": text}] if text else blocks


def _to_block(attachment: Attachment) -> Block:
    for matches, convert in _CONVERTERS:
        if matches(attachment.media_type):
            return convert(attachment)
    raise ValueError(f"Unsupported attachment type: {attachment.media_type} ({attachment.name})")


def _base64(attachment: Attachment) -> str:
    return base64.b64encode(attachment.data).decode()


def _image_block(attachment: Attachment) -> Block:
    return {"type": "image", "base64": _base64(attachment), "mime_type": attachment.media_type}


def _pdf_block(attachment: Attachment) -> Block:
    return {"type": "file", "base64": _base64(attachment), "mime_type": attachment.media_type}


def _text_file_block(attachment: Attachment) -> Block:
    body = attachment.data.decode(errors="replace")
    return {"type": "text", "text": f'<file name="{attachment.name}">\n{body}\n</file>'}


_CONVERTERS: list[tuple[Callable[[str], bool], Callable[[Attachment], Block]]] = [
    (lambda media_type: media_type.startswith("image/"), _image_block),
    (lambda media_type: media_type == "application/pdf", _pdf_block),
    (lambda media_type: media_type.startswith("text/"), _text_file_block),
]
