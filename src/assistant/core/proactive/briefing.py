"""The morning briefing: today's calendar, what's due, important mail, the open loops that matter now and the reviews'
suggestions, in one short message. Gathering reads the sources the user has (sources.py) with the worker model, then
one structured call writes the message and the reminders it found (a bill due, invoices to issue, a mail to answer),
which are kept as open loops. Nothing is gathered or written when the user has no source, no open loop and no
suggestion waiting: there's nothing to tell.

The message goes to the notifications feed, which the apps show, and to the user's own chat on every chat channel
connected (core/conversation/sent.py), where a reply to it arrives with it in its turn header. It never fails the
schedule: a failure is recorded on the briefing, which the apps show."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.store.base import BaseStore

from assistant.core import i18n
from assistant.core.context import UNATTENDED_CHANNEL, Context
from assistant.core.conversation import prompts
from assistant.core.proactive import clock, inputs, loops, records, sources
from assistant.core.proactive.failures import SECONDS, reason
from assistant.core.proactive.model import Briefing, BriefingDraft, ProactiveSettings, Review
from assistant.core.proactive.sources import ReadOnlyTools, Sources
from assistant.core.proactive.telling import Teller
from assistant.core.proactive.writing import ProactiveModels
from assistant.core.secret_store import SecretBox

logger = logging.getLogger(__name__)

_ASKS = {
    "calendar": "Calendar: today's events from every calendar, in order of time, and tomorrow's before 10:00.",
    "expenses": "Bills: those not paid that are overdue or due by {week} (month_summary has the unpaid ones), each "
    "with its amount and due day; recurring obligations due by then with no bill yet.",
    "billing": "Invoices: those of the last period that ended (prepare_month shows each one's status) not issued yet.",
    sources.MAIL: "Mail in {accounts}: unread messages since {mail_since} (search_email with unread_only and since). "
    "Say which come from a person and look important, and which ask the user something and are 2 days old or more.",
}


def _to_tell(review: Review) -> bool:
    """Its suggestions, and a weekly review's look back, go into the next briefing."""
    return bool(review.suggestions) or (review.kind == "weekly" and bool(review.summary))


class Briefer:
    def __init__(
        self,
        store: BaseStore,
        models: Callable[[], ProactiveModels],
        tools: ReadOnlyTools,
        secrets: SecretBox,
        teller: Teller,
        user_id: str,
    ) -> None:
        """`models` gives those of the model in use, which changes when the user picks another."""
        self._store = store
        self._models = models
        self._tools = tools
        self._secrets = secrets
        self._teller = teller
        self._user_id = user_id

    async def brief(self, now: datetime) -> Briefing:
        """Writes the briefing of the user's day and tells it. Never raises: a failure is recorded."""
        day, at = clock.day_of(now), datetime.now(UTC).isoformat()
        try:
            async with asyncio.timeout(SECONDS):
                draft = await self._draft(now)
        except Exception as e:
            logger.warning("Couldn't write the briefing: %s", e, exc_info=not isinstance(e, TimeoutError))
            error = (await i18n.chosen(self._store)).shown(reason(e))
            briefing = Briefing(day=day, at=at, status="failed", error=error)
        else:
            briefing = await self._told(day, at, draft)
        await records.save_briefing(self._store, self._user_id, briefing)
        return briefing

    async def _draft(self, now: datetime) -> BriefingDraft | None:
        """None when there's nothing to tell."""
        chosen = await records.load_settings(self._store, self._user_id)
        found = await sources.available(self._store, self._tools)
        waiting = [r for r in await records.reviews(self._store, self._user_id) if not r.briefed]
        open_now = [o for o in await loops.open_loops(self._store, self._user_id) if o.kind not in chosen.muted]
        if not found.tools and not open_now and not any(_to_tell(r) for r in waiting):
            return None
        gathered = await self._gathered(found, now)
        draft = BriefingDraft.model_validate(
            await self._models().briefing.ainvoke(
                [
                    SystemMessage(await self._system()),
                    HumanMessage(await self._input(now, gathered, chosen, loops.render(open_now), waiting)),
                ]
            )
        )
        for reminder in draft.reminders:
            await loops.add(self._store, self._user_id, reminder, "briefing")
        await records.mark_briefed(self._store, self._user_id, waiting)
        return draft

    async def _gathered(self, found: Sources, now: datetime) -> str:
        if not found.tools:
            return "(no plugin or mail account to read)"
        values = {"week": clock.days_from(now, 7), "mail_since": clock.days_from(now, -3)}
        task = f"Now: {clock.stamp(now)}.\nFind:\n{sources.asked(found, _ASKS, **values)}"
        context = Context(self._user_id, UNATTENDED_CHANNEL, secrets=self._secrets)
        return await self._models().gatherer.gather(context, prompts.load("proactive_gather"), task, found.tools)

    async def _system(self) -> str:
        return prompts.load("briefing").format(language=await inputs.language(self._store, self._user_id))

    async def _input(
        self, now: datetime, gathered: str, chosen: ProactiveSettings, open_loops: str, waiting: list[Review]
    ) -> str:
        weekly = [r.summary for r in waiting if r.kind == "weekly" and r.summary]
        suggestions = [f"[{s.kind}] {s.text}" for r in waiting for s in r.suggestions]
        parts = [
            f"Now: {clock.stamp(now)}.",
            f"# Found in the plugins and mail\n{gathered}",
            f"# Open loops\n{open_loops}",
            f"# Suggestions from the reviews\n{inputs.listed(suggestions)}",
            *([f"# Last week\n{inputs.listed(weekly)}"] if weekly else []),
            f"# Habits\n{inputs.listed(await inputs.habits(self._store, self._user_id))}",
            f"# Muted kinds\n{inputs.muted(chosen)}",
        ]
        return "\n\n".join(parts)

    async def _told(self, day: str, at: str, draft: BriefingDraft | None) -> Briefing:
        text = draft.text.strip() if draft else ""
        if not text:
            return Briefing(day=day, at=at, status="nothing")
        t = await i18n.chosen(self._store)
        channels = await self._teller.tell("briefing", t("Morning briefing"), text)
        return Briefing(day=day, at=at, status="sent", text=text, channels=channels)
