"""How sure routing a message from the inbox has to be to continue a conversation, from any client
(Settings → Model, /model), and routing a new conversation's first message (core/conversation/first_message.py)."""

from assistant.core import inbox
from assistant.core.agent.base import ServiceBase
from assistant.core.conversation import dispatch_setting, first_message
from assistant.core.conversation.dispatch_setting import DispatchSetting


class DispatchMixin(ServiceBase):
    async def dispatch_setting(self) -> DispatchSetting:
        return await dispatch_setting.load(self._storage.store)

    async def set_dispatch_setting(self, setting: DispatchSetting) -> DispatchSetting:
        """Applies from the next message. Raises DispatchSettingError."""
        return await dispatch_setting.save(self._storage.store, setting)

    async def route_first_message(self, user_id: str, text: str) -> str:
        """The conversation the first message of a new one continues, "" for none."""
        store = self._storage.store
        inbox_id = await inbox.current(store, user_id) or ""
        search = self._storage.search
        return await first_message.place(self._classify, store, search, user_id, inbox_id, text, self._similar)
