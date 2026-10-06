"""Attachments in messages.

Stored form: files are saved under the uploads dir and the message keeps a reference block
(a LangChain `non_standard` block), so checkpoints never hold file contents.
Request form: `hydrate` replaces each reference with the file's content before the model call.
Hydration is deterministic, so every turn renders earlier messages identically and the prompt
cache and thinking blocks stay valid.

Tool results keep their references (images from MCP tools) in the message's `artifact`, which
LangChain never sends to the model: the tool node accepts only its own block types as content.
`hydrate` adds them to the result, or, for APIs that take images only in user messages, to a user
message after the results, built for the request and never saved.
"""

import base64
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from assistant.core import uploads

Block = dict[str, Any]

# The name on the user message that carries images from tool results, so it isn't taken for the
# user speaking (core/llm/copilot.py).
TOOL_MEDIA_SENDER = "tool_results"
_TOOL_MEDIA_INTRO = "[Images from the tool results above]"


@dataclass
class Attachment:
    name: str
    media_type: str
    data: bytes


def to_content(text: str, attachments: Sequence[Attachment]) -> list[Block]:
    """Save attachments and build stored message content. Raises ValueError on unsupported types."""
    for attachment in attachments:
        _converter_for(attachment)
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
    reference = {"path": path, "name": attachment.name, "media_type": attachment.media_type}
    return {"type": "non_standard", "value": {"upload": reference}}


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


def _hydrate_block(block: Any) -> list[Any]:
    reference = _reference(block)
    if reference is None:
        return [block]
    data = uploads.load(reference["path"])
    if data is None:
        return [_text(f"[Uploaded file {reference['name']} is no longer available]")]
    attachment = Attachment(name=reference["name"], media_type=reference["media_type"], data=data)
    where = uploads.absolute(reference["path"])
    try:
        convert = _converter_for(attachment)
    except ValueError:
        # Only tool results refer to such files (an email's spreadsheet): chat attachments are checked
        # when they're sent.
        return [_text(f"[File {attachment.name} ({attachment.media_type}) saved at {where}; open it with bash]")]
    return [_text(f"[Uploaded file {attachment.name}, saved at {where}]"), convert(attachment)]


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
