"""The morning briefing: each plugin's list for the day (core/mcp/today.py: today's events, bills coming due, invoices
to issue), the unread mail that matters, the open loops that matter now and the reviews' suggestions, laid out by code
(laid_out.py) in the language the apps show. What a plugin says needs doing is kept as an open loop. The one model call
picks the unread mail worth the user's attention, made only when there's unread mail and the user didn't mute it.
Nothing is sent when there's nothing to tell.

The message goes to the notifications feed, which the apps show, and to the user's own chat on every chat channel
connected (core/conversation/sent.py), where a reply to it arrives with it in its turn header. It never fails the
schedule: a failure is recorded on the briefing, which the apps show."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.store.base import BaseStore

from assistant.core import i18n
from assistant.core.conversation import prompts
from assistant.core.i18n import Texts
from assistant.core.mcp.today import Listed, TodayItem, TodayLists
from assistant.core.proactive import clock, inputs, loops, records
from assistant.core.proactive.failures import SECONDS, reason
from assistant.core.proactive.laid_out import Part, compose, item_line, loop_line
from assistant.core.proactive.mail import Unread, UnreadMail, render
from assistant.core.proactive.model import Briefing, LoopDraft, MailDraft, MailPick, ProactiveSettings
from assistant.core.proactive.telling import Teller
from assistant.core.proactive.writing import ProactiveModels

logger = logging.getLogger(__name__)

IMPORTANT_MAIL = "important mail"
UNANSWERED_MAIL = "unanswered mail"
# Unread mail the briefing looks at, and how old one asking something is before it's an open loop.
MAIL_DAYS = 3
ANSWER_DAYS = 2
# Open loops it lists at most: those due first, then the oldest.
LOOPS_SHOWN = 5
_PICKS = 5


class Briefer:
    def __init__(
        self,
        store: BaseStore,
        models: Callable[[], ProactiveModels],
        lists: TodayLists,
        mail: UnreadMail,
        teller: Teller,
        user_id: str,
    ) -> None:
        """`models` gives those of the model in use, which changes when the user picks another."""
        self._store = store
        self._models = models
        self._lists = lists
        self._mail = mail
        self._teller = teller
        self._user_id = user_id

    async def brief(self, now: datetime) -> Briefing:
        """Writes the briefing of the user's day and tells it. Never raises: a failure is recorded."""
        day, at = clock.day_of(now), datetime.now(UTC).isoformat()
        try:
            async with asyncio.timeout(SECONDS):
                text = await self._text(now)
        except Exception as e:
            logger.warning("Couldn't write the briefing: %s", e, exc_info=not isinstance(e, TimeoutError))
            error = (await i18n.chosen(self._store)).shown(reason(e))
            briefing = Briefing(day=day, at=at, status="failed", error=error)
        else:
            briefing = await self._told(day, at, text)
        await records.save_briefing(self._store, self._user_id, briefing)
        return briefing

    async def _text(self, now: datetime) -> str:
        chosen, t = await records.load_settings(self._store, self._user_id), await i18n.chosen(self._store)
        today = clock.local(now).date()
        listed = await self._lists.every(today.isoformat(), t.language)
        items = [i for found in listed if found.today for i in found.today.items if i.kind not in chosen.muted]
        for found in listed:
            await self._follow(found, chosen)
        mail = await self._mail_picks(now, chosen)
        waiting = [r for r in await records.reviews(self._store, self._user_id) if not r.briefed]
        parts = [
            *_plugin_parts(t, listed, chosen, today),
            Part(t("Mail"), [p.line for p in mail]),
            Part(t("Open loops"), await self._loop_lines(t, chosen, {*map(_key_of, items), *map(_mail_key, mail)})),
            Part(t("Suggestions"), [s.text for r in waiting for s in r.suggestions]),
            Part(t("Last week"), [r.summary for r in waiting if r.kind == "weekly" and r.summary]),
            Part(t("Couldn't read"), [f"{found.plugin}: {found.error}" for found in listed if found.error]),
        ]
        await records.mark_briefed(self._store, self._user_id, waiting)
        return compose(parts)

    async def _follow(self, found: Listed, chosen: ProactiveSettings) -> None:
        """What the plugin says needs doing is kept as an open loop, once; one it kept that its list no longer has (the
        bill was paid) is done. Nothing changes for a list that couldn't be read."""
        if found.today is None:
            return
        needs = [i for i in found.today.items if i.needs and i.kind not in chosen.muted]
        for item in needs:
            draft = LoopDraft(text=item.needs, kind=item.kind, key=_key_of(item), due=item.date)
            await loops.add(self._store, self._user_id, draft, "briefing", plugin=found.plugin)
        listed = {_key_of(i) for i in found.today.items}
        for gone in await loops.open_loops(self._store, self._user_id):
            if gone.plugin == found.plugin and gone.key not in listed:
                await loops.close(self._store, self._user_id, gone.id, "done")

    async def _loop_lines(self, t: Texts, chosen: ProactiveSettings, listed_keys: set[str]) -> list[str]:
        """The open loops not of a muted kind and not already in a plugin's list: due first, then the oldest."""
        found = [
            o
            for o in await loops.open_loops(self._store, self._user_id)
            if o.kind not in chosen.muted and o.key not in listed_keys
        ]
        found.sort(key=lambda o: (o.due or "9999", o.created_at))
        return [loop_line(t, o) for o in found[:LOOPS_SHOWN]]

    async def _mail_picks(self, now: datetime, chosen: ProactiveSettings) -> list[MailPick]:
        if IMPORTANT_MAIL in chosen.muted:
            return []
        unread = await self._mail.since(clock.local(now).date() - timedelta(days=MAIL_DAYS))
        if not unread:
            return []
        picks = await self._picked(now, unread)
        if UNANSWERED_MAIL not in chosen.muted:
            await self._keep_unanswered(now, unread, picks)
        return picks

    async def _picked(self, now: datetime, unread: list[Unread]) -> list[MailPick]:
        """The model's picks among the unread mail, only those it was given."""
        system = prompts.load("briefing_mail").format(language=await inputs.language(self._store, self._user_id))
        message = HumanMessage(f"Now: {clock.stamp(now)}.\n\n# Unread mail\n{render(unread)}")
        draft = MailDraft.model_validate(await self._models().mail.ainvoke([SystemMessage(system), message]))
        given = {(m.account, m.uid) for m in unread}
        return [p for p in draft.important if (p.account, p.uid) in given][:_PICKS]

    async def _keep_unanswered(self, now: datetime, unread: list[Unread], picks: list[MailPick]) -> None:
        """Mail asking the user something, unread for ANSWER_DAYS or more, is kept as an open loop."""
        received = {(m.account, m.uid): m.date for m in unread}
        before = clock.local(now).date() - timedelta(days=ANSWER_DAYS)
        for pick in (p for p in picks if p.asks and _day(received[(p.account, p.uid)]) <= before):
            draft = LoopDraft(text=pick.line, kind=UNANSWERED_MAIL, key=_mail_key(pick))
            await loops.add(self._store, self._user_id, draft, "briefing")

    async def _told(self, day: str, at: str, text: str) -> Briefing:
        if not text:
            return Briefing(day=day, at=at, status="nothing")
        t = await i18n.chosen(self._store)
        channels = await self._teller.tell("briefing", t("Morning briefing"), text)
        return Briefing(day=day, at=at, status="sent", text=text, channels=channels)


def _plugin_parts(t: Texts, listed: list[Listed], chosen: ProactiveSettings, today: date) -> list[Part]:
    """A part per plugin's list, under the heading it gives, without the items of a muted kind."""
    return [
        Part(
            found.today.heading or found.plugin,
            [item_line(t, i, today) for i in found.today.items if i.kind not in chosen.muted],
        )
        for found in listed
        if found.today
    ]


def _key_of(item: TodayItem) -> str:
    return loops.key_of(item.key or item.needs or item.title)


def _mail_key(pick: MailPick) -> str:
    return loops.key_of(f"mail {pick.account} {pick.uid}")


def _day(received: str) -> date:
    """The day a message was received; one whose date can't be read counts as new, so it isn't kept as unanswered."""
    try:
        return datetime.fromisoformat(received).date()
    except ValueError:
        return date.max
