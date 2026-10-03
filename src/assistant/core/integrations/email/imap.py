"""Reading mail over IMAP with the /email settings: searching, reading one message, and waiting for
new ones (IDLE). Messages are read with BODY.PEEK, so reading never marks them as read.

TLS on port 993. Plain IMAP only to this machine, for local bridges (Proton Mail Bridge).
"""

import asyncio
import contextlib
import email
import mimetypes
import re
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import default
from email.utils import parsedate_to_datetime

import certifi
from aioimaplib import IMAP4, IMAP4_SSL, AioImapException, Response

from assistant.core.integrations.email.accounts import EmailConfig, EmailError
from assistant.core.internet.fetch import html_to_markdown

_TIMEOUT = 20
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_UID_VALIDITY = re.compile(rb"UIDVALIDITY (\d+)")
_ATOM = re.compile(r"^[A-Za-z0-9_./-]+$")
_FETCH_META = re.compile(rb"UID (\d+)")
_FLAGS = re.compile(rb"FLAGS \(([^)]*)\)")
_HEADERS = "BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE)]"


@dataclass
class MailSummary:
    uid: int
    sender: str
    subject: str
    date: str
    unread: bool


@dataclass
class MailAttachment:
    name: str
    media_type: str
    data: bytes


@dataclass
class Mail:
    summary: MailSummary
    to: str
    cc: str
    body: str
    attachments: list[MailAttachment]


class Mailbox:
    """One selected folder of an open IMAP connection."""

    def __init__(self, client: IMAP4, uid_validity: str = "") -> None:
        self._client = client
        # Changes when the server renumbers the folder; UIDs from before mean nothing then.
        self.uid_validity = uid_validity

    async def search(self, criteria: list[str], limit: int) -> list[MailSummary]:
        """The newest `limit` messages matching IMAP search criteria, newest first."""
        uids = await self._search(criteria or ["ALL"])
        return list(reversed(await self.summaries(uids[-limit:])))

    async def read(self, uid: int) -> Mail | None:
        response = await self._fetch(str(uid), "(UID FLAGS BODY.PEEK[])")
        parts = parse_fetch(response.lines)
        return _mail(*parts[0]) if parts else None

    async def last_uid(self) -> int:
        uids = await self._search(["ALL"])
        return uids[-1] if uids else 0

    async def uids_after(self, uid: int) -> list[int]:
        # "N:*" always matches the newest message, even when its UID is below N.
        return [u for u in await self._search(["UID", f"{uid + 1}:*"]) if u > uid]

    async def wait_for_new(self, timeout: float) -> None:
        """Returns when the server reports a change (new mail), or after `timeout` seconds."""
        idle = await self._client.idle_start(timeout=timeout)
        try:
            await self._client.wait_server_push(timeout=timeout + _TIMEOUT)
        except TimeoutError:
            pass
        finally:
            self._client.idle_done()
            await asyncio.wait_for(idle, _TIMEOUT)

    async def summaries(self, uids: list[int]) -> list[MailSummary]:
        """Sender, subject, date and unread for these messages, oldest first."""
        if not uids:
            return []
        response = await self._fetch(",".join(map(str, uids)), f"(UID FLAGS {_HEADERS})")
        summaries = [_summary(meta, raw) for meta, raw in parse_fetch(response.lines)]
        return sorted(summaries, key=lambda s: s.uid)

    async def _search(self, criteria: list[str]) -> list[int]:
        response = await self._client.uid_search(*criteria)
        _check(response, "search")
        return sorted(int(u) for line in response.lines[:-1] if _is_search_result(line) for u in line.split())

    async def _fetch(self, uids: str, parts: str) -> Response:
        response = await self._client.uid("fetch", uids, parts)
        _check(response, "fetch")
        return response


@asynccontextmanager
async def open_mailbox(config: EmailConfig, folder: str = "INBOX") -> AsyncIterator[Mailbox]:
    """Log in and select `folder`. Raises EmailError."""
    client = _client(config)
    try:
        # The connection is opened in a task of the client's; awaiting it first reports a refused
        # connection at once, instead of as a timeout waiting for the server's greeting.
        await asyncio.wait_for(client._client_task, _TIMEOUT)
        await client.wait_hello_from_server()
        _check(await client.login(config.username, config.password), "log in")
        selected = await client.select(_mailbox_name(folder))
        _check(selected, f"open {folder}")
    except (AioImapException, OSError, TimeoutError) as e:
        raise EmailError(f"Couldn't read mail on {config.imap_host}:{config.imap_port}: {e}") from e
    try:
        yield Mailbox(client, _uid_validity(selected))
    except (AioImapException, OSError) as e:
        raise EmailError(f"Reading mail failed: {e}") from e
    finally:
        await _logout(client)


