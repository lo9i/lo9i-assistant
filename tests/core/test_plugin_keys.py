"""A plugin's keys (core/mcp/keys.py): encrypted apart from its record, kept when it's removed until
the user deletes them, used again when it's installed again; and a private repository's token kept
while a plugin from it is installed."""

import json

import pytest

from assistant.core.agent import KeptKeys, McpServer, McpServerChanges, ServerValues
from assistant.core.mcp import keys, servers
from tests.core.test_plugin_repositories import PRIVATE, TOKEN, private, remote  # noqa: F401 (fixtures)
from tests.core.test_repositories import HELLO, URL, repo  # noqa: F401 (a fixture, used by `remote`)


@pytest.fixture
def extras(repo):  # noqa: F811
    """The repository the plugins install from (test_repositories.py)."""
    return repo


@pytest.fixture
def private_repository(private):  # noqa: F811
    """A private repository that answers only with its token (test_plugin_repositories.py)."""
    return private


async def _plain_store(service) -> str:
    """Everything the Store holds, as text, to look for a value in it."""
    found = []
    for namespace in (("mcp_servers",), ("plugin_keys",), ("secrets",)):
        found += [item.value for item in await service.store.asearch(namespace, limit=100)]
    return json.dumps(found)


async def test_a_plugins_keys_are_encrypted_and_reach_it(service, extras):
    await service.install_from_repository(URL, [], [HELLO])
    stored = await _plain_store(service)
    assert "Ana" not in stored and "s3cret" not in stored
    assert await keys.names(service.store, "hello") == ["HELLO_TOKEN", "HELLO_USER"]
    server = await keys.fill(service.store, service.secrets, await servers.load(service.store, "hello"))
    assert (server.env["HELLO_USER"], server.env["HELLO_TOKEN"]) == ("Ana", "s3cret")


async def test_a_server_added_by_hand_has_all_its_values_encrypted(service):
    await service.add_mcp_server(McpServer("remote", url="https://mcp.example.com", headers={"Authorization": "t0k"}))
    assert "t0k" not in await _plain_store(service)
    await service.update_mcp_server("remote", McpServerChanges(trusted=True))
    server = await keys.fill(service.store, service.secrets, await servers.load(service.store, "remote"))
    assert server.headers == {"Authorization": "t0k"}
    assert await service.remove_mcp_server("remote") is None
    assert await keys.names(service.store, "remote") == []


async def test_removing_a_plugin_keeps_its_keys_for_installing_it_again(service, extras):
    await service.install_from_repository(URL, [], [HELLO])
    kept = await service.remove_mcp_server("hello")
    assert kept == KeptKeys("hello", ["HELLO_TOKEN", "HELLO_USER"])
    found = next(s for s in (await service.browse_repository(URL)).servers if s.name == "hello")
    assert found.known_fields == ["HELLO_TOKEN", "HELLO_USER"]
    await service.install_from_repository(URL, [], [ServerValues("hello", {"HELLO_USER": "", "HELLO_TOKEN": ""})])
    server = await keys.fill(service.store, service.secrets, await servers.load(service.store, "hello"))
    assert (server.env["HELLO_USER"], server.env["HELLO_TOKEN"]) == ("Ana", "s3cret")


async def test_a_value_typed_again_replaces_the_kept_one(service, extras):
    await service.install_from_repository(URL, [], [HELLO])
    await service.remove_mcp_server("hello")
    await service.install_from_repository(URL, [], [ServerValues("hello", {"HELLO_USER": "Bea", "HELLO_TOKEN": ""})])
    server = await keys.fill(service.store, service.secrets, await servers.load(service.store, "hello"))
    assert (server.env["HELLO_USER"], server.env["HELLO_TOKEN"]) == ("Bea", "s3cret")


async def test_the_user_can_delete_a_removed_plugins_keys(service, extras):
    await service.install_from_repository(URL, [], [HELLO])
    kept = await service.remove_mcp_server("hello")
    assert kept is not None
    await service.forget_keys(kept)
    assert await keys.names(service.store, "hello") == []
    assert "s3cret" not in await _plain_store(service)


async def test_kept_keys_are_listed_later_until_installed_again_or_deleted(service, extras):
    assert await service.kept_keys() == []
    await service.install_from_repository(URL, [], [HELLO])
    assert await service.kept_keys() == []  # installed: its keys are in use
    await service.remove_mcp_server("hello")
    assert await service.kept_keys() == [KeptKeys("hello", ["HELLO_TOKEN", "HELLO_USER"])]
    await service.install_from_repository(URL, [], [ServerValues("hello", {"HELLO_USER": "", "HELLO_TOKEN": ""})])
    assert await service.kept_keys() == []
    kept = await service.remove_mcp_server("hello")
    assert kept is not None
    await service.forget_keys(kept)
    assert await service.kept_keys() == []


async def test_keys_saved_in_plain_before_are_moved_out_at_start(service):
    old = McpServer("old", command="run", env={"API_KEY": "plain"}, source="https://example.com/x")
    await servers.save(service.store, old)
    await keys.migrate(service.store, service.secrets)
    record = await servers.load(service.store, "old")
    assert (record.env, record.keys) == ({"API_KEY": ""}, ["API_KEY"])
    assert (await keys.fill(service.store, service.secrets, record)).env == {"API_KEY": "plain"}
    await keys.migrate(service.store, service.secrets)  # nothing left to move
    assert (await keys.fill(service.store, service.secrets, record)).env == {"API_KEY": "plain"}


# --- A private repository's token ---


async def test_a_private_repositorys_token_stays_while_a_plugin_from_it_is_installed(service, private_repository):
    await service.add_repository(PRIVATE, TOKEN)
    await service.install_from_repository(PRIVATE, [], [HELLO])
    await service.remove_repository(PRIVATE)
    assert await service.update_mcp_server_from_repository("hello")
    kept = await service.remove_mcp_server("hello")
    assert kept is not None and (kept.repository, kept.repository_name) == (PRIVATE, "me/private-plugins")
    listed = await service.kept_keys()  # kept for later: the plugin's keys, and the token on its own
    assert listed == [KeptKeys("hello", kept.keys), KeptKeys("", [], PRIVATE, "me/private-plugins")]
    await service.forget_keys(listed[1])
    assert await service.kept_keys() == [KeptKeys("hello", kept.keys)]
    await service.forget_keys(kept)
    assert await service.store.asearch(("secrets",)) == []


async def test_a_kept_token_is_used_when_the_repository_is_added_again(service, private_repository):
    await service.add_repository(PRIVATE, TOKEN)
    await service.install_from_repository(PRIVATE, ["expenses"], [])
    await service.remove_repository(PRIVATE)
    assert (await service.add_repository(PRIVATE)).private


async def test_a_listed_repositorys_token_isnt_offered_for_deleting(service, private_repository):
    await service.add_repository(PRIVATE, TOKEN)
    await service.install_from_repository(PRIVATE, ["expenses"], [])
    assert await service.delete_skill("expenses") is None


async def test_a_skill_from_a_removed_private_repository_offers_its_token(service, private_repository):
    await service.add_repository(PRIVATE, TOKEN)
    await service.install_from_repository(PRIVATE, ["expenses"], [])
    await service.remove_repository(PRIVATE)
    kept = await service.delete_skill("expenses")
    assert kept == KeptKeys("expenses", [], PRIVATE, "me/private-plugins")
    await service.forget_keys(kept)
    with pytest.raises(Exception, match="private"):
        await service.add_repository(PRIVATE)
