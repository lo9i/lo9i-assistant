"""Grouping what the doctor finds by cause: each time something happened is an occurrence, and occurrences with
the same text, apart from its numbers and ids, in the same place are one cause."""

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from assistant.core.doctor.model import Cause, CauseKind, ThreadRef
from assistant.core.logs import LEVELS

_TITLE_CHARS = 300
_EXAMPLE_CHARS = 4000
# Ids (uuids, hashes, thread ids) and numbers change each time the same thing happens.
_IDS = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|\b(?=[0-9a-f]*\d)[0-9a-f]{8,}\b", re.IGNORECASE)
_NUMBERS = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True)
class Occurrence:
    title: str
    where: str
    at: datetime
    level: str = ""
    example: str = ""
    thread: ThreadRef | None = None

    @property
    def key(self) -> str:
        return normalized(self.title)


def normalized(text: str) -> str:
    """The text without what changes each time the same thing happens."""
    return _NUMBERS.sub("N", _IDS.sub("…", text))


def cause_id(kind: CauseKind, key: str, where: str) -> str:
    return hashlib.sha256(f"{kind}\n{key}\n{where}".encode()).hexdigest()[:16]


def group(kind: CauseKind, occurrences: Iterable[Occurrence]) -> list[Cause]:
    """The most frequent first."""
    by_id: dict[str, list[Occurrence]] = {}
    for occurrence in sorted(occurrences, key=lambda o: o.at):
        by_id.setdefault(cause_id(kind, occurrence.key, occurrence.where), []).append(occurrence)
    causes = [_cause(kind, id, found) for id, found in by_id.items()]
    return sorted(causes, key=lambda c: c.count, reverse=True)


def _cause(kind: CauseKind, id: str, found: list[Occurrence]) -> Cause:
    latest = found[-1]
    return Cause(
        id=id,
        kind=kind,
        level=max((o.level for o in found), key=_rank),
        title=_cut(latest.title, _TITLE_CHARS),
        where=latest.where,
        count=len(found),
        first=found[0].at.isoformat(),
        last=latest.at.isoformat(),
        example=_cut(latest.example, _EXAMPLE_CHARS),
        threads=list({o.thread.thread_id: o.thread for o in found if o.thread is not None}.values()),
    )


def _rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else -1


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
