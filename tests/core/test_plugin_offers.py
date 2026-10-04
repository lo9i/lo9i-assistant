"""Plugins the agent offers (offer_plugin): the system prompt lists the extras' plugins that aren't
installed, the run waits while the user installs one in the app, and a failed send on a channel that
isn't installed points to the offer."""

import pytest

from assistant.core.conversation.prompt import build_system_prompt
from assistant.core.events import ApprovalRequired, Done, ToolFinished, is_plugin_offer
from assistant.core.mcp import servers
from assistant.core.mcp.install import FoundServer, ServerField
from assistant.core.mcp.servers import McpServer
from assistant.core.repositories import cache, checkout
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.known import EXTRAS
from assistant.core.skills.install import FoundSkill
from tests.conftest import collect

_TELEGRAM = FoundServer(
    "telegram",
    "Chat with the assistant on Telegram, and get its messages and reminders there",
    "none",
    [ServerField("TELEGRAM_TOKEN", "Bot token", secret=True, help="https://t.me/BotFather")],
    False,
    channel=True,
)
_SETUP_HINT = " If it isn't set up yet (email accounts, a channel's pairing), open_plugin_setup opens it here."
_NOTES = FoundSkill("notes", "Keep notes in a folder", [])


@pytest.fixture
async def extras(service, monkeypatch):
    """The extras as last read by the update checker; reading them again finds the same commit."""
    await cache.save(service.store, EXTRAS, cache.Listing("c1", [_NOTES], [_TELEGRAM]))

    async def latest_commit(url: str) -> str:
        return "c1"

    monkeypatch.setattr(checkout, "latest_commit", latest_commit)


async def _offered(service, script, channel: str = "web", name: str = "telegram"):
    script.call("offer_plugin", name=name).reply("ok")
    session = await service.session("owner", channel)
    events = await collect(service.send(session, "I want your messages on Telegram"))
    return session, events


async def _install_telegram(service) -> None:
    """What the app's install dialog does: the daemon saves the plugin."""
    await servers.save(service.store, McpServer("telegram", channel_command="uv", source=EXTRAS))


async def test_the_prompt_lists_the_plugins_not_installed(service, extras):
    prompt = await build_system_prompt(service.store, "owner", "", "")
    assert "# Plugins you can offer" in prompt and "offer_plugin" in prompt
    assert f"- telegram: {_TELEGRAM.description}" in prompt and f"- notes: {_NOTES.description}" in prompt
    await _install_telegram(service)
    assert "- telegram:" not in await build_system_prompt(service.store, "owner", "", "")


async def test_no_section_before_the_extras_were_read(service):
    assert "Plugins you can offer" not in await build_system_prompt(service.store, "owner", "", "")


async def test_the_run_waits_while_the_user_installs_it_in_the_app(service, script, extras):
    session, events = await _offered(service, script)
    offer = next(e for e in events if isinstance(e, ApprovalRequired))
    assert is_plugin_offer(offer.request)
    assert (offer.request["name"], offer.request["description"]) == ("telegram", _TELEGRAM.description)
    assert offer.request["server"]["fields"][0]["key"] == "TELEGRAM_TOKEN"
    await _install_telegram(service)
    events = await collect(service.resume(session, {offer.interrupt_id: {"installed": True}}))
    assert events[0].output == "telegram is installed." + _SETUP_HINT
    assert isinstance(events[-1], Done)


async def test_an_installed_email_plugin_points_to_its_setup(service, script, extras):
    gmail = FoundServer("gmail", "Send and read Gmail", "none", [], False, email=True)
    await cache.save(service.store, EXTRAS, cache.Listing("c1", [_NOTES], [_TELEGRAM, gmail]))
    session, events = await _offered(service, script, name="gmail")
    offer = next(e for e in events if isinstance(e, ApprovalRequired))
    gmail_provider = {"id": "gmail", "name": "Gmail", "host": "smtp.gmail.com", "port": 587, "imap_host": "i"}
    await servers.save(service.store, McpServer("gmail", email_providers=[gmail_provider], source=EXTRAS))
    events = await collect(service.resume(session, {offer.interrupt_id: {"installed": True}}))
    assert events[0].output == "gmail is installed." + _SETUP_HINT


