"""The conversation a client shows, kept in step with the daemon: which conversation is active,
which runs come from other channels, and which replies were left running after starting a new
conversation. Any client (terminal, web) can use it; how things are shown stays in the client."""

from typing import Any, Protocol

from assistant.core.agent import Session


class Conversations(Protocol):
    """The DaemonClient calls LiveConversation needs."""

    async def new_thread(self, user_id: str) -> str: ...
    async def session(self, user_id: str, channel: str) -> Session: ...


class LiveConversation:
    def __init__(self, client: Conversations, session: Session) -> None:
        self._client = client
        self.session = session
        # Conversations left with a reply still running; the daemon finishes those replies.
        self._left_running: set[str] = set()

    async def start_new(self, *, leave_running: bool = False) -> None:
        """Switch to a new conversation. With `leave_running`, the reply running in the current one
        keeps going in the daemon, and `left_run_finished` reports when it ends."""
        if leave_running:
            self._left_running.add(self.session.thread_id)
        self.session.thread_id = await self._client.new_thread(self.session.user_id)

    async def follow(self) -> bool:
        """Switch to the conversation the daemon has active for this channel. True when it changed,
        which happens when another channel starts a new conversation."""
        active = await self._client.session(self.session.user_id, self.session.channel)
        if active.thread_id == self.session.thread_id:
            return False
        self.session.thread_id = active.thread_id
        return True

    def started_elsewhere(self, run: dict[str, Any]) -> bool:
        """A run (from a `run` event) in this conversation, started from another channel."""
        return run["thread_id"] == self.session.thread_id and run["channel"] != self.session.channel

    def left_run_finished(self, run: dict[str, Any]) -> bool:
        """True, once, when a finished run (a `run_finished` event) is one left with `start_new`."""
        if run["thread_id"] not in self._left_running:
            return False
        self._left_running.discard(run["thread_id"])
        return True
