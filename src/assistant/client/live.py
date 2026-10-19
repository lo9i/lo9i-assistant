"""The conversation a client shows: which conversation this client is on, which runs in it come
from elsewhere (another client, or a channel like Telegram), and which replies were left running
after moving to another conversation. Any client (terminal, web) can use it; how things are
shown stays in the client."""

from typing import Any, Protocol

from assistant.core.agent import Session


class Conversations(Protocol):
    """The DaemonClient calls LiveConversation needs."""

    async def inbox_thread(self, user_id: str) -> str: ...
    async def new_thread(self, user_id: str) -> str: ...
    async def resume_thread(self, user_id: str, thread_id: str) -> None: ...


class LiveConversation:
    def __init__(self, client: Conversations, session: Session, client_id: str) -> None:
        self._client = client
        self.session = session
        # How the daemon names this client in the runs it announces.
        self._client_id = client_id
        # Conversations left with a reply still running; the daemon finishes those replies.
        self._left_running: set[str] = set()

    async def start_new(self, *, leave_running: bool = False) -> None:
        """Move to a new conversation. With `leave_running`, the reply running in the current one
        keeps going in the daemon, and `left_run_finished` reports when it ends."""
        if leave_running:
            self._left_running.add(self.session.thread_id)
        self.session.thread_id = await self._client.new_thread(self.session.user_id)

    async def go_inbox(self, *, leave_running: bool = False) -> None:
        """Move to the inbox, like `start_new`."""
        if leave_running:
            self._left_running.add(self.session.thread_id)
        self.session.thread_id = await self._client.inbox_thread(self.session.user_id)

    async def resume(self, thread_id: str, *, leave_running: bool = False) -> None:
        """Move back to an earlier conversation, like `start_new`. Raises ConversationError."""
        await self._client.resume_thread(self.session.user_id, thread_id)
        if leave_running:
            self._left_running.add(self.session.thread_id)
        self.session.thread_id = thread_id

    def started_elsewhere(self, run: dict[str, Any]) -> bool:
        """A run (from a `run` event) in this conversation, started by anything but this client."""
        return run["thread_id"] == self.session.thread_id and run.get("client_id") != self._client_id

    def left_run_finished(self, run: dict[str, Any]) -> bool:
        """True, once, when a finished run (a `run_finished` event) is one left with `start_new`."""
        if run["thread_id"] not in self._left_running:
            return False
        self._left_running.discard(run["thread_id"])
        return True
