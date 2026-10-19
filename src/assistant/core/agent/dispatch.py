"""How sure routing a message from the inbox has to be to continue a conversation, from any client
(Settings → Model, /model)."""

from assistant.core.agent.base import ServiceBase
from assistant.core.conversation import dispatch_setting
from assistant.core.conversation.dispatch_setting import DispatchSetting


class DispatchMixin(ServiceBase):
    async def dispatch_setting(self) -> DispatchSetting:
        return await dispatch_setting.load(self._storage.store)

    async def set_dispatch_setting(self, setting: DispatchSetting) -> DispatchSetting:
        """Applies from the next message. Raises DispatchSettingError."""
        return await dispatch_setting.save(self._storage.store, setting)
