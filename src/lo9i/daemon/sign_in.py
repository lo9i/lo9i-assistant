"""Signing a browser in without a client on the computer itself: the setup code for the first one (core/setup_code.py,
taken by /auth/pair like a pairing code), and links emailed to the owner for the ones after (core/sign_in_links.py).
Open to browsers that aren't paired, and limited like pairing."""

import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

from lo9i.core.agent import AssistantService, Device, DeviceError
from lo9i.core.i18n import message, said
from lo9i.daemon.auth import DeviceCookie, PairingLimiter, ip_of
from lo9i.daemon.web_ui import PREFIX
from lo9i.protocol import LANGUAGE_HEADER

logger = logging.getLogger(__name__)

# The page that takes a link's token, after #, so the token never reaches a server's log.
_LINK_PAGE = f"{PREFIX}/sign-in#"


class SignInWays(BaseModel):
    """How a browser that isn't paired can sign in."""

    # No device was ever paired: the first one pairs with the setup code.
    setup: bool
    # An email account can send a sign-in link.
    email_link: bool


class LinkRequest(BaseModel):
    email: str = Field(max_length=320)


class LinkAsked(BaseModel):
    ok: bool = True


class LinkSignIn(BaseModel):
    token: str = Field(max_length=200)
    name: str = Field(max_length=200)


def add_sign_in_routes(app: FastAPI, service: AssistantService, cookie: DeviceCookie) -> None:
    asked, wrong = PairingLimiter(), PairingLimiter()

    @app.get("/auth/sign-in")
    async def sign_in_ways() -> SignInWays:
        return SignInWays(setup=await service.setup_code_open(), email_link=await service.sign_in_links_work())

    @app.post("/auth/link")
    async def ask_for_link(body: LinkRequest, request: Request, background: BackgroundTasks) -> LinkAsked:
        """Emails a sign-in link for this site when the address is the owner's. Answered the same, and at once,
        either way: the link goes after the answer."""
        ip = ip_of(request)
        if asked.blocked(ip):
            raise HTTPException(429, said("Too many sign-in links asked for. Wait a few minutes and try again."))
        # Every request counts, since none says whether the address was right.
        asked.failed(ip)
        site = _site_of(request)
        language = request.headers.get(LANGUAGE_HEADER)
        background.add_task(service.send_sign_in_link, body.email, site, f"{site}{_LINK_PAGE}", language)
        return LinkAsked()

    @app.post("/auth/link/finish")
    async def sign_in_with_link(body: LinkSignIn, request: Request, response: Response) -> Device:
        """Pairs this browser as a new device with a link's token, and sets its token cookie."""
        ip = ip_of(request)
        if wrong.blocked(ip):
            raise HTTPException(429, said("Too many failed sign-ins. Wait a few minutes and try again."))
        try:
            device, token = await service.sign_in_with_link(body.token, _site_of(request), body.name, ip)
        except DeviceError as e:
            wrong.failed(ip)
            raise HTTPException(400, message(e)) from e
        logger.info("Signed in device %s (%s) with an emailed link from %s", device.name, device.id, ip)
        cookie.set(response, token)
        return device


def _site_of(request: Request) -> str:
    """The origin the browser opened, as it named it: its host was checked to be one of the daemon's own
    (api.py's known hosts), so a link is never made for another site."""
    url = request.url
    return f"{url.scheme}://{url.netloc}".lower()
