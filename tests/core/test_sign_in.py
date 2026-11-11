"""Signing in without a client on the computer itself: the setup code pairs the first browser and never another,
and a link emailed to the owner's address pairs a browser once, on the site it was asked from, for a while."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lo9i.core import sign_in_links
from lo9i.core.agent import AboutYou, DeviceError
from lo9i.core.config import settings

_SITE = "https://lo9i.local:8443"
_PAGE = f"{_SITE}/app/sign-in#"


def _code_file() -> Path:
    return Path(settings.setup_code_path)


async def test_the_first_browser_pairs_with_the_setup_code_and_none_after(service):
    _code_file().write_text("k7qm 2xpd\n")
    await service.prepare_setup_code()
    assert await service.setup_code_open()
    device, _ = await service.pair_device("K7QM-2XPD", "Phone", "10.0.0.2")
    assert device.name == "Phone" and not await service.setup_code_open() and not _code_file().exists()
    await service.revoke_device(device.id)
    _code_file().write_text("K7QM-2XPD")
    assert not await service.setup_code_open()
    with pytest.raises(DeviceError):
        await service.pair_device("K7QM-2XPD", "Thief", "10.0.0.3")


async def test_a_setup_code_is_written_where_none_was_given(service):
    await service.prepare_setup_code()
    written = _code_file().read_text().strip()
    assert len(written) == 9 and written[4] == "-" and _code_file().stat().st_mode & 0o077 == 0
    with pytest.raises(DeviceError):
        await service.pair_device("AAAA-AAAA", "Guess", "10.0.0.3")
    assert (await service.pair_device(written, "Laptop", "10.0.0.2"))[0].name == "Laptop"


async def test_pairing_another_way_closes_the_setup_code(service):
    await service.prepare_setup_code()
    written = _code_file().read_text()
    await service.pair_device((await service.open_device_pairing()).code, "Desk", "10.0.0.2")
    assert not await service.setup_code_open()
    _code_file().write_text(written)
    with pytest.raises(DeviceError):
        await service.pair_device(written, "Thief", "10.0.0.3")


async def test_an_install_with_devices_never_offers_the_setup_code(service):
    await service.pair_device((await service.open_device_pairing()).code, "Desk", "10.0.0.2")
    await service.prepare_setup_code()
    assert not _code_file().exists() and not await service.setup_code_open()


async def test_a_setup_code_too_short_to_be_safe_isnt_used(service):
    _code_file().write_text("1234")
    await service.prepare_setup_code()
    assert not await service.setup_code_open()
    with pytest.raises(DeviceError):
        await service.pair_device("1234", "Phone", "10.0.0.2")


async def test_a_link_goes_only_to_the_owners_address(service, smtp):
    assert not await service.sign_in_links_work()
    await service.send_sign_in_link("me@test.com", _SITE, _PAGE, None)
    await service.add_email_account("", "smtp.test", 587, "me", "right", "Me <me@test.com>")
    assert await service.sign_in_links_work()
    await service.send_sign_in_link("someone@else.com", _SITE, _PAGE, None)
    assert smtp == []
    await service.send_sign_in_link(" ME@test.com ", _SITE, _PAGE, "es")
    [(sender, to, subject, body)] = smtp
    assert sender == "Me <me@test.com>" and to == ["me@test.com"] and subject == "Iniciar sesión en lo9i"
    assert _PAGE in body and "15 minutos" in body


async def test_the_address_the_profile_gives_gets_a_link_from_the_default_account(service, smtp):
    await service.add_email_account("", "smtp.test", 587, "me", "right", "lo9i@test.com")
    await service.save_about_you(settings.owner_id, AboutYou(name="Ana", email="ana@home.org"))
    assert (await service.about_you(settings.owner_id)).answers.email == "ana@home.org"
    await service.send_sign_in_link("ana@home.org", _SITE, _PAGE, None)
    [(sender, to, _, _)] = smtp
    assert sender == "lo9i@test.com" and to == ["ana@home.org"]


async def test_a_link_signs_a_browser_in_once_on_its_own_site(service, smtp):
    await service.add_email_account("", "smtp.test", 587, "me", "right", "me@test.com")
    await service.send_sign_in_link("me@test.com", _SITE, _PAGE, None)
    token = smtp[0][3].split(_PAGE, 1)[1].split()[0]
    with pytest.raises(DeviceError):
        await service.sign_in_with_link(token, "https://lo9i.example.ts.net:8443", "Phone", "10.0.0.2")
    device, _ = await service.sign_in_with_link(token, _SITE, "Phone", "10.0.0.2")
    assert [d.id for d in await service.list_devices()] == [device.id]
    with pytest.raises(DeviceError):
        await service.sign_in_with_link(token, _SITE, "Phone", "10.0.0.2")


async def test_a_link_expires(service):
    now = datetime.now(UTC)
    token = await sign_in_links.open_link(service.store, _SITE, now)
    assert not await sign_in_links.take(service.store, token, _SITE, now + sign_in_links.LIFETIME)
    fresh = await sign_in_links.open_link(service.store, _SITE, now)
    assert await sign_in_links.take(service.store, fresh, _SITE, now + sign_in_links.LIFETIME - timedelta(seconds=1))