async def verify(config: EmailConfig) -> None:
    """Log in and open the inbox. Raises EmailError with the server's reason."""
    async with open_mailbox(config):
        pass


def quote(text: str) -> str:
    """An IMAP quoted string."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _uid_validity(selected: Response) -> str:
    found = (_UID_VALIDITY.search(bytes(line)) for line in selected.lines)
    return next((m.group(1).decode() for m in found if m), "")


def _is_search_result(line: bytes) -> bool:
    """The SEARCH line holds only UIDs. Others (`3 EXISTS`) are the server reporting changes."""
    return all(token.isdigit() for token in line.split())


def _mailbox_name(folder: str) -> str:
    """Folder names with spaces or special characters go quoted; plain ones (INBOX) as they are."""
    return folder if _ATOM.match(folder) else quote(folder)


def parse_fetch(lines: list) -> list[tuple[bytes, bytes]]:
    """(metadata, literal) for each message in a FETCH response. Servers put UID and FLAGS before
    or after the literal, so the metadata joins the lines around it."""
    found: list[tuple[bytes, bytes]] = []
    for i, line in enumerate(lines):
        if isinstance(line, bytearray) and i > 0:
            after = lines[i + 1] if i + 1 < len(lines) and not isinstance(lines[i + 1], bytearray) else b""
            found.append((bytes(lines[i - 1]) + b" " + bytes(after), bytes(line)))
    return found


def _client(config: EmailConfig) -> IMAP4:
    if config.imap_port == 993:
        context = ssl.create_default_context(cafile=certifi.where())
        return IMAP4_SSL(config.imap_host, config.imap_port, timeout=_TIMEOUT, ssl_context=context)
    if config.imap_host in _LOCAL_HOSTS:
        return IMAP4(config.imap_host, config.imap_port, timeout=_TIMEOUT)
    raise EmailError("Reading mail needs IMAP over TLS on port 993 (plain IMAP only to this computer).")


async def _logout(client: IMAP4) -> None:
    with contextlib.suppress(AioImapException, OSError, TimeoutError):
        await client.logout()


def _check(response: Response, action: str) -> None:
    if response.result != "OK":
        detail = response.lines[-1].decode(errors="replace") if response.lines else response.result
        raise EmailError(f"The mail server couldn't {action}: {detail}")


def _summary(meta: bytes, raw: bytes) -> MailSummary:
    headers = email.message_from_bytes(raw, policy=default)
    uid = _FETCH_META.search(meta)
    flags = _FLAGS.search(meta)
    return MailSummary(
        uid=int(uid.group(1)) if uid else 0,
        sender=str(headers.get("From", "")),
        subject=str(headers.get("Subject", "")),
        date=_date(str(headers.get("Date", ""))),
        unread=flags is not None and b"\\Seen" not in flags.group(1),
    )


def _mail(meta: bytes, raw: bytes) -> Mail:
    message = email.message_from_bytes(raw, policy=default)
    if not isinstance(message, EmailMessage):
        raise EmailError("The mail server sent a message that couldn't be read.")
    attachments = [_attachment(part) for part in message.iter_attachments()]
    to, cc = str(message.get("To", "")), str(message.get("Cc", ""))
    return Mail(_summary(meta, raw), to, cc, _body(message), attachments)


def _attachment(part: EmailMessage) -> MailAttachment:
    name = part.get_filename() or "unnamed"
    media_type = part.get_content_type()
    # Mailers often send any file as application/octet-stream; its name says more.
    if media_type == "application/octet-stream":
        media_type = mimetypes.guess_type(name)[0] or media_type
    payload = part.get_payload(decode=True)
    return MailAttachment(name, media_type, payload if isinstance(payload, bytes) else b"")


def _body(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain", "html"))
    if not isinstance(part, EmailMessage):
        return ""
    text = part.get_content()
    return html_to_markdown(text, "") if part.get_content_subtype() == "html" else text


def _date(value: str) -> str:
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return value
