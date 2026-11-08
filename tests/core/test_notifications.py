from dataclasses import asdict

from lo9i.core import notifications
from lo9i.core.notifications import Notification


async def test_the_feed_keeps_only_what_needs_the_user(service):
    kept = await notifications.add(service.store, "owner", "reminder", "Reminder", "Call the bank.", True)
    assert await notifications.add(service.store, "owner", "background", "Trip", "✅ Done.", True) is None
    assert await notifications.add(service.store, "owner", "briefing", "Morning briefing", "Today.", True) is None
    assert (
        await notifications.add_job_run(service.store, "owner", "news", "2026-11-08T08:00:00+00:00", "", True) is None
    )
    assert await notifications.recent(service.store, "owner") == [kept]


async def test_what_the_feed_kept_before_that_doesnt_need_the_user_isnt_listed_and_clears(service):
    old = Notification("old", "2026-11-01T08:00:00+00:00", "background", "Trip", "✅ Done.", True)
    await service.store.aput(("notifications", "owner"), old.id, asdict(old))
    kept = await notifications.add(service.store, "owner", "reminder", "Reminder", "Call the bank.", True)
    assert await notifications.recent(service.store, "owner") == [kept]
    await notifications.clear(service.store, "owner")
    assert await service.store.asearch(("notifications", "owner")) == []
