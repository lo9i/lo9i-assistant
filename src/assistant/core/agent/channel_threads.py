"""Conversations for chat channels (Telegram, Slack), which have no client to hold one: a new message goes
to the inbox, which routes it; a reply to a message goes on in that message's conversation; /new sends the
next message to a new conversation (core/channels/chat/threads.py). Each reply is tagged with a short name
of its conversation, so the user sees where it went."""

from assistant.core import conversations
from assistant.core.agent.threads import ThreadsMixin
from assistant.core.channels.chat import threads
from assistant.core.conversations import Conversation

# A tag's longest: a conversation's first tag, or the start of its title.
_TAG_WORDS = 3
_TAG_CHARS = 30


class ChannelThreadsMixin(ThreadsMixin):
    async def chat_message_thread(self, user_id: str, channel: str, chat: str, message: str) -> str | None:
        """The conversation a message in the chat belongs to; None for one not kept."""
        return await threads.thread_of(self._storage.store, user_id, channel, chat, message)

    async def chat_messages_in(
        self, user_id: str, channel: str, chat: str, messages: list[str], thread_id: str
    ) -> None:
        """The chat's `messages` belong to `thread_id`: replying to one goes on there."""
        await threads.record(self._storage.store, user_id, channel, chat, messages, thread_id)

    async def channel_wants_new(self, user_id: str, channel: str) -> None:
        """The channel's /new: its next message starts a new conversation."""
        await threads.want_new(self._storage.store, user_id, channel)

    async def channel_takes_new(self, user_id: str, channel: str) -> bool:
        """Whether the channel's /new waits for this message; it no longer does."""
        return await threads.take_new(self._storage.store, user_id, channel)

    async def chat_tag(self, user_id: str, thread_id: str, text: str = "") -> str:
        """A short name for the conversation, shown with the replies in a chat: "inbox", its first tag, or
        the start of its title; for one that isn't saved yet, the start of `text`, its first message."""
        if thread_id == await self.inbox_thread(user_id):
            return "inbox"
        conversation = await conversations.load(self._storage.store, user_id, thread_id)
        return _short(_name(conversation) if conversation else text)


def _name(conversation: Conversation) -> str:
    return conversation.tags[0] if conversation.tags else conversation.title


def _short(name: str) -> str:
    words = " ".join(name.split()[:_TAG_WORDS])
    return words if len(words) <= _TAG_CHARS else words[: _TAG_CHARS - 1] + "…"
