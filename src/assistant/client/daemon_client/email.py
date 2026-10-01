from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import EmailError, EmailProvider, EmailStatus

_PATH = "/integrations/email"


class EmailApi:
    """The daemon's email (SMTP) account, and who the agent may email without asking."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def providers(self) -> list[EmailProvider]:
        """Mail providers to pick from, so only the address and the password are typed."""
        return [EmailProvider(**p) for p in await self._transport.request("GET", f"{_PATH}/providers")]

    async def status(self) -> EmailStatus:
        return EmailStatus(**await self._transport.request("GET", _PATH))

    async def connect(self, host: str, port: int, username: str, password: str, sender: str) -> EmailStatus:
        body = {"host": host, "port": port, "username": username, "password": password, "sender": sender}
        return EmailStatus(**await self._transport.request("POST", _PATH, json=body, errors={400: EmailError}))

    async def set_recipients(self, addresses: list[str]) -> EmailStatus:
        data = await self._transport.request("PUT", f"{_PATH}/recipients", json={"addresses": addresses})
        return EmailStatus(**data)

    async def disconnect(self) -> None:
        await self._transport.request("DELETE", _PATH)
