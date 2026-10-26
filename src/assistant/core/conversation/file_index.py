"""The files each conversation's messages refer to, its subagents' included, so the Files list (core/agent/files.py)
pages over them without reading every conversation's checkpoint. One Store record per listed conversation under
("conversation_files", user_id), written when a run in it ends (core/agent/runs.py) and for conversations with
none when the daemon starts, and gone with the conversation."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass

from langchain_core.messages import BaseMessage
from langgraph.store.base import BaseStore

from assistant.core import conversations
from assistant.core.agent_tasks import sent
from assistant.core.attachments import tool_uploads, user_uploads

_SCAN_LIMIT = 100_000


@dataclass
class FileReference:
    # Relative to the uploads dir.
    path: str
    name: str
    media_type: str
    # The tool whose result brought it (read_email, mcp__<server>__<tool>); "" for a file the user sent.
    tool: str


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("conversation_files", user_id)


def references(messages: Sequence[BaseMessage]) -> list[FileReference]:
    """Each file's reference with the tool that brought it, "" for the user's (to an agent at work too)."""
    found = [("", r) for r in [*user_uploads(messages), *sent.uploads(messages)]] + tool_uploads(messages)
    return [FileReference(r["path"], r["name"], r["media_type"], tool) for tool, r in found]


async def save(store: BaseStore, user_id: str, thread_id: str, files: list[FileReference]) -> None:
    """Only for a listed conversation (a scheduled job's runs aren't), and only when its files changed: each write
    tells the apps' Files lists to load again."""
    if await conversations.load(store, user_id, thread_id) is None:
        return
    record = {"files": [asdict(f) for f in files]}
    kept = await store.aget(_namespace(user_id), thread_id)
    if kept is None or kept.value != record:
        await store.aput(_namespace(user_id), thread_id, record)


async def of_user(store: BaseStore, user_id: str) -> dict[str, list[FileReference]]:
    """The files of each conversation indexed, by its thread id."""
    items = await store.asearch(_namespace(user_id), limit=_SCAN_LIMIT)
    return {item.key: [FileReference(**f) for f in item.value.get("files", [])] for item in items}


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """For a deleted conversation."""
    await store.adelete(_namespace(user_id), thread_id)
