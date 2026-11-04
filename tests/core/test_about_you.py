"""The apps' About you step: its answers written to the profile and read back, the extras' plugins it
suggests, and the get-to-know-you offer that still comes after it."""

import pytest

from lo9i.core.agent import AboutYou, MemoryEditError
from lo9i.core.mcp import servers
from lo9i.core.mcp.install import FoundServer
from lo9i.core.mcp.servers import McpServer
from lo9i.core.memory import about_you, facts, profile
from lo9i.core.memory.profile import MAX_ITEMS, Profile
from lo9i.core.repositories import cache, checkout
from lo9i.core.repositories.known import EXTRAS
from lo9i.core.skills.install import FoundSkill
from tests.conftest import collect

_ANSWERS = AboutYou("Ana", "Spanish", "short", ["email", "media"], "planning trips")


def test_the_answers_go_to_their_sections_and_read_back():
    written, overflow = about_you.written(Profile(how_to_reply=["Plain text, no tables"]), _ANSWERS)
    assert overflow == []
    assert written.about == ["Name: Ana"]
    assert written.how_to_reply == [
        "Reply language: Spanish",
        "Reply length: short and to the point",
        "Plain text, no tables",
    ]
    assert written.goals == ["Wants help with: email, movies and YouTube", "Also wants help with: planning trips"]
    assert about_you.read(written) == _ANSWERS


def test_answers_again_replace_theirs_in_place_and_an_empty_one_is_taken_out():
    first, _ = about_you.written(Profile(about=["Lives in Madrid", "name: Ann"]), _ANSWERS)
    assert first.about == ["Lives in Madrid", "Name: Ana"]
    again, _ = about_you.written(first, AboutYou("Ana María", reply_length="detailed"))
    assert again.about == ["Lives in Madrid", "Name: Ana María"]
    assert again.how_to_reply == ["Reply length: detailed, with explanations"]
    assert again.goals == []


def test_an_item_pushed_out_of_a_full_section_comes_back():
    full = Profile(about=[f"detail {i}" for i in range(MAX_ITEMS)])
    written, overflow = about_you.written(full, AboutYou("Ana"))
    assert written.about[0] == "Name: Ana" and len(written.about) == MAX_ITEMS
    assert overflow == [f"detail {MAX_ITEMS - 1}"]


def test_only_answers_means_nothing_else_is_in_the_profile():
    assert about_you.only_answers(Profile())
    assert about_you.only_answers(about_you.written(Profile(), _ANSWERS)[0])
    assert not about_you.only_answers(Profile(about=["Name: Ana"], work=["Nurse"]))


async def test_the_step_is_needed_until_there_is_a_name(service):
    status = await service.about_you("owner")
    assert status.needed and status.answers == AboutYou()
    await service.save_about_you("owner", _ANSWERS)
    status = await service.about_you("owner")
    assert not status.needed and status.answers == _ANSWERS
    with pytest.raises(MemoryEditError, match="name"):
        await service.save_about_you("owner", AboutYou("  "))


async def test_a_full_section_keeps_what_it_pushes_out_as_a_fact(service):
    await profile.save(service.store, "owner", Profile(about=[f"detail {i}" for i in range(MAX_ITEMS)]))
    await service.save_about_you("owner", AboutYou("Ana"))
    assert [f.text for f in await facts.load_all(service.store, "owner")] == [f"detail {MAX_ITEMS - 1}"]


@pytest.fixture
async def extras(service, monkeypatch):
    gmail = FoundServer("gmail", "Send and read Gmail", "none", [], False, email=True)
    icloud = FoundServer("icloud", "Send and read iCloud mail", "none", [], False, email=True)
    watchlist = FoundServer("watchlist", "Movies and shows to watch", "none", [], False)
    youtube = FoundSkill("youtube", "Summarize YouTube videos", [])
    hosts = FoundServer("hosts", "Servers reached over SSH", "none", [], False)
    await cache.save(service.store, EXTRAS, cache.Listing("c1", [youtube], [gmail, icloud, watchlist, hosts]))

    async def latest_commit(url: str, token: str = "") -> str:
        return "c1"

    monkeypatch.setattr(checkout, "latest_commit", latest_commit)


async def test_the_extras_plugins_for_each_topic_are_suggested(service, extras):
    found = await service.save_about_you("owner", AboutYou("Ana", help_with=["media", "email", "calendar", "hosts"]))
    assert [(s.topic, [p.name for p in s.servers], [p.name for p in s.skills]) for s in found] == [
        ("media", ["watchlist"], ["youtube"]),
        ("email", ["gmail", "icloud"], []),
        ("hosts", ["hosts"], []),
    ]


async def test_installed_plugins_arent_suggested_and_one_mail_provider_is_enough(service, extras):
    await servers.save(service.store, McpServer("hosts", command="uv", source=EXTRAS))
    icloud = {"id": "icloud", "name": "iCloud", "host": "smtp.mail.me.com", "port": 587, "imap_host": "i"}
    await servers.save(service.store, McpServer("icloud", email_providers=[icloud], source=EXTRAS))
    assert await service.save_about_you("owner", AboutYou("Ana", help_with=["email", "hosts"])) == []


async def test_after_the_step_the_first_message_still_carries_the_offer(service, script):
    await service.save_about_you("owner", _ANSWERS)
    script.reply("Hi Ana!")
    await collect(service.send(await service.session("owner", "cli"), "hello"))
    header = script.requests[-1][-1].content[1]["text"]
    assert "get-to-know-you" in header and "About you step" in header
