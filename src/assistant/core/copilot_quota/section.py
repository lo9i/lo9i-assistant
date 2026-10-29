"""Home's Copilot card, built by code from the last check (core/home/coded.py): the plan, the premium requests
left, the credits used and when they reset. No model call, so it shows when the model is out of quota too."""

from collections.abc import Callable

from langgraph.store.base import BaseStore

from assistant.core.copilot_quota import records
from assistant.core.copilot_quota.quota import CopilotQuota, Quota
from assistant.core.home.model import HomeItem, SectionContent
from assistant.core.llm.choice import ModelChoice


class CopilotSection:
    def __init__(self, store: BaseStore, model: Callable[[], ModelChoice]) -> None:
        """`model` gives the model in use, which changes when the user picks another."""
        self._store = store
        self._model = model

    async def build(self) -> SectionContent:
        if self._model().provider != "copilot":
            return SectionContent(items=[], note="Shown while the model is GitHub Copilot (Settings → Model).")
        check = await records.last(self._store)
        if check is None:
            return SectionContent(items=[], note="Not checked yet.")
        note = f"Couldn't check it again: {check.error}" if check.error else ""
        return SectionContent(items=items(check.quota) if check.quota else [], note=note)


def items(quota: CopilotQuota) -> list[HomeItem]:
    shown = [HomeItem(title=f"Plan: {quota.plan}")] if quota.plan else []
    if quota.premium:
        shown.append(_premium(quota.premium))
    if quota.chat and not quota.chat.unlimited:
        shown.append(HomeItem(title=f"Chat: {_left(quota.chat)}"))
    if quota.reset_date:
        shown.append(HomeItem(title="Resets", date=quota.reset_date))
    return shown


def _premium(quota: Quota) -> HomeItem:
    return HomeItem(title=f"Premium requests: {_left(quota)}", subtitle=f"{quota.credits_used:,.0f} credits used")


def _left(quota: Quota) -> str:
    if quota.unlimited:
        return "Unlimited"
    of = f" ({quota.remaining:,.0f} of {quota.entitlement:,.0f})" if quota.entitlement else ""
    return f"{quota.percent_left}% left{of}"
