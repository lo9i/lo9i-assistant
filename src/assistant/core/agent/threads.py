import asyncio
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage

from assistant.core import conversations, home, uploads
from assistant.core.agent.archive import ArchiveMixin
from assistant.core.agent.session import Session
from assistant.core.attachments import upload_paths
from assistant.core.config import settings
from assistant.core.conversation import handoffs, pinned
from assistant.core.speech.voice import audio_paths


class ConversationError(Exception):
    pass


class ConversationBusyError(ConversationError):
    """A reply is running in the conversation."""


class ThreadsMixin(ArchiveMixin):
    """Conversations. A client (terminal, web page) holds its own and says when it leaves one; a
    channel without a client (Telegram) is on home (core/home.py) unless it started a side
    conversation with /new, which it keeps here until its /home."""

    async def session(self, user_id: str, channel: str) -> Session:
        """The channel's current conversation: its side conversation, or home."""
        thread_id = await home.channel_thread(self._storage.store, user_id, channel)
        thread_id = thread_id or await self.home_thread(user_id)
        return Session(user_id=user_id, channel=channel, thread_id=thread_id)

    async def home_thread(self, user_id: str) -> str:
        """The home conversation's id, started on first use."""
        store = self._storage.store
        if (thread_id := await home.current(store, user_id)) is None:
            thread_id = await self.new_thread(user_id)
            await home.start(store, user_id, thread_id)
        return thread_id

    async def channels_to_home(self, user_id: str) -> int:
        """Moves channels still on a conversation from before home existed to home, once: without a
        home, every channel's saved conversation predates it (a /new now starts home first). Those
        conversations are archived in the background. Returns how many channels moved."""
        store = self._storage.store
        if await home.current(store, user_id) is not None:
            return 0
        saved = await store.asearch(home.channels_namespace(user_id), limit=100)
        for item in saved:
            await store.adelete(home.channels_namespace(user_id), item.key)
            self.leave_thread(user_id, item.value["thread_id"])
        return len(saved)

    async def channel_home(self, user_id: str, channel: str) -> str:
        """Moves the channel back to home (its /home) and returns home's id. The side conversation
        it leaves is archived in the background."""
        previous = await self._storage.store.aget(home.channels_namespace(user_id), channel)
        if previous is not None:
            await self._storage.store.adelete(home.channels_namespace(user_id), channel)
            self.leave_thread(user_id, previous.value["thread_id"])
        return await self.home_thread(user_id)

    async def new_thread(self, user_id: str) -> str:
        """A new conversation's id. It's saved, and listed, once it has a message."""
        return f"{user_id}:{uuid4().hex[:12]}"

    async def new_channel_thread(self, user_id: str, channel: str) -> str:
        """Start a side conversation for the channel (its /new). What's new in the conversation it
        leaves, home or another side one, is archived in the background."""
        left = (await self.session(user_id, channel)).thread_id
        thread_id = await self.new_thread(user_id)
        await self._storage.store.aput(home.channels_namespace(user_id), channel, {"thread_id": thread_id})
        self.leave_thread(user_id, left)
        return thread_id

    async def require_conversation(self, user_id: str, thread_id: str) -> None:
        """Raises ConversationError unless the conversation exists, before a client resumes it."""
        if await conversations.load(self._storage.store, user_id, thread_id) is None:
            raise ConversationError(f"No conversation {thread_id}.")

    async def delete_conversation(self, user_id: str, thread_id: str) -> None:
        """Delete the conversation: its messages, its place in the list and in search, and the files
        and voice recordings sent in it. What memory learned from it stays. A channel on it (Telegram) starts
        a new one with its next message. Raises ConversationError for an unknown one,
        ConversationBusyError while a reply is running."""
        await self.require_conversation(user_id, thread_id)
        if thread_id in self._active_runs:
            raise ConversationBusyError("A reply is still running in this conversation. Stop it first.")
        async with self._thread_lock(thread_id):
            state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
            await self._storage.checkpointer.adelete_thread(thread_id)
            await self._storage.search.remove(thread_id)
            async with self._conversations_lock:
                await conversations.remove(self._storage.store, user_id, thread_id)
            await self._forget_channel_pointers(user_id, thread_id)
            await home.forget(self._storage.store, user_id, thread_id)
            await pinned.forget(self._storage.store, user_id, thread_id)
            await handoffs.forget(self._storage.store, user_id, thread_id)
        await asyncio.to_thread(_delete_files, state.values.get("messages", []))
        self.bus.publish("conversations")

    async def _forget_channel_pointers(self, user_id: str, thread_id: str) -> None:
        for item in await self._storage.store.asearch(home.channels_namespace(user_id), limit=100):
            if item.value.get("thread_id") == thread_id:
                await self._storage.store.adelete(home.channels_namespace(user_id), item.key)

    def leave_thread(self, user_id: str, thread_id: str) -> None:
        """Nobody is on the conversation any more: archive what's new in it, in the background."""
        self._archive_in_background(thread_id, user_id)

    async def last_reply(self, thread_id: str) -> str:
        """The text of the conversation's last assistant message."""
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        replies = [m for m in state.values.get("messages", []) if isinstance(m, AIMessage)]
        return replies[-1].text.strip() if replies else ""


def _delete_files(messages: list[BaseMessage]) -> None:
    """The conversation's uploads and voice recordings. Only files inside the uploads folder."""
    root = Path(settings.uploads_dir).expanduser().resolve()
    for path in [uploads.absolute(p) for p in upload_paths(messages)] + audio_paths(messages):
        target = path.resolve()
        if target.is_relative_to(root) and target.is_file():
            target.unlink()
            _remove_empty(target.parent, root)


def _remove_empty(folder: Path, root: Path) -> None:
    """Each upload has a folder of its own; it goes with its file."""
    if folder != root and folder.is_relative_to(root) and not any(folder.iterdir()):
        folder.rmdir()
