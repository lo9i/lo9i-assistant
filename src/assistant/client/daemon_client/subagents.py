from typing import Any

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import BackgroundStep, BackgroundSubagent, SubagentDetails, SubagentError
from assistant.core.background_subagents.records import from_value


class SubagentsApi:
    """Subagents sent off in the background: a conversation's or every one, the newest first. `subagents` and
    `subagent_step` events say when they change."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self, thread_id: str = "") -> list[BackgroundSubagent]:
        listed = await self._transport.request("GET", "/subagents", params={"thread_id": thread_id})
        return [from_value(s) for s in listed]

    async def get(self, subagent_id: str) -> SubagentDetails:
        """Raises SubagentError for one that went."""
        found = await self._transport.request("GET", f"/subagents/{subagent_id}", errors={404: SubagentError})
        return SubagentDetails(from_value(found["subagent"]), [BackgroundStep(**s) for s in found["steps"]])

    async def answer(self, subagent_id: str, interrupt_id: str, decision: dict[str, Any]) -> bool:
        """False when it doesn't wait for that any more."""
        body = {"interrupt_id": interrupt_id, "decision": decision}
        answered = await self._transport.request(
            "POST", f"/subagents/{subagent_id}/answers", json=body, errors={404: SubagentError}
        )
        return bool(answered["answered"])

    async def stop(self, subagent_id: str) -> None:
        """Raises SubagentError when it isn't working."""
        errors = {404: SubagentError, 409: SubagentError}
        await self._transport.request("POST", f"/subagents/{subagent_id}/stop", errors=errors)

    async def remove(self, subagent_id: str) -> None:
        """Raises SubagentError while it's still working."""
        errors = {404: SubagentError, 409: SubagentError}
        await self._transport.request("DELETE", f"/subagents/{subagent_id}", errors=errors)
