"""Home's Copilot card, built by code from the last check (core/home/coded.py): the plan, the premium requests
left, the credits used and when they reset. No model call, so it shows when the model is out of quota too."""

from collections.abc import Callable

from langgraph.store.base import BaseStore

from assistant.core import i18n
from assistant.core.copilot_quota import records
from assistant.core.copilot_quota.quota import CopilotQuota, Quota
from assistant.core.home.model import HomeItem, SectionContent
from assistant.core.i18n import Texts
from assistant.core.llm.choice import ModelChoice


class CopilotSection:
    def __init__(self, store: BaseStore, model: Callable[[], ModelChoice]) -> None:
        """`model` gives the model in use, which changes when the user picks another."""
        self._store = store
        self._model = model

    async def build(self) -> SectionContent:
        """In the language chosen when it's built."""
        t = await i18n.chosen(self._store)
        if self._model().provider != "copilot":
            return SectionContent(items=[], note=t("Shown while the model is GitHub Copilot (Settings → Model)."))
        check = await records.last(self._store)
        if check is None:
            return SectionContent(items=[], note=t("Not checked yet."))
        note = t("Couldn't check it again: {error}", error=check.error) if check.error else ""
        return SectionContent(items=items(t, check.quota) if check.quota else [], note=note)


def items(t: Texts, quota: CopilotQuota) -> list[HomeItem]:
    shown = [HomeItem(title=t("Plan: {plan}", plan=quota.plan))] if quota.plan else []
    if quota.premium:
        shown.append(_premium(t, quota.premium))
    if quota.chat and not quota.chat.unlimited:
        shown.append(HomeItem(title=t("Chat: {left}", left=_left(t, quota.chat))))
    if quota.reset_date:
        shown.append(HomeItem(title=t("Resets"), date=quota.reset_date))
    return shown


def _premium(t: Texts, quota: Quota) -> HomeItem:
    used = t("{credits} credits used", credits=t.number(quota.credits_used))
    return HomeItem(title=t("Premium requests: {left}", left=_left(t, quota)), subtitle=used)


def _left(t: Texts, quota: Quota) -> str:
    if quota.unlimited:
        return t("Unlimited")
    if not quota.entitlement:
        return t("{percent}% left", percent=quota.percent_left)
    remaining, entitlement = t.number(quota.remaining), t.number(quota.entitlement)
    return t(
        "{percent}% left ({remaining} of {entitlement})",
        percent=quota.percent_left,
        remaining=remaining,
        entitlement=entitlement,
    )
