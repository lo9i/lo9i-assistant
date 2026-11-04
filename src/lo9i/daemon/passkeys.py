"""Passkeys over HTTP: a paired browser adds one and lists or removes them; a browser signs in with one
instead of a pairing code (core/passkeys.py). Each step is two requests: the options the browser's
`navigator.credentials` takes, under a ceremony id, then what the browser answered for that ceremony."""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from lo9i.core.agent import AssistantService, Device, Passkey, PasskeyError, Site
from lo9i.core.i18n import message, said
from lo9i.core.passkeys import site_for
from lo9i.daemon.auth import PairingLimiter, device_of, ip_of, set_device_cookie

logger = logging.getLogger(__name__)


class PasskeyCeremony(BaseModel):
    ceremony: str
    # PublicKeyCredentialCreationOptions or ...RequestOptions as JSON, binary values base64url.
    options: dict[str, Any]


class PasskeyAnswer(BaseModel):
    ceremony: str
    # The PublicKeyCredential the browser returned, as JSON, binary values base64url.
    credential: dict[str, Any]


class PasskeyRemoved(BaseModel):
    ok: bool = True


def add_passkey_routes(app: FastAPI, service: AssistantService) -> None:
    _add_sign_in_routes(app, service)

    @app.get("/passkeys")
    async def passkey_list() -> list[Passkey]:
        """Every device's, most recently used first."""
        return await service.list_passkeys()

    @app.post("/passkeys/options")
    async def passkey_options(request: Request) -> PasskeyCeremony:
        """Starts adding a passkey for the calling device."""
        device = device_of(request)
        if device is None:
            raise HTTPException(403, said("Only a paired browser can add a passkey."))
        ceremony, options = await service.passkey_options(_site(request), device)
        return PasskeyCeremony(ceremony=ceremony, options=options)

    @app.post("/passkeys")
    async def add_passkey(body: PasskeyAnswer) -> Passkey:
        try:
            passkey = await service.add_passkey(body.ceremony, body.credential)
        except PasskeyError as e:
            raise HTTPException(400, message(e)) from e
        logger.info("Added a passkey for device %s", passkey.device_id)
        return passkey

    @app.delete("/passkeys/{passkey_id}")
    async def remove_passkey(passkey_id: str) -> PasskeyRemoved:
        try:
            await service.remove_passkey(passkey_id)
        except PasskeyError as e:
            raise HTTPException(404, message(e)) from e
        return PasskeyRemoved()


def _add_sign_in_routes(app: FastAPI, service: AssistantService) -> None:
    """Open to browsers that aren't paired: the passkey is what proves the device."""
    limiter = PairingLimiter()

    @app.post("/auth/passkey/options")
    async def sign_in_options(request: Request) -> PasskeyCeremony:
        ceremony, options = service.passkey_sign_in_options(_site(request))
        return PasskeyCeremony(ceremony=ceremony, options=options)

    @app.post("/auth/passkey")
    async def sign_in(body: PasskeyAnswer, request: Request, response: Response) -> Device:
        """Signs this browser in as the passkey's device, and sets its token cookie."""
        ip = ip_of(request)
        if limiter.blocked(ip):
            raise HTTPException(429, said("Too many failed sign-ins. Wait a few minutes and try again."))
        try:
            device, token = await service.sign_in_with_passkey(body.ceremony, body.credential, ip)
        except PasskeyError as e:
            limiter.failed(ip)
            raise HTTPException(400, message(e)) from e
        logger.info("Signed in device %s (%s) with a passkey from %s", device.name, device.id, ip)
        set_device_cookie(response, token)
        return device


def _site(request: Request) -> Site:
    """The site the browser opened: its host name was checked to be the daemon's own (api.py's
    known hosts), so a passkey made here can't be asked for from another."""
    url = request.url
    try:
        return site_for(url.scheme, url.hostname or "", url.port)
    except PasskeyError as e:
        raise HTTPException(400, message(e)) from e
