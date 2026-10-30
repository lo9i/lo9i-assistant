"""Attachments in messages.

Stored form: files are saved under the uploads dir and the message keeps a reference block
(a LangChain `non_standard` block), so checkpoints never hold file contents.
Request form: `hydrate` replaces each reference with the file's content before the model call.
A file the model can't read (a video, an archive) is sent as a note with where it was saved, to
open with bash; an agent a conversation is handed to gets every file's path. Hydration is
deterministic, so every turn renders earlier messages identically and the prompt
cache and thinking blocks stay valid. Images go scaled down (core/images.py); the file keeps its size.

Tool results keep their references (images from MCP tools) in the message's `artifact`, which
LangChain never sends to the model: the tool node accepts only its own block types as content.
`hydrate` adds them to the result, or, for APIs that take images only in user messages, to a user
message after the results, built for the request and never saved.
"""

import base64
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from assistant.core import images, uploads

Block = dict[str, Any]

# The name on the user message that carries images from tool results, so it isn't taken for the
# user speaking (core/llm/copilot.py).
TOOL_MEDIA_SENDER = "tool_results"
_TOOL_MEDIA_INTRO = "[Images from the tool results above]"
# Images fitted for the model (core/images.py) kept in memory, so each call of a run doesn't fit them again.
_FITTED_IMAGES = 64


@dataclass
class Attachment:
    name: str
    media_type: str
    data: bytes


def to_content(text: str, attachments: Sequence[Attachment]) -> list[Block]:
    """Save attachments, of any type, and build stored message content."""
    blocks = [reference(a) for a in attachments]
    return [*blocks, {"type": "text", "text": text}] if text else blocks


def hydrate(messages: Sequence[BaseMessage], images_in_tool_results: bool) -> list[BaseMessage]:
    """Messages with every upload reference replaced by the file's content. Without
    `images_in_tool_results`, the files from tool results go in a user message after them."""
    if images_in_tool_results:
        messages = [_with_tool_media(m) for m in messages]
    else:
        messages = _tool_media_after_results(messages)
    return [_hydrate_message(m) for m in messages]


def reference(attachment: Attachment) -> Block:
    """Saves the file and returns the block that refers to it."""
    path = uploads.save(attachment.name, attachment.data)
    return referring({"path": path, "name": attachment.name, "media_type": attachment.media_type})


def referring(upload: dict[str, str]) -> Block:
    """The block that refers to a file saved under the uploads dir (path, name, media_type)."""
    return {"type": "non_standard", "value": {"upload": upload}}


def _with_tool_media(message: BaseMessage) -> BaseMessage:
    """A tool result with its references after its content."""
    references = _tool_references(message)
    if not references:
        return message
    return message.model_copy(update={"content": [*_blocks(message.content), *references]})


