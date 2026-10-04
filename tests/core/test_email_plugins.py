"""Email providers come from email plugins, and an account belongs to the plugin it was connected
with: used while that plugin is installed and on, kept but unused without it, deleted with its data."""

from dataclasses import replace

import pytest

from assistant.core.agent import EmailError, McpServer
from assistant.core.conversation.prompt import build_system_prompt
from assistant.core.integrations.email import accounts
from assistant.core.mcp import servers

_GMAIL = {"id": "gmail", "name": "Gmail", "host": "smtp.gmail.com", "port": 587, "imap_host": "imap.gmail.com"}


async def _plugin(service, name: str = "gmail", enabled: bool = True) -> McpServer:
    server = McpServer(name, enabled=enabled, email_providers=[{**_GMAIL, "plugin": name}])
    await servers.save(service.store, server)
    return server


async def _add(service, sender: str, plugin: str = ""):
    return await service.add_email_account("", "smtp.test", 587, "me", "right", sender, plugin=plugin)


async def test_providers_are_the_presets_of_the_email_plugins_that_are_on(service):
    assert await service.email_providers() == []
    await _plugin(service)
    await _plugin(service, "off", enabled=False)
    [gmail] = await service.email_providers()
    assert (gmail.id, gmail.name, gmail.plugin, gmail.imap_host) == ("gmail", "Gmail", "gmail", "imap.gmail.com")


async def test_an_account_belongs_to_its_plugin_and_needs_it_installed(service, smtp):
    with pytest.raises(EmailError, match="gmail isn't an email plugin"):
        await _add(service, "me@gmail.com", "gmail")
    await _plugin(service)
    account = await _add(service, "me@gmail.com", "gmail")
    assert account.plugin == "gmail"


async def test_without_its_plugin_an_account_is_kept_but_not_used(service, smtp):
    server = await _plugin(service)
    await _add(service, "me@gmail.com", "gmail")
    hand = await _add(service, "me@test.com")
    await servers.save(service.store, replace(server, enabled=False))
    assert [a.sender for a in await service.email_accounts()] == ["me@test.com"]
    assert "me@gmail.com" not in await build_system_prompt(service.store, "u", "", "")
    # The default is off with its plugin, so the account in use stands in for it.
    assert (await accounts.load(service.store, service.secrets)).account_id == hand.id
    with pytest.raises(EmailError, match="No email account called"):
        await accounts.load(service.store, service.secrets, "me@gmail.com")
    await servers.save(service.store, server)
    assert {a.sender for a in await service.email_accounts()} == {"me@gmail.com", "me@test.com"}


async def test_removing_the_plugin_with_its_data_deletes_its_accounts(service, smtp):
    await _plugin(service)
    await _add(service, "me@gmail.com", "gmail")
    await _add(service, "me@test.com")
    await service.remove_mcp_server("gmail")
    await _plugin(service)
    assert len(await service.email_accounts()) == 2
    await service.remove_mcp_server("gmail", delete_data=True)
    await _plugin(service)
    assert [a.sender for a in await service.email_accounts()] == ["me@test.com"]
