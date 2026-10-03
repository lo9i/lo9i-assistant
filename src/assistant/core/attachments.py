"""Attachments in messages.

Stored form: files are saved under the uploads dir and the message keeps a reference block
(a LangChain `non_standard` block), so checkpoints never hold file contents.
Request form: `hydrate` replaces each reference with the file's content before the model call.
Hydration is deterministic, so every turn renders earlier messages identically and the prompt
cache and thinking blocks stay valid.
"""

import base64
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from assistant.core import uploads

Block = dict[str, Any]


@dataclass
class Attachment:
    name: str
    media_type: str
    data: bytes


def to_content(text: str, attachments: Sequence[Attachment]) -> list[Block]:
    """Save attachments and build stored message content. Raises ValueError on unsupported types."""
    for attachment in attachments:
        _converter_for(attachment)
    blocks = [_reference_block(a) for a in attachments]
    return [*blocks, {"type": "text", "text": text}] if text else blocks


def hydrate(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Messages with every upload reference replaced by the file's content."""
    return [_hydrate_message(m) for m in messages]


def _reference_block(attachment: Attachment) -> Block:
    path = uploads.save(attachment.name, attachment.data)
    reference = {"path": path, "name": attachment.name, "media_type": attachment.media_type}
    return {"type": "non_standard", "value": {"upload": reference}}


def _hydrate_message(message: BaseMessage) -> BaseMessage:
    if not isinstance(message, HumanMessage) or not isinstance(message.content, list):
        return message
    if not any(_reference(block) for block in message.content):
        return message
    content = [hydrated for block in message.content for hydrated in _hydrate_block(block)]
    return message.model_copy(update={"content": content})


def _reference(block: Any) -> dict[str, str] | None:
    if isinstance(block, dict) and block.get("type") == "non_standard":
        return block.get("value", {}).get("upload")
    return None


def upload_paths(messages: Sequence[BaseMessage]) -> list[str]:
    """The uploads (relative paths) the user's messages refer to."""
    return [
        reference["path"]
        for message in messages
        if isinstance(message, HumanMessage) and isinstance(message.content, list)
        for block in message.content
        if (reference := _reference(block)) is not None
    ]


def _hydrate_block(block: Any) -> list[Any]:
    reference = _reference(block)
    if reference is None:
        return [block]
    data = uploads.load(reference["path"])
    if data is None:
        return [_text(f"[Uploaded file {reference['name']} is no longer available]")]
    attachment = Attachment(name=reference["name"], media_type=reference["media_type"], data=data)
    note = _text(f"[Uploaded file {attachment.name}, saved at {uploads.absolute(reference['path'])}]")
    return [note, _converter_for(attachment)(attachment)]


def _converter_for(attachment: Attachment) -> Callable[[Attachment], Block]:
    for matches, convert in _CONVERTERS:
        if matches(attachment.media_type):
            return convert
    raise ValueError(f"Unsupported attachment type: {attachment.media_type} ({attachment.name})")


def _text(text: str) -> Block:
    return {"type": "text", "text": text}


def _base64(attachment: Attachment) -> str:
    return base64.b64encode(attachment.data).decode()


def _image_block(attachment: Attachment) -> Block:
    return {"type": "image", "base64": _base64(attachment), "mime_type": attachment.media_type}


def _pdf_block(attachment: Attachment) -> Block:
    return {"type": "file", "base64": _base64(attachment), "mime_type": attachment.media_type}


def _text_file_block(attachment: Attachment) -> Block:
    body = attachment.data.decode(errors="replace")
    return _text(f'<file name="{attachment.name}">\n{body}\n</file>')


_CONVERTERS: list[tuple[Callable[[str], bool], Callable[[Attachment], Block]]] = [
    (lambda media_type: media_type.startswith("image/"), _image_block),
    (lambda media_type: media_type == "application/pdf", _pdf_block),
    (lambda media_type: media_type.startswith("text/"), _text_file_block),
]
