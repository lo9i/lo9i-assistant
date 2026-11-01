"""Telling a spending limit nearly reached (budget.py): in the notifications feed, which keeps it for the apps (opening
the conversation, for a conversation's limit), and in the user's own chat on every chat channel connected then, as the
Copilot allowance's alerts are told. Written in the language the user chose."""

from datetime import UTC, datetime

from langgraph.store.base import BaseStore

from assistant.core import conversations, i18n, notifications
from assistant.core.conversation import sent
from assistant.core.i18n import Texts
from assistant.core.outbox import Outbox
from assistant.core.usage.budget import Spending, dollars


class SpendingAlerts:
    def __init__(self, store: BaseStore, outbox: Outbox, user_id: str) -> None:
        self._store = store
        self._outbox = outbox
        self._user_id = user_id

    async def __call__(self, spending: Spending) -> None:
        t = await i18n.chosen(self._store)
        text = await self._text(t, spending)
        thread_id = spending.thread_id if spending.kind == "conversation" else ""
        await notifications.add(self._store, self._user_id, "spending", t("Spending limit"), text, False, thread_id)
        await sent.tell_every_channel(self._store, self._outbox, self._user_id, text, datetime.now(UTC))

    async def _text(self, t: Texts, spending: Spending) -> str:
        values = {"spent": dollars(spending.spent), "limit": dollars(spending.limit), "job": spending.job}
        if spending.kind == "job_run":
            nearly = t("A run of the job {job} has spent {spent} of its {limit} limit per run.", **values)
        elif spending.kind == "job_day":
            nearly = t("The job {job} has spent {spent} today of its {limit} daily limit.", **values)
        elif spending.kind == "conversation":
            title = await self._title(t, spending.thread_id)
            nearly = t("The conversation “{title}” has spent {spent} of its {limit} limit.", title=title, **values)
        else:
            nearly = t("The assistant has spent {spent} today of the {limit} daily limit.", **values)
        return nearly + " " + t("At the limit it stops; Settings → Model (/limits in the terminal app) changes it.")

    async def _title(self, t: Texts, thread_id: str) -> str:
        listed = await conversations.load(self._store, self._user_id, thread_id)
        return listed.title if listed and listed.title else t("Untitled")
