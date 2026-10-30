import asyncio
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import AIMessage

from assistant.core import conversations, inbox, notifications
from assistant.core.agent.archive import ArchiveMixin
from assistant.core.agent.session import Session
from assistant.core.agent.thread_files import ThreadFilesMixin, referenced
from assistant.core.channels.chat import threads as chat_threads
from assistant.core.config import settings
from assistant.core.conversation import choices, ended, file_index, handoffs, moved, pinned, queued, summaries
from assistant.core.home import pins as home_pins

# What the home conversation from before the inbox is listed as.
_HOME_TITLE = "Home (before the inbox)"


class ConversationError(Exception):
    pass


class ConversationBusyError(ConversationError):
    """A reply is running in the conversation."""


class ThreadsMixin(ArchiveMixin, ThreadFilesMixin):
    """Conversations. A client (terminal, web page) holds its own and says when it leaves one. A message
    written outside a conversation goes to the inbox (core/inbox.py), which routes it; a chat channel
    (Telegram) writes every new message there and keeps the conversation its last one went to."""

    async def session(self, user_id: str, channel: str) -> Session:
        """Where the channel writes a new message: the inbox."""
        return Session(user_id=user_id, channel=channel, thread_id=await self.inbox_thread(user_id))

    async def inbox_thread(self, user_id: str) -> str:
        """The inbox's id, started on first use."""
        store = self._storage.store
        if (thread_id := await inbox.current(store, user_id)) is None:
            thread_id = await self.new_thread(user_id)
            await inbox.start(store, user_id, thread_id)
        return thread_id

    async def retire_home(self, user_id: str) -> str | None:
        """Keeps the home conversation from before the inbox as an archived conversation, once: readable
        and listed, never routed to, and what's new in it archived into memory in the background. Chat
        channels were on home or a side conversation; their next message goes to the inbox. Returns the
        retired conversation's id."""
        store = self._storage.store
        if (home_id := await inbox.legacy_home(store, user_id)) is None:
            return None
        async with self._conversations_lock:
            await conversations.archive(store, user_id, home_id, _HOME_TITLE)
        for item in await store.asearch(inbox.channels_namespace(user_id), limit=100):
            await store.adelete(inbox.channels_namespace(user_id), item.key)
        await inbox.drop_legacy_home(store, user_id)
        self.leave_thread(user_id, home_id)
        self.bus.publish("conversations")
        return home_id

    async def channel_thread(self, user_id: str, channel: str) -> str:
        """The conversation the channel's last message went to, or the inbox."""
        return await inbox.channel_thread(self._storage.store, user_id, channel) or await self.inbox_thread(user_id)

    async def channel_wrote(self, user_id: str, channel: str, thread_id: str) -> None:
        """The channel's message went to `thread_id`. What's new in the conversation its last one went to,
        when that's another, is archived in the background."""
        left = await inbox.channel_thread(self._storage.store, user_id, channel)
        if left == thread_id:
            return
        await self._storage.store.aput(inbox.channels_namespace(user_id), channel, {"thread_id": thread_id})
        if left is not None:
            self.leave_thread(user_id, left)

    async def new_thread(self, user_id: str) -> str:
        """A new conversation's id. It's saved, and listed, once it has a message."""
        return f"{user_id}:{uuid4().hex[:12]}"

    async def require_conversation(self, user_id: str, thread_id: str) -> None:
        """Raises ConversationError unless the conversation exists, before a client resumes it."""
        if await conversations.load(self._storage.store, user_id, thread_id) is None:
            raise ConversationError(f"No conversation {thread_id}.")

    async def delete_conversation(self, user_id: str, thread_id: str) -> None:
        """Delete the conversation: its messages, its place in the list and in search, and the files
        and voice recordings sent in it, but those another conversation refers to too. What memory learned from it
        stays. A channel on it (Telegram) starts
        a new one with its next message. Raises ConversationError for an unknown one,
        ConversationBusyError while a reply is running."""
        listed = await conversations.load(self._storage.store, user_id, thread_id)
        if listed is None:
            raise ConversationError(f"No conversation {thread_id}.")
        if thread_id in self._active_runs:
            raise ConversationBusyError("A reply is still running in this conversation. Stop it first.")
        async with self._thread_lock(thread_id):
            messages = await self._thread_messages(thread_id)
            await self._storage.checkpointer.adelete_thread(thread_id)
            await self._storage.search.remove(thread_id)
            async with self._conversations_lock:
                await conversations.remove(self._storage.store, user_id, thread_id)
            await self._forget_channel_pointers(user_id, thread_id)
            await inbox.forget(self._storage.store, user_id, thread_id)
            await pinned.forget(self._storage.store, user_id, thread_id)
            await home_pins.forget(self._storage.store, user_id, thread_id)
            await summaries.forget(self._storage.store, user_id, thread_id)
            await file_index.forget(self._storage.store, user_id, thread_id)
            await handoffs.forget(self._storage.store, user_id, thread_id)
            await ended.forget(self._storage.store, user_id, thread_id)
            await moved.forget(self._storage.store, user_id, thread_id)
            await queued.forget(self._storage.store, user_id, thread_id)
            await notifications.forget_conversation(self._storage.store, user_id, thread_id)
            await chat_threads.forget(self._storage.store, user_id, listed.channels, thread_id)
        await asyncio.to_thread(_delete_files, referenced(messages), await self._files_elsewhere(user_id, thread_id))
        self.bus.publish("conversations")

    async def _forget_channel_pointers(self, user_id: str, thread_id: str) -> None:
        for item in await self._storage.store.asearch(inbox.channels_namespace(user_id), limit=100):
            if item.value.get("thread_id") == thread_id:
                await self._storage.store.adelete(inbox.channels_namespace(user_id), item.key)

    def leave_thread(self, user_id: str, thread_id: str) -> None:
        """Nobody is on the conversation any more: archive what's new in it, in the background."""
        self._archive_in_background(thread_id, user_id)

    async def last_reply(self, thread_id: str) -> str:
        """The text of the conversation's last assistant message."""
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        replies = [m for m in state.values.get("messages", []) if isinstance(m, AIMessage)]
        return choices.without_markers(replies[-1].text).strip() if replies else ""


def _delete_files(paths: list[Path], kept: list[Path]) -> None:
    """The conversation's files, but those in `kept`. Only files inside the uploads folder."""
    root = Path(settings.uploads_dir).expanduser().resolve()
    keep = {path.resolve() for path in kept}
    for path in paths:
        target = path.resolve()
        if target.is_relative_to(root) and target not in keep and target.is_file():
            target.unlink()
            _remove_empty(target.parent, root)


def _remove_empty(folder: Path, root: Path) -> None:
    """Each upload has a folder of its own; it goes with its file."""
    if folder != root and folder.is_relative_to(root) and not any(folder.iterdir()):
        folder.rmdir()
