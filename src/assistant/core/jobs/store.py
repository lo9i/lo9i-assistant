"""Job records. One Store record per job, keyed by name, under ("jobs", user_id)."""

import re
from dataclasses import asdict, dataclass, field

from langgraph.store.base import BaseStore

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
# Recent runs kept on each job.
_HISTORY = 10


class JobError(Exception):
    pass


@dataclass
class RunRecord:
    at: str
    status: str  # ok | failed | needs attention | skipped | missed
    summary: str = ""
    thread_id: str = ""


@dataclass
class Job:
    name: str
    user_id: str
    schedule: str
    timezone: str
    task: str
    next_run_at: str
    enabled: bool = True
    runs: list[RunRecord] = field(default_factory=list)
    # Runs once at next_run_at, then turns itself off. `schedule` is empty.
    one_time: bool = False

    def record(self, run: RunRecord) -> None:
        self.runs = [*self.runs, run][-_HISTORY:]


def namespace(user_id: str) -> tuple[str, ...]:
    return ("jobs", user_id)


def check_name(name: str) -> None:
    if not _NAME.match(name):
        raise JobError("Job names use lowercase letters, digits and hyphens, e.g. daily-news.")


async def load(store: BaseStore, user_id: str, name: str) -> Job | None:
    item = await store.aget(namespace(user_id), name)
    return from_value(item.value) if item else None


async def list_jobs(store: BaseStore, user_id: str) -> list[Job]:
    items = await store.asearch(namespace(user_id), limit=1000)
    return sorted((from_value(i.value) for i in items), key=lambda j: j.name)


async def all_jobs(store: BaseStore) -> list[Job]:
    """Every user's jobs, for the scheduler."""
    items = await store.asearch(("jobs",), limit=10_000)
    return [from_value(i.value) for i in items]


async def save(store: BaseStore, job: Job) -> None:
    await store.aput(namespace(job.user_id), job.name, asdict(job))


async def delete(store: BaseStore, user_id: str, name: str) -> bool:
    if await load(store, user_id, name) is None:
        return False
    await store.adelete(namespace(user_id), name)
    return True


def from_value(value: dict) -> Job:
    """A job from its stored (or JSON) form."""
    runs = [RunRecord(**r) for r in value.get("runs", [])]
    return Job(**{**value, "runs": runs})
