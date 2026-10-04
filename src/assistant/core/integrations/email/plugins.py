"""The email plugins installed here: plugins with an `email:` section (core/mcp/install.py), each
offering provider presets. An account belongs to the plugin it was connected with (accounts.py) and
is used only while that plugin is installed and on."""

from dataclasses import replace

from langgraph.store.base import BaseStore

from assistant.core.integrations.email.providers import EmailProvider
from assistant.core.mcp import servers


async def providers(store: BaseStore) -> list[EmailProvider]:
    """The presets of the email plugins that are on, by plugin and in the order each declares them."""
    return [
        replace(EmailProvider(**data), plugin=server.name)
        for server in await servers.load_all(store)
        if server.enabled
        for data in server.email_providers
    ]


async def active(store: BaseStore) -> set[str]:
    """The email plugins that are installed and on."""
    return {s.name for s in await servers.load_all(store) if s.enabled and s.email_providers}
