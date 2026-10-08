"""Conversations handed to another agent. A plugin can bring one (`agent:` in its server.yaml, like Claude
Code): the apps offer its command (/claude, with a folder or picking one), and from then on each of the
user's messages in that conversation runs as one of the agent's tasks in that folder
(core/agent_tasks/) and its reply comes back, instead of the assistant's model answering. Both are added
to the conversation, so when the user hands it back (/claude off) the assistant sees what was said, and
that message's turn header says it was another agent, once. Kept in the Store per conversation.
"""

from dataclasses import asdict, dataclass

from langgraph.store.base import BaseStore

from assistant.core.conversation import prompts
from assistant.core.conversation.turn_header import note_block
from assistant.core.mcp import servers


@dataclass(frozen=True)
class Agent:
    """An agent a plugin brings."""

    # The plugin it comes with.
    server: str
    # The apps' command for it, without the slash: "claude".
    command: str
    name: str


@dataclass(frozen=True)
class Handoff:
    """The agent a conversation is with, and the folder it works in."""

    server: str
    command: str
    name: str
    folder: str


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("handoffs", user_id)


async def agents(store: BaseStore) -> list[Agent]:
    """The agents the turned-on plugins bring, by command. A plugin written for an older version of lo9i
    (no worker) isn't one until it's updated (`outdated`)."""
    found = [s for s in await servers.load_all(store) if s.enabled and s.agent_command and s.agent_worker]
    return sorted((Agent(s.name, s.agent_command, s.agent_name) for s in found), key=lambda a: a.command)


async def outdated(store: BaseStore, command: str) -> str:
    """The name of the plugin that brings `command` in a format this lo9i no longer runs; "" for none."""
    found = [s for s in await servers.load_all(store) if s.agent_command == command and not s.agent_worker]
    return found[0].agent_name if found else ""


async def current(store: BaseStore, user_id: str, thread_id: str) -> Handoff | None:
    item = await store.aget(_namespace(user_id), thread_id)
    return Handoff(**item.value["handoff"]) if item and item.value.get("handoff") else None


async def hand(store: BaseStore, user_id: str, thread_id: str, handoff: Handoff) -> None:
    await store.aput(_namespace(user_id), thread_id, {"handoff": asdict(handoff)})


async def take_back(store: BaseStore, user_id: str, thread_id: str) -> Handoff | None:
    """Back to the assistant; its next message's turn header says who answered meanwhile. Returns the
    handoff it ended, None when the conversation was the assistant's already."""
    ended = await current(store, user_id, thread_id)
    if ended is not None:
        await store.aput(_namespace(user_id), thread_id, {"handoff": None, "returned_from": asdict(ended)})
    return ended


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """For a deleted conversation."""
    await store.adelete(_namespace(user_id), thread_id)


async def take_notice(store: BaseStore, user_id: str, thread_id: str) -> list[dict[str, str]]:
    """The turn header note after the conversation came back from an agent, once."""
    item = await store.aget(_namespace(user_id), thread_id)
    returned = item.value.get("returned_from") if item else None
    if not returned:
        return []
    await store.aput(_namespace(user_id), thread_id, {"handoff": None})
    return [note_block(prompts.load("handed_back").format(name=returned["name"], folder=returned["folder"]))]
