from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import EmailAccount, EmailAccountNotFoundError, EmailError, EmailProvider

_PATH = "/integrations/email"
_ERRORS = {400: EmailError, 404: EmailAccountNotFoundError}


class EmailApi:
    """The daemon's email accounts (SMTP to send, IMAP to read): which is the default and where each
    one's new mail is announced; and who the agent may email without asking, from any account."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def providers(self) -> list[EmailProvider]:
        """Mail providers to pick from, so only the address and the password are typed."""
        return [EmailProvider(**p) for p in await self._transport.request("GET", f"{_PATH}/providers")]

    async def accounts(self) -> list[EmailAccount]:
        """The default first."""
        return [EmailAccount(**a) for a in await self._transport.request("GET", f"{_PATH}/accounts")]

    async def add(
        self,
        label: str,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        imap_host: str = "",
        imap_port: int = 993,
    ) -> EmailAccount:
        """Checks the logins first. Raises EmailError."""
        body = _settings(label, host, port, username, password, sender, imap_host, imap_port)
        return EmailAccount(**await self._transport.request("POST", f"{_PATH}/accounts", json=body, errors=_ERRORS))

    async def update(
        self,
        account_id: str,
        label: str,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        imap_host: str = "",
        imap_port: int = 993,
    ) -> EmailAccount:
        """An empty password keeps the saved one. Raises EmailError."""
        body = _settings(label, host, port, username, password, sender, imap_host, imap_port)
        return await self._put(account_id, "", body)

    async def rename(self, account_id: str, label: str) -> EmailAccount:
        """Only the name; the sign-in stays. Raises EmailError when another account has it."""
        return await self._put(account_id, "/label", {"label": label})

    async def make_default(self, account_id: str) -> EmailAccount:
        return await self._put(account_id, "/default", None)

    async def set_new_mail_alerts(self, account_id: str, channel: str) -> EmailAccount:
        return await self._put(account_id, "/alerts", {"channel": channel})

    async def recipients(self) -> list[str]:
        """Besides the user's own accounts, which always are."""
        return (await self._transport.request("GET", f"{_PATH}/recipients"))["addresses"]

    async def set_recipients(self, addresses: list[str]) -> list[str]:
        body = {"addresses": addresses}
        return (await self._transport.request("PUT", f"{_PATH}/recipients", json=body))["addresses"]

    async def remove(self, account_id: str) -> None:
        await self._transport.request("DELETE", f"{_PATH}/accounts/{account_id}", errors=_ERRORS)

    async def start_sign_in(
        self,
        provider: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        address: str,
        label: str = "",
        account_id: str = "",
    ) -> str:
        """The provider's sign-in page (OAuth: google, microsoft). The browser comes back to
        `redirect_uri`, the web app's /app/oauth, which finishes it (`client.oauth`). Raises EmailError."""
        body = {
            "provider": provider,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "address": address,
            "label": label,
            "account_id": account_id,
        }
        data = await self._transport.request("POST", f"{_PATH}/oauth/start", json=body, errors=_ERRORS)
        return data["url"]

    async def _put(self, account_id: str, path: str, body: dict | None) -> EmailAccount:
        url = f"{_PATH}/accounts/{account_id}{path}"
        return EmailAccount(**await self._transport.request("PUT", url, json=body, errors=_ERRORS))


def _settings(
    label: str, host: str, port: int, username: str, password: str, sender: str, imap_host: str, imap_port: int
) -> dict:
    return {
        "label": label,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "sender": sender,
        "imap_host": imap_host,
        "imap_port": imap_port,
    }
