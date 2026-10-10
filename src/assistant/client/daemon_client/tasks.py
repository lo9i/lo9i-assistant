from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import RunningTask


class TasksApi:
    """Coding agents' tasks running in the background."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def running(self) -> list[RunningTask]:
        return [RunningTask(**t) for t in await self._transport.request("GET", "/agent-tasks/running")]
