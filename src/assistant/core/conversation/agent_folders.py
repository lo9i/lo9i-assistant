"""The folders the apps offer when a conversation is handed to an agent (core/conversation/handoffs.py), so
the user picks one instead of typing its path: the agents' workspace, the folders used before (newest
first, kept in the Store per user), and the folders inside one, to browse to a project not used yet.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from langgraph.store.base import BaseStore

from assistant.core.config import settings

_RECENT_LIMIT = 10
_KEY = "recent"


@dataclass(frozen=True)
class AgentFolders:
    # Where an agent works when the user has no project in mind; created when first handed to.
    workspace: str
    # Folders used before that still exist, newest first; never the workspace.
    recent: list[str]
    # Where browsing starts.
    home: str


@dataclass(frozen=True)
class FolderListing:
    path: str
    # None at the root.
    parent: str | None
    # Full paths of the folders inside, by name; hidden ones left out.
    children: list[str]


class FolderError(Exception):
    pass


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("agent_folders", user_id)


def workspace() -> Path:
    return Path(settings.agent_workspace_dir).expanduser()


async def offered(store: BaseStore, user_id: str) -> AgentFolders:
    saved = await _saved(store, user_id)
    existing = await asyncio.to_thread(lambda: [f for f in saved if Path(f).is_dir()])
    return AgentFolders(str(workspace()), existing, str(Path.home()))


async def remember(store: BaseStore, user_id: str, folder: Path) -> None:
    """Moves `folder` to the front of the recent ones; the workspace is offered on its own."""
    if folder == workspace():
        return
    saved = [f for f in await _saved(store, user_id) if f != str(folder)]
    await store.aput(_namespace(user_id), _KEY, {"folders": [str(folder), *saved][:_RECENT_LIMIT]})


async def children(folder: str) -> FolderListing:
    """Raises FolderError when `folder` isn't an existing folder given by its full path, or can't be read."""
    where = Path(folder).expanduser()
    if not where.is_absolute():
        raise FolderError(f"{folder} isn't a full path.")
    try:
        inside = await asyncio.to_thread(_folders_in, where)
    except OSError as e:
        raise FolderError(f"Can't read {folder}: {e.strerror or e}") from e
    return FolderListing(str(where), str(where.parent) if where.parent != where else None, inside)


async def ensure_workspace() -> None:
    await asyncio.to_thread(workspace().mkdir, parents=True, exist_ok=True)


def _folders_in(where: Path) -> list[str]:
    found = (p for p in where.iterdir() if not p.name.startswith(".") and p.is_dir())
    return sorted((str(p) for p in found), key=lambda p: Path(p).name.lower())


async def _saved(store: BaseStore, user_id: str) -> list[str]:
    item = await store.aget(_namespace(user_id), _KEY)
    return list(item.value.get("folders", [])) if item else []
