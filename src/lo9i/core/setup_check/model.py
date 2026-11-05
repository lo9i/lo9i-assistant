"""A setup check's result: each part checked, in the order the apps show them."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Status = Literal["ok", "warn", "fail"]


@dataclass
class SetupCheck:
    # What it checks, the same each time: daemon, model, plugin:<name>, email:<account id>, channel:<name>, web_app,
    # disk, command.
    id: str
    title: str
    status: Status
    # What was found, one line.
    detail: str
    # How to fix it, one line; "" when it's ok.
    fix: str = ""


@dataclass
class SetupReport:
    checks: list[SetupCheck]
    # When it was checked (ISO 8601).
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def failed(self) -> bool:
        return any(c.status == "fail" for c in self.checks)


def merged(checks: list[SetupCheck], own: list[SetupCheck]) -> list[SetupCheck]:
    """`checks` with those of `own` in their place, by id, and those it lacks first: the command's own checks (its
    PATH, the socket it reached the daemon on) over the daemon's."""
    mine = {c.id: c for c in own}
    kept = [mine.pop(c.id, c) for c in checks]
    return list(mine.values()) + kept