async def test_what_counts_is_whats_installed_not_the_answer(service, script, extras):
    session, events = await _offered(service, script)
    offer = next(e for e in events if isinstance(e, ApprovalRequired))
    events = await collect(service.resume(session, {offer.interrupt_id: {"installed": True}}))
    assert events[0] == ToolFinished("offer_plugin", "The user didn't install telegram.")


async def test_chat_channels_point_to_the_app_and_unknown_names_list_the_plugins(service, script, extras):
    _, events = await _offered(service, script, channel="telegram")
    assert "Not offered: telegram can't show the install" in events[1].output
    assert not any(isinstance(e, ApprovalRequired) for e in events)
    _, events = await _offered(service, script, name="whatsapp")
    assert events[1].output == "The extras have no plugin named whatsapp. They have: notes, telegram."
    await _install_telegram(service)
    _, events = await _offered(service, script)
    assert events[1].output.startswith("telegram is installed.")


async def test_the_extras_unreachable_and_never_read(service, script, monkeypatch):
    async def latest_commit(url: str) -> str:
        raise RepositoryError("Couldn't reach GitHub")

    monkeypatch.setattr(checkout, "latest_commit", latest_commit)
    _, events = await _offered(service, script)
    assert events[1].output == "The extras can't be read right now: Couldn't reach GitHub"


async def test_a_failed_send_on_a_channel_not_installed_points_to_the_offer(service, script, extras):
    script.call("send_message", text="Stretch!", channel="telegram").reply("ok")
    events = await collect(service.send(await service.session("owner", "cli"), "remind me on Telegram"))
    assert events[1].output == "telegram isn't installed. Offer it to the user with offer_plugin."
    script.call("send_message", text="Stretch!", channel="fax").reply("ok")
    events = await collect(service.send(await service.session("owner", "cli"), "fax me"))
    assert events[1].output.startswith("Can't send on fax right now")


async def test_the_setup_opens_in_the_conversation_and_tells_what_it_left(service, script, extras, monkeypatch):
    from assistant.core.events import is_plugin_setup
    from assistant.core.integrations.email import smtp

    async def verify(config):
        pass

    monkeypatch.setattr(smtp, "verify", verify)
    gmail = FoundServer("gmail", "Send and read Gmail", "none", [], False, email=True)
    await cache.save(service.store, EXTRAS, cache.Listing("c1", [_NOTES], [_TELEGRAM, gmail]))
    gmail_provider = {"id": "gmail", "name": "Gmail", "host": "smtp.gmail.com", "port": 587, "imap_host": "i"}
    await servers.save(service.store, McpServer("gmail", email_providers=[gmail_provider], source=EXTRAS))
    script.call("open_plugin_setup", name="gmail").reply("ok")
    session = await service.session("owner", "web")
    events = await collect(service.send(session, "set up my Gmail"))
    setup = next(e for e in events if isinstance(e, ApprovalRequired))
    assert is_plugin_setup(setup.request) and setup.request["server"]["email"]
    await service.add_email_account("", "smtp.gmail.com", 587, "me@gmail.com", "pw", "me@gmail.com", plugin="gmail")
    events = await collect(service.resume(session, {setup.interrupt_id: {"done": True}}))
    assert events[0].output == "The user closed gmail's setup. Its email accounts: me@gmail.com."


async def test_the_setup_needs_an_installed_plugin_with_something_to_set_up(service, script, extras):
    script.call("open_plugin_setup", name="telegram").reply("ok")
    events = await collect(service.send(await service.session("owner", "web"), "pair telegram"))
    assert events[1].output == "telegram isn't an installed plugin. Offer it with offer_plugin first."
    await _install_telegram(service)
    script.call("open_plugin_setup", name="telegram").reply("ok")
    events = await collect(service.send(await service.session("owner", "telegram"), "pair"))
    assert events[1].output.startswith("Not opened: telegram can't show it.")
