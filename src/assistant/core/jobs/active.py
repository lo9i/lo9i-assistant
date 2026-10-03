"""Job runs in progress, one Store record each under ("job_runs", user_id), keyed by conversation.

A record is saved when a run starts and removed once the run is recorded on its job, so a run the
daemon stopped in the middle of (a restart while it waited for approval) is found on the next start.
"""

from dataclasses import asdict, dataclass

from langgraph.store.base import BaseStore


@dataclass
class ActiveRun:
    user_id: str
    job: str
    thread_id: str
    started: str


def namespace(user_id: str) -> tuple[str, ...]:
    return ("job_runs", user_id)


async def start(store: BaseStore, run: ActiveRun) -> None:
    await store.aput(namespace(run.user_id), run.thread_id, asdict(run))


async def finish(store: BaseStore, run: ActiveRun) -> None:
    await store.adelete(namespace(run.user_id), run.thread_id)


async def all_runs(store: BaseStore) -> list[ActiveRun]:
    items = await store.asearch(("job_runs",), limit=10_000)
    return [ActiveRun(**i.value) for i in items]
