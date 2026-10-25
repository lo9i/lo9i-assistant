"""The doctor's records: one report per day checked under ("doctor", user_id), the last KEPT_DAYS of them, so a
check compares with the day before; and the causes marked as known noise under ("doctor", user_id, "known"). Writing
them publishes a `doctor` event (core/storage.py)."""

from datetime import date

from langgraph.store.base import BaseStore

from assistant.core.doctor.model import DoctorReport, KnownCause

KEPT_DAYS = 7
_REPORT = "report:"
_SCAN_LIMIT = 1000


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("doctor", user_id)


def _known(user_id: str) -> tuple[str, ...]:
    return (*_namespace(user_id), "known")


async def reports(store: BaseStore, user_id: str) -> list[DoctorReport]:
    """The latest day first."""
    items = await store.asearch(_namespace(user_id), limit=_SCAN_LIMIT)
    found = [DoctorReport.model_validate(i.value) for i in items if i.key.startswith(_REPORT)]
    return sorted(found, key=lambda r: r.day, reverse=True)


async def latest(store: BaseStore, user_id: str) -> DoctorReport | None:
    return next(iter(await reports(store, user_id)), None)


async def of_day(store: BaseStore, user_id: str, day: date) -> DoctorReport | None:
    item = await store.aget(_namespace(user_id), _REPORT + day.isoformat())
    return DoctorReport.model_validate(item.value) if item else None


async def before(store: BaseStore, user_id: str, day: date) -> DoctorReport | None:
    """The report of the latest day checked before `day`."""
    return next((r for r in await reports(store, user_id) if r.day < day.isoformat()), None)


async def save(store: BaseStore, user_id: str, report: DoctorReport) -> None:
    await store.aput(_namespace(user_id), _REPORT + report.day, report.model_dump())
    for old in (await reports(store, user_id))[KEPT_DAYS:]:
        await store.adelete(_namespace(user_id), _REPORT + old.day)


async def known(store: BaseStore, user_id: str) -> list[KnownCause]:
    """The latest marked first."""
    items = await store.asearch(_known(user_id), limit=_SCAN_LIMIT)
    return sorted((KnownCause.model_validate(i.value) for i in items), key=lambda k: k.at, reverse=True)


async def mark_known(store: BaseStore, user_id: str, cause: KnownCause) -> None:
    await store.aput(_known(user_id), cause.id, cause.model_dump())


async def forget_known(store: BaseStore, user_id: str, cause_id: str) -> bool:
    """False for a cause that wasn't marked."""
    if await store.aget(_known(user_id), cause_id) is None:
        return False
    await store.adelete(_known(user_id), cause_id)
    return True
