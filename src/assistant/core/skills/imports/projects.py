"""The project folders whose skills are offered: those the assistant knows, where conversations were handed to a
coding agent (core/conversation/agent_folders.py), the agents' workspace included."""

from pathlib import Path

from langgraph.store.base import BaseStore

from assistant.core.conversation import agent_folders


async def known(store: BaseStore, user_id: str) -> list[Path]:
    offered = await agent_folders.offered(store, user_id)
    return [Path(offered.workspace), *(Path(f) for f in offered.recent)]
