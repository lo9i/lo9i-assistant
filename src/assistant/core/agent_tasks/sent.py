"""What the user sent a task while it worked, kept as they sent it. The agent gets the text with where each
file was saved (it reads them from disk), and its worker writes a `user` step with that text and the
message's id (docs/agent-plugins.md). The daemon wrote the message, with what the user wrote and the files'
upload references beside the text the agent gets; it puts those back in the step, so the conversation keeps
the files as any message's: the Files list, deleting the conversation, and history and the apps showing them
as files instead of the note with their paths."""

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from assistant.core.agent_tasks.steps import STEPS, Upload, files_of, parse


def message(text: str, said: str, files: list[Upload]) -> dict[str, Any]:
    """The message for the task's inbox: `text` for the agent, what the user wrote and their files for the daemon."""
    return {"kind": "message", "text": text, "said": said, "files": files}


def message_id(step: str) -> str:
    """The id of the message a `user` step passed on; "" for any other step."""
    fields = parse(step)
    return fields.get("id", "") if fields.get("kind") == "user" else ""


def as_sent(step: str, sent: dict[str, Any] | None) -> str:
    """The `user` step with what the user wrote and their files, from the message it passed on; as it was
    when that message isn't there or came from elsewhere."""
    if not sent or "said" not in sent:
        return step
    return json.dumps(json.loads(step) | {"text": sent["said"], "files": sent.get("files", [])})


def user_step(sent: dict[str, Any]) -> str:
    """A `user` step for a message the task ended without taking, which the next task gets."""
    return as_sent(json.dumps({"kind": "user", "text": sent.get("text", "")}), sent)


def said(messages: Sequence[dict[str, Any]]) -> str:
    """What the user wrote in `messages`, in order, as one message: the text the agent got where the daemon didn't
    keep what they wrote."""
    return "\n\n".join(part for m in messages if (part := str(m.get("said", m.get("text", ""))).strip()))


def files(messages: Sequence[dict[str, Any]]) -> list[Upload]:
    """The files the user sent with `messages`, in order."""
    return [upload for m in messages for upload in m.get("files", [])]


def uploads(messages: Sequence[BaseMessage]) -> list[Upload]:
    """The files the user sent handed-off agents while they worked, kept with their replies' steps."""
    return [
        upload
        for message in messages
        if isinstance(message, AIMessage)
        for step in message.response_metadata.get(STEPS, [])
        for upload in files_of(step)
    ]
