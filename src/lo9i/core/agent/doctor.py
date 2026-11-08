"""The doctor for clients (core/doctor/): the latest health check, checking today now, and the causes marked as
known noise."""

from lo9i.core.agent.base import ServiceBase
from lo9i.core.doctor.model import Cause, ContextPart, DoctorPage, DoctorReport, KnownCause, StartingContext
from lo9i.core.i18n import Texts

__all__ = ["Cause", "ContextPart", "DoctorMixin", "DoctorPage", "DoctorReport", "KnownCause", "StartingContext"]


class DoctorMixin(ServiceBase):
    async def doctor_page(self, user_id: str) -> DoctorPage:
        return await self.doctor.page(user_id)

    async def starting_context(self, user_id: str, t: Texts) -> StartingContext:
        """What a new conversation's context would be made of now, part by part: the system prompt and the tool
        definitions, as the health check measures them."""
        return await self.doctor.context(user_id, t)

    async def check_health(self, user_id: str) -> DoctorPage:
        """Checks today so far in the background, unless a check runs."""
        return await self.doctor.check_now(user_id)

    async def mark_known(self, user_id: str, cause_id: str) -> bool:
        """The cause is noise: left out from now on. False for one the latest check didn't find."""
        return await self.doctor.mark_known(user_id, cause_id)

    async def forget_known(self, user_id: str, cause_id: str) -> bool:
        """The cause shows again from the next check. False for one that wasn't marked."""
        return await self.doctor.forget_known(user_id, cause_id)
