"""A key of a plugin's own, for encrypting what it keeps in its data folder: `data_key: true` in its server.yaml
(format 4). lo9i makes a random one when the plugin is installed, or updated to a version that asks for it, and
keeps it encrypted with the secret store (core/secret_store.py), like the plugin's keys (keys.py). Its processes
(the MCP server, the page, the channel, the agent's worker) get it in `LO9I_DATA_KEY` when they start; it's never
saved with the plugin's record, and the plugin never sees lo9i's own key.

It's a Fernet key (cryptography's: url-safe base64 of 32 random bytes), which the plugin can use as it is. It
stays when the plugin is removed, as its data does, so installing it again opens what it kept; it goes with its
data when the user deletes that."""

from dataclasses import replace

from cryptography.fernet import Fernet
from langgraph.store.base import BaseStore

from assistant.core import secret_store
from assistant.core.mcp.servers import McpServer
from assistant.core.secret_store import SecretBox

ENV = "LO9I_DATA_KEY"


def parse(value: object) -> bool:
    """Raises ValueError for anything but true or false."""
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError("its data_key must be true or false")
    return value


async def ensure(store: BaseStore, box: SecretBox, server: McpServer) -> None:
    """Make the plugin's key if it asks for one and has none yet; one it has is kept, so what it encrypted
    stays readable. Only installing and updating call this, never a process's start: two starting at once
    could each make one."""
    if server.data_key and not await secret_store.get(store, box, _ref(server.name)):
        await secret_store.put(store, box, _ref(server.name), Fernet.generate_key().decode())


async def with_key(store: BaseStore, box: SecretBox, server: McpServer) -> McpServer:
    """The server with its key in its env when it asks for one, for starting its processes. Raises SecretError
    when the key file can't read it."""
    if not server.data_key:
        return server
    key = await secret_store.get(store, box, _ref(server.name))
    return replace(server, env={**server.env, ENV: key}) if key else server


async def delete(store: BaseStore, name: str) -> None:
    await secret_store.delete(store, _ref(name))


def _ref(name: str) -> str:
    return f"plugin_data_key:{name}"
