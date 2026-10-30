"""Reading the allowance: what GitHub reports to VS Code at copilot_internal/user, with the GitHub token the
Copilot model provider uses (core/llm/copilot.py). Plain HTTP: the plan, when it resets, and for each quota
(premium requests, chat, completions) whether it's unlimited and how much of it is left."""

import datetime as dt
import math

import httpx
from pydantic import BaseModel, ValidationError

from assistant.core.i18n import said

_URL = "https://api.github.com/copilot_internal/user"
# GitHub answers this for known editors.
_EDITOR_VERSION = "vscode/1.95.0"
_TIMEOUT = 20


class QuotaCheckError(Exception):
    """The allowance couldn't be read. The text says why."""


class Quota(BaseModel):
    """One of the plan's quotas, as GitHub reports it."""

    unlimited: bool = False
    percent_remaining: float = 100.0
    remaining: float = 0
    entitlement: float = 0
    # Requests past the quota are allowed, and billed.
    overage_permitted: bool = False
    credits_used: float = 0

    @property
    def exhausted(self) -> bool:
        if self.unlimited:
            return False
        return self.percent_remaining <= 0 or (self.entitlement > 0 and self.remaining <= 0)

    @property
    def percent_left(self) -> int:
        """The share left in whole percent, never 0 while some is left."""
        return 0 if self.exhausted else max(1, math.floor(self.percent_remaining))


class CopilotQuota(BaseModel):
    plan: str = ""
    # When the quotas start again, as YYYY-MM-DD; "" when GitHub doesn't say.
    reset_date: str = ""
    # None for a quota GitHub doesn't report.
    premium: Quota | None = None
    chat: Quota | None = None
    completions: Quota | None = None

    def lowest(self) -> Quota | None:
        """The premium requests' or chat's quota with the least left, among those that aren't unlimited."""
        limited = [q for q in (self.premium, self.chat) if q is not None and not q.unlimited]
        return min(limited, key=lambda q: (not q.exhausted, q.percent_remaining), default=None)


async def fetch(github_token: str, transport: httpx.AsyncBaseTransport | None = None) -> CopilotQuota:
    """Raises QuotaCheckError. `transport` replaces the network in tests."""
    headers = {
        "Authorization": f"token {github_token}",
        "Editor-Version": _EDITOR_VERSION,
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(transport=transport, timeout=_TIMEOUT) as http:
        try:
            response = await http.get(_URL, headers=headers)
        except httpx.HTTPError as e:
            raise QuotaCheckError(said("Couldn't reach GitHub: {error}", error=e)) from e
    if response.status_code == 401:
        raise QuotaCheckError(said("GitHub rejected the Copilot token: it's wrong or was revoked."))
    if response.status_code != 200:
        raise QuotaCheckError(
            said("GitHub didn't say the allowance (HTTP {status_code}).", status_code=response.status_code)
        )
    try:
        return parse(response.json())
    except ValueError as e:
        raise QuotaCheckError(said("GitHub's answer isn't JSON: {error}", error=e)) from e


def parse(data: object) -> CopilotQuota:
    """Raises QuotaCheckError for an answer without the plan's quotas."""
    snapshots = data.get("quota_snapshots") if isinstance(data, dict) else None
    if not isinstance(data, dict) or not isinstance(snapshots, dict):
        raise QuotaCheckError(said("GitHub answered without the plan's quotas."))
    try:
        return CopilotQuota(
            plan=str(data.get("copilot_plan") or ""),
            reset_date=_day(data.get("quota_reset_date")),
            premium=_quota(snapshots.get("premium_interactions")),
            chat=_quota(snapshots.get("chat")),
            completions=_quota(snapshots.get("completions")),
        )
    except ValidationError as e:
        raise QuotaCheckError(said("GitHub's quotas didn't read as expected: {error}", error=e)) from e


def _quota(value: object) -> Quota | None:
    return Quota.model_validate(value) if isinstance(value, dict) else None


def _day(value: object) -> str:
    """The day as YYYY-MM-DD, or "" when it isn't one."""
    try:
        return dt.date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return ""
