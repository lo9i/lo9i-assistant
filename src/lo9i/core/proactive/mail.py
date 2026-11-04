"""The user's unread mail, read straight from their accounts (core/integrations/email/), for the briefing and the
nightly review: no model picks the search. An account that can't be read is skipped, and logged."""

import logging
from dataclasses import dataclass
from datetime import date

from langgraph.store.base import BaseStore

from lo9i.core.hidden_text import strip_hidden
from lo9i.core.integrations.email import accounts, imap
from lo9i.core.integrations.email.accounts import EmailError
from lo9i.core.secret_store import SecretBox

logger = logging.getLogger(__name__)

# Per account, the newest.
MAX_PER_ACCOUNT = 20


@dataclass(frozen=True)
class Unread:
    account: str
    uid: int
    sender: str
    subject: str
    # ISO 8601 when the message says, else as it says.
    date: str


class UnreadMail:
    def __init__(self, store: BaseStore, secrets: SecretBox) -> None:
        self._store = store
        self._secrets = secrets

    async def since(self, day: date) -> list[Unread]:
        """Unread messages received since `day`, in every account that can be read."""
        found: list[Unread] = []
        for config in await accounts.list_accounts(self._store):
            if config.can_read:
                found += await self._of(config.account_id, config.label, day)
        return found

    async def _of(self, account_id: str, label: str, day: date) -> list[Unread]:
        criteria = ["SINCE", day.strftime("%d-%b-%Y"), "UNSEEN"]
        try:
            config = await accounts.load(self._store, self._secrets, account_id)
            async with imap.open_mailbox(config) as mailbox:
                found = await mailbox.search(criteria, MAX_PER_ACCOUNT)
        except EmailError as e:
            logger.info("Couldn't read the unread mail of %s: %s", label, e)
            return []
        return [Unread(label, m.uid, strip_hidden(m.sender), strip_hidden(m.subject), m.date) for m in found]


def render(mail: list[Unread]) -> str:
    """For a model: written by the senders, which it's told."""
    return "\n".join(f"- [{m.account} {m.uid}] {m.date[:16]} · {m.sender} · {m.subject}" for m in mail) or "(none)"
