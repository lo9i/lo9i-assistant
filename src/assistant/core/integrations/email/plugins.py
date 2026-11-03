"""The email plugins installed here: plugins with an `email:` section (core/mcp/install.py), each
offering provider presets. An account belongs to the plugin it was connected with (accounts.py) and
is used only while that plugin is installed and on."""

from dataclasses import replace

from langgraph.store.base import BaseStore

from assistant.core.integrations.email import oauth
from assistant.core.integrations.email.providers import EmailProvider
from assistant.core.mcp import servers


async def providers(store: BaseStore) -> list[EmailProvider]:
    """The presets of the email plugins that are on, by plugin and in the order each declares them."""
    return [
        _built_in(replace(EmailProvider(**data), plugin=server.name))
        for server in await servers.load_all(store)
        if server.enabled
        for data in server.email_providers
    ]


def _built_in(provider: EmailProvider) -> EmailProvider:
    """With whether lo9i has an app of its own for its sign-in: this version's, whatever the one it was installed by."""
    return replace(provider, oauth_built_in=oauth.has_built_in(provider.oauth))


async def active(store: BaseStore) -> set[str]:
    """The email plugins that are installed and on."""
    return {s.name for s in await servers.load_all(store) if s.enabled and s.email_providers}
