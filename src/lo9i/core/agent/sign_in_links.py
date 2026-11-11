"""Sign-in links (core/sign_in_links.py): a browser that isn't paired asks for one with the owner's email address,
and the link emailed pairs it as a new device. Whether the address is the owner's is never said: the request is
answered the same either way and the link is sent after it."""

import logging
from datetime import UTC, datetime
from email.utils import parseaddr

from lo9i.core import i18n, identity, language, sign_in_links
from lo9i.core.agent.devices import DeviceError, DevicesMixin
from lo9i.core.config import settings
from lo9i.core.devices import Device
from lo9i.core.i18n import Texts, said
from lo9i.core.integrations.email import accounts as email_accounts
from lo9i.core.integrations.email import smtp
from lo9i.core.integrations.email.accounts import EmailConfig, EmailError
from lo9i.core.memory import about_you, profile

__all__ = ["SignInLinksMixin"]

logger = logging.getLogger(__name__)

# The name the email gives the assistant while it has none of its own.
_UNNAMED = "lo9i"


class SignInLinksMixin(DevicesMixin):
    async def sign_in_links_work(self) -> bool:
        """Whether there's an email account to send a sign-in link from."""
        return any(config.connected for config in await email_accounts.list_accounts(self._storage.store))

    async def send_sign_in_link(self, address: str, site: str, page: str, app_shows: str | None) -> None:
        """Emails a link that signs a browser in on `site` (an origin, e.g. https://lo9i.local:8443) when `address`
        is the owner's: an email account's, or the profile's. Nothing otherwise. The link is `page` followed by its
        token."""
        try:
            sender = await self._link_sender(address)
            if sender is None:
                logger.info("A sign-in link was asked for an address that isn't the owner's; none was sent.")
                return
            await self._send_link(sender, _address(address), site, page, app_shows)
        except EmailError as e:
            logger.warning("Couldn't send a sign-in link: %s", e)
            return
        logger.info("Sent a sign-in link for %s", site)

    async def _send_link(self, sender: EmailConfig, to: str, site: str, page: str, app_shows: str | None) -> None:
        store = self._storage.store
        token = await sign_in_links.open_link(store, site, datetime.now(UTC))
        t = i18n.texts(language.answered_in(await language.load(store), app_shows))
        name = await identity.load_name(store) or _UNNAMED
        await smtp.send(sender, [to], t("Sign in to {name}", name=name), _body(t, name, site, page + token))

    async def sign_in_with_link(self, token: str, site: str, name: str, ip: str) -> tuple[Device, str]:
        """A new device and its token for the browser that opened the link. Raises DeviceError when the link was
        used, expired or made for another site."""
        if not await sign_in_links.take(self._storage.store, token, site, datetime.now(UTC)):
            raise DeviceError(said("This sign-in link was used already or has expired. Ask for a new one."))
        return await self._new_device(name, ip)

    async def _link_sender(self, address: str) -> EmailConfig | None:
        """The account to send the link from when `address` is the owner's: that account when it's one, else the
        default when it's the address the profile gives. None when it isn't the owner's or nothing can send."""
        store, wanted = self._storage.store, _address(address)
        connected = [config for config in await email_accounts.list_accounts(store) if config.connected]
        if not wanted or not connected:
            return None
        own = next((config for config in connected if _address(config.sender) == wanted), None)
        if own is None and _address(about_you.email(await profile.load(store, settings.owner_id))) != wanted:
            return None
        return await email_accounts.load(store, self.secrets, (own or connected[0]).account_id)


def _address(text: str) -> str:
    """The address alone, in lower case: "Ana <Ana@Example.com>" is ana@example.com."""
    return parseaddr(text)[1].strip().lower()


def _body(t: Texts, name: str, site: str, link: str) -> str:
    minutes = int(sign_in_links.LIFETIME.total_seconds() // 60)
    return t(
        "Someone asked to sign in to {name} at {site} with this address. To sign in on that browser, open this "
        "link there:\n\n{link}\n\nIt works once, for {minutes} minutes. If it wasn't you, ignore this email: "
        "without the link nobody can sign in.",
        name=name,
        site=site,
        link=link,
        minutes=minutes,
    )
