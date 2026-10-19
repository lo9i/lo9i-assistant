"""The notifications feed for clients (core/notifications.py): list it, mark it read, dismiss or clear."""

from assistant.core import notifications
from assistant.core.agent.base import ServiceBase
from assistant.core.notifications import Notification

__all__ = ["Notification", "NotificationsMixin"]


class NotificationsMixin(ServiceBase):
    async def notifications(self, user_id: str) -> list[Notification]:
        """Newest first."""
        return await notifications.recent(self._storage.store, user_id)

    async def mark_notifications_read(self, user_id: str) -> None:
        await notifications.mark_read(self._storage.store, user_id)

    async def dismiss_notification(self, user_id: str, notification_id: str) -> bool:
        """False for one that isn't there."""
        dismissed = await notifications.dismiss(self._storage.store, user_id, notification_id)
        if dismissed:
            self.bus.publish("notifications")
        return dismissed

    async def clear_notifications(self, user_id: str) -> None:
        await notifications.clear(self._storage.store, user_id)
        self.bus.publish("notifications")