def _tool_media_after_results(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    result: list[BaseMessage] = []
    moved: list[Block] = []
    for message in messages:
        if moved and not isinstance(message, ToolMessage):
            result.append(_tool_media_message(moved))
            moved = []
        references = _tool_references(message)
        if references:
            notes = [_moved_note(r) for r in references]
            message = message.model_copy(update={"content": [*_blocks(message.content), *notes]})
            moved += references
        result.append(message)
    return [*result, _tool_media_message(moved)] if moved else result


def _moved_note(block: Block) -> Block:
    name = (_reference(block) or {}).get("name", "a file")
    return _text(f"[{name}: in the next message]")


def carries_files(message: BaseMessage) -> bool:
    """A tool result whose artifact refers to saved files, which `hydrate` adds to the request."""
    return bool(_tool_references(message))


def carries_user_files(message: BaseMessage) -> bool:
    """A user's message that refers to saved files, which `hydrate` adds to the request."""
    if not isinstance(message, HumanMessage) or not isinstance(message.content, list):
        return False
    return any(map(is_reference, message.content))


def _tool_references(message: BaseMessage) -> list[Block]:
    if not isinstance(message, ToolMessage) or not isinstance(message.artifact, list):
        return []
    return [block for block in message.artifact if _reference(block)]


def _blocks(content: str | list[Any]) -> list[Any]:
    if isinstance(content, str):
        return [_text(content)] if content else []
    return list(content)


def _tool_media_message(references: list[Block]) -> HumanMessage:
    return HumanMessage([_text(_TOOL_MEDIA_INTRO), *references], name=TOOL_MEDIA_SENDER)


def _hydrate_message(message: BaseMessage) -> BaseMessage:
    if not isinstance(message, HumanMessage | ToolMessage) or not isinstance(message.content, list):
        return message
    if not any(_reference(block) for block in message.content):
        return message
    content = [hydrated for block in message.content for hydrated in _hydrate_block(block)]
    return message.model_copy(update={"content": content})


def is_reference(block: Any) -> bool:
    return _reference(block) is not None


def _reference(block: Any) -> dict[str, str] | None:
    if isinstance(block, dict) and block.get("type") == "non_standard":
        return block.get("value", {}).get("upload")
    return None


def upload_paths(messages: Sequence[BaseMessage]) -> list[str]:
    """The uploads (relative paths) the user's messages and tool results refer to."""
    return [
        reference["path"]
        for message in messages
        for block in _stored_references(message)
        if (reference := _reference(block)) is not None
    ]


def user_uploads(messages: Sequence[BaseMessage]) -> list[dict[str, str]]:
    """The references of the files the user sent, oldest first. Files from tool results aren't theirs."""
    return [
        reference
        for message in messages
        if isinstance(message, HumanMessage) and message.name != TOOL_MEDIA_SENDER and isinstance(message.content, list)
        for block in message.content
        if (reference := _reference(block)) is not None
    ]


def tool_uploads(messages: Sequence[BaseMessage]) -> list[tuple[str, dict[str, str]]]:
    """The references of the files tool results brought (an email's attachments, an MCP tool's images),
    each with the tool's name, oldest first."""
    return [
        (message.name or "", reference)
        for message in messages
        for block in _tool_references(message)
        if (reference := _reference(block)) is not None
    ]


def _stored_references(message: BaseMessage) -> list[Any]:
    if isinstance(message, HumanMessage) and isinstance(message.content, list):
        return message.content
    return _tool_references(message)


def left_out(message: HumanMessage) -> HumanMessage:
    """The user's message with each file it refers to replaced by a note saying where it's saved, sent once
    its files are old (conversation/trim.py) or the request was too large (conversation/oversized.py)."""
    if not isinstance(message.content, list):
        return message
    content = [_left_out_note(r) if (r := _reference(block)) else block for block in message.content]
    return message.model_copy(update={"content": content})


def _left_out_note(reference: dict[str, str]) -> Block:
    where = uploads.absolute(reference["path"])
    return _text(f"[File {reference['name']} left out to save space; saved at {where}]")


def _hydrate_block(block: Any) -> list[Any]:
    reference = _reference(block)
    if reference is None:
        return [block]
    where = uploads.absolute(reference["path"])
    if not where.is_file():
        return [_text(f"[Uploaded file {reference['name']} is no longer available]")]
    attachment = _loaded(reference, where)
    try:
        convert = _converter_for(attachment)
    except ValueError:
        # A file the model can't take (a video, a spreadsheet): it can open it with bash.
        return [_text(f"[File {attachment.name} ({attachment.media_type}) saved at {where}; open it with bash]")]
    return [_text(f"[Uploaded file {attachment.name}, saved at {where}]"), convert(attachment)]


def _loaded(reference: dict[str, str], where: Path) -> Attachment:
    name, media_type = reference["name"], reference["media_type"]
    if media_type.startswith("image/"):
        data, media_type = _fitted_image(where, media_type)
        return Attachment(name=name, media_type=media_type, data=data)
    return Attachment(name=name, media_type=media_type, data=where.read_bytes())


@lru_cache(maxsize=_FITTED_IMAGES)
def _fitted_image(where: Path, media_type: str) -> tuple[bytes, str]:
    """By path: an upload never changes, each is saved in a folder of its own (core/uploads.py)."""
    return images.fit(where.read_bytes(), media_type)


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
