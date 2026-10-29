import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

from assistant.client.daemon_client.chat import ChatBase
from assistant.client.daemon_client.reconnect import ReconnectPolicy, resumable_events
from assistant.core.agent import Session
from assistant.core.attachments import Attachment
from assistant.core.events import Event
from assistant.protocol import END, event_from_dict

# A run is short-lived; if the daemon stays away this long, the reply is reported as lost.
_RECONNECT = ReconnectPolicy(delay_seconds=1, attempts=5)


class RunsMixin(ChatBase):
    """Starting runs and following their events. Runs keep going in the daemon if we disconnect."""

    async def send(self, session: Session, text: str, attachments: Sequence[Attachment] = ()) -> AsyncIterator[Event]:
        files = [("files", (a.name, a.data, a.media_type)) for a in attachments]
        data = {"channel": session.channel, "text": text}
        run = await self._transport.request(
            "POST", f"/threads/{session.thread_id}/messages", data=data, files=files or None
        )
        async for event in self._follow(run["run_id"]):
            yield event

    async def send_dispatched(
        self, session: Session, dispatch_id: str, text: str, brief: str = ""
    ) -> AsyncIterator[Event]:
        """Sends a message the inbox sent on (a Dispatched event) in `session`'s conversation, as it was
        written. Its text, and for a coding task its agent (`brief`), are announced with the run."""
        body = {"channel": session.channel, "text": text, "brief": brief}
        run = await self._transport.request("POST", f"/threads/{session.thread_id}/dispatched/{dispatch_id}", json=body)
        async for event in self._follow(run["run_id"]):
            yield event

    async def move_dispatched(self, session: Session, dispatch_id: str = "") -> AsyncIterator[Event]:
        """Asks in the inbox (`session`) where a message it sent on goes instead, the last one when `dispatch_id`
        is empty; a Dispatched event says where it went."""
        body = {"channel": session.channel, "id": dispatch_id}
        run = await self._transport.request("POST", f"/threads/{session.thread_id}/moves", json=body)
        async for event in self._follow(run["run_id"]):
            yield event

    async def resume(self, session: Session, decisions: dict[str, dict[str, Any]]) -> AsyncIterator[Event]:
        body = {"channel": session.channel, "decisions": decisions}
        run = await self._transport.request("POST", f"/threads/{session.thread_id}/approvals", json=body)
        async for event in self._follow(run["run_id"]):
            yield event

    async def cancel(self, session: Session) -> bool:
        """Stop the conversation's run in progress, whichever channel started it. Its events end
        with Cancelled. Returns whether a run was in progress."""
        return (await self._transport.request("POST", f"/threads/{session.thread_id}/cancel"))["cancelled"]

    async def runs_in_progress(self) -> list[dict[str, Any]]:
        """The replies in progress in any conversation, oldest first, as the `run` events announce them."""
        return await self._transport.request("GET", "/runs")

    def follow_run(self, run_id: str) -> AsyncIterator[Event]:
        """A run started elsewhere (another channel), from its first event."""
        return self._follow(run_id)

    async def _follow(self, run_id: str) -> AsyncIterator[Event]:
        """Stream a run's events, reconnecting from the last event id if the connection drops."""
        async for kind, data in resumable_events(self._transport, f"/runs/{run_id}/events", _RECONNECT):
            if kind == END:
                return
            yield event_from_dict(json.loads(data))
