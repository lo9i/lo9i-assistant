"""The repositories Plugins lists plugins from: the official extras, built in, and the ones the user
adds and removes. Every address downloads the same fake repository (test_repositories.py)."""

from pathlib import Path

import pytest

from assistant.core.agent import PluginUpdate, Repository, RepositoryError
from assistant.core.mcp import servers
from assistant.core.repositories import cache, offers
from assistant.core.repositories.known import EXTRAS
from tests.core.test_repositories import HELLO, REMOTE, repo  # noqa: F401 (a fixture, used by `remote`)

MINE = "https://github.com/me/my-plugins.git"


@pytest.fixture
def remote(repo: Path) -> Path:  # noqa: F811
    return repo


async def test_the_extras_are_listed_first_and_are_the_only_official_one(service, remote):
    assert await service.repositories() == [Repository(EXTRAS, "lo9i/lo9i-assistant-extras", True)]
    assert await service.add_repository(f" {MINE} ") == Repository(MINE, "me/my-plugins", False)
    assert [(r.name, r.official) for r in await service.repositories()] == [
        ("lo9i/lo9i-assistant-extras", True),
        ("me/my-plugins", False),
    ]


async def test_every_listed_repository_offers_its_plugins(service, remote):
    await service.add_repository(MINE)
    read = await service.repository_plugins()
    assert [(r.repository.url, r.error) for r in read] == [(EXTRAS, ""), (MINE, "")]
    assert all(r.contents and {s.name for s in r.contents.servers} == {"hello", "tasks"} for r in read)


@pytest.mark.parametrize(
    ("url", "problem"),
    [
        (EXTRAS + "/", "listed already"),
        ("http://github.com/me/plugins", "https://"),
        ("ext::sh -c touch% /tmp/x", "https://"),
    ],
)
async def test_a_repository_that_cant_be_added_is_refused(service, remote, url, problem):
    with pytest.raises(RepositoryError, match=problem):
        await service.add_repository(url)
    assert len(await service.repositories()) == 1


async def test_the_same_repository_isnt_added_twice(service, remote):
    await service.add_repository(MINE)
    with pytest.raises(RepositoryError, match="listed already"):
        await service.add_repository("https://github.com/Me/my-plugins/")


async def test_a_repository_that_cant_be_read_isnt_added(service, remote):
    REMOTE["head"] = None
    with pytest.raises(RepositoryError, match="no network"):
        await service.add_repository(MINE)
    assert len(await service.repositories()) == 1


async def test_the_extras_cant_be_removed(service, remote):
    with pytest.raises(RepositoryError, match="built in"):
        await service.remove_repository(EXTRAS)
    with pytest.raises(RepositoryError, match="isn't listed"):
        await service.remove_repository(MINE)


async def test_removing_a_repository_keeps_what_was_installed_from_it(service, remote):
    await service.add_repository(MINE)
    await service.install_from_repository(MINE, [], [HELLO])
    await service.remove_repository(MINE)
    assert [r.url for r in await service.repositories()] == [EXTRAS]
    assert (await servers.load(service._storage.store, "hello")).source == MINE
    assert await cache.load(service._storage.store, MINE) is None


async def test_a_repository_that_cant_be_read_says_why_without_hiding_the_others(service, remote):
    await service.browse_repository(EXTRAS)
    await service.add_repository(MINE)
    await cache.forget(service._storage.store, MINE)
    REMOTE["head"] = None
    read = await service.repository_plugins()
    assert read[0].contents is not None and read[0].error == ""
    assert read[1].contents is None and "no network" in read[1].error


async def test_a_plugin_from_an_added_repository_has_updates_too(service, remote):
    await service.add_repository(MINE)
    await service.install_from_repository(MINE, [], [HELLO])
    manifest = remote / "other" / "general" / "hello" / "server.yaml"
    manifest.write_text(f"version: 2.0.0\n{manifest.read_text()}")
    REMOTE["head"] = "head2"
    await service.repository_plugins()
    assert await service.plugin_updates() == [PluginUpdate("server", "hello", "", "2.0.0")]


async def test_the_agent_offers_only_the_extras_plugins(service, remote):
    await service.add_repository(MINE)
    assert await offers.offerable(service._storage.store) == []


# --- Private repositories ---

PRIVATE = "https://github.com/me/private-plugins"
TOKEN = "ghp_secret"


@pytest.fixture
def private(remote, monkeypatch):
    """PRIVATE answers only with TOKEN, the way git fails without it."""
    from assistant.core.repositories import checkout

    fetch, latest = checkout._fetch, checkout.latest_commit

    def sign_in(url: str, token: str) -> None:
        if url == PRIVATE and token != TOKEN:
            raise RepositoryError("Couldn't get the repository: it's private, or the token can't read it.")

    async def fetch_private(url, dest, token=""):
        sign_in(url, token)
        return await fetch(url, dest, token)

    async def latest_private(url, token=""):
        sign_in(url, token)
        return await latest(url, token)

    monkeypatch.setattr(checkout, "_fetch", fetch_private)
    monkeypatch.setattr(checkout, "latest_commit", latest_private)


async def test_a_private_repository_needs_a_token_that_reads_it(service, private):
    with pytest.raises(RepositoryError, match="private"):
        await service.add_repository(PRIVATE)
    with pytest.raises(RepositoryError, match="private"):
        await service.add_repository(PRIVATE, "wrong")
    added = await service.add_repository(PRIVATE, f" {TOKEN} ")
    assert (added.official, added.private) == (False, True)
    assert (await service.repositories())[1].private


async def test_a_private_repositorys_token_is_kept_encrypted(service, private):
    await service.add_repository(PRIVATE, TOKEN)
    secrets = await service._storage.store.asearch(("secrets",))
    assert len(secrets) == 1 and TOKEN not in str(secrets[0].value)


async def test_a_private_repository_is_listed_installed_from_and_updated_with_its_token(service, private):
    await service.add_repository(PRIVATE, TOKEN)
    await cache.forget(service._storage.store, PRIVATE)
    read = await service.repository_plugins()
    assert read[1].error == "" and read[1].contents is not None
    assert (await service.browse_repository(PRIVATE)).servers
    await service.install_from_repository(PRIVATE, ["expenses"], [HELLO])
    assert (await service.update_mcp_server_from_repository("hello")).source == PRIVATE
    assert (await service.update_installed_skill("expenses")).source == PRIVATE


async def test_removing_a_private_repository_deletes_its_token(service, private):
    await service.add_repository(PRIVATE, TOKEN)
    await service.remove_repository(PRIVATE)
    assert await service._storage.store.asearch(("secrets",)) == []


def test_a_token_reaches_git_as_a_header_for_the_repositorys_host_only():
    import base64

    from assistant.core.repositories.checkout import _auth

    assert _auth(PRIVATE, "") == {}
    env = _auth(PRIVATE, TOKEN)
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraHeader"
    sent = base64.b64decode(env["GIT_CONFIG_VALUE_0"].removeprefix("Authorization: Basic ")).decode()
    assert sent == f"x-access-token:{TOKEN}"
