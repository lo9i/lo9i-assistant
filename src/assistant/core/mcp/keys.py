"""A plugin's keys: the values the user gave its fields (API keys, passwords, addresses), and every
env and header value of an MCP server added by hand. They're encrypted with the secret store
(core/secret_store.py), apart from the server's Store record (servers.py), which keeps their names
with empty values: a server is saved with `save`, never servers.save, and `fill` puts the values back
for whatever starts or connects it.

When a plugin is removed its keys stay until the user says to delete them, so installing it again
can leave its fields empty and keep them (`given`)."""

import json
from dataclasses import dataclass, field, replace

from langgraph.store.base import BaseStore

from assistant.core import secret_store
from assistant.core.mcp import servers
from assistant.core.mcp.servers import McpServer
from assistant.core.secret_store import SecretBox

# The names of each plugin's kept keys, readable without the key file; their values are secrets.
_NAMESPACE = ("plugin_keys",)


@dataclass(frozen=True)
class Keys:
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def names(self) -> list[str]:
        return sorted({*self.env, *self.headers})


def names_in(server: McpServer) -> set[str]:
    """Which of its env and header values are keys: the fields of a plugin installed from a
    repository, everything in one added by hand."""
    return set(server.keys) if server.source else {*server.env, *server.headers}


def split(server: McpServer) -> tuple[McpServer, Keys]:
    """The server with its keys' values emptied, and the keys."""
    secret = names_in(server)
    keys = Keys(
        {k: v for k, v in server.env.items() if k in secret}, {k: v for k, v in server.headers.items() if k in secret}
    )
    blank = replace(
        server,
        env={k: "" if k in secret else v for k, v in server.env.items()},
        headers={k: "" if k in secret else v for k, v in server.headers.items()},
    )
    return blank, keys


async def save(store: BaseStore, box: SecretBox, server: McpServer) -> None:
    """The server's record, and its keys encrypted. A key given empty keeps its saved value."""
    servers.validate(server)
    blank, keys = split(server)
    await put(store, box, server.name, keys)
    await servers.save(store, blank)


async def fill_all(store: BaseStore, box: SecretBox, found: list[McpServer]) -> list[McpServer]:
    return [await fill(store, box, s) for s in found]


async def put(store: BaseStore, box: SecretBox, name: str, keys: Keys) -> None:
    """Saves them, keeping a saved value for each one given empty."""
    kept = await get(store, box, name)
    merged = Keys(
        {k: v or kept.env.get(k, "") for k, v in keys.env.items()},
        {k: v or kept.headers.get(k, "") for k, v in keys.headers.items()},
    )
    await _write(store, box, name, merged)


async def forget(store: BaseStore, box: SecretBox, name: str, key: str) -> None:
    """Drop one key's saved value, which `put` keeps when it's given empty: a plugin signing out
    (plugin_oauth.py)."""
    kept = await get(store, box, name)
    left = Keys({k: v for k, v in kept.env.items() if k != key}, {k: v for k, v in kept.headers.items() if k != key})
    await _write(store, box, name, left)


async def _write(store: BaseStore, box: SecretBox, name: str, keys: Keys) -> None:
    if not keys.names:
        await delete(store, name)
        return
    await secret_store.put(store, box, _ref(name), json.dumps({"env": keys.env, "headers": keys.headers}))
    await store.aput(_NAMESPACE, name, {"names": keys.names})


async def get(store: BaseStore, box: SecretBox, name: str) -> Keys:
    """Empty when none are kept. Raises SecretError when the key file can't read them."""
    text = await secret_store.get(store, box, _ref(name))
    data = json.loads(text) if text else {}
    return Keys(data.get("env", {}), data.get("headers", {}))


async def names(store: BaseStore, name: str) -> list[str]:
    """The names of the keys kept for a plugin, without reading their values."""
    item = await store.aget(_NAMESPACE, name)
    return list(item.value.get("names", [])) if item else []


async def kept(store: BaseStore) -> dict[str, list[str]]:
    """Every plugin's kept keys' names, by plugin, without reading their values."""
    items = await store.asearch(_NAMESPACE, limit=10_000)
    return {item.key: list(item.value.get("names", [])) for item in items}


async def delete(store: BaseStore, name: str) -> None:
    await secret_store.delete(store, _ref(name))
    await store.adelete(_NAMESPACE, name)


async def fill(store: BaseStore, box: SecretBox, server: McpServer) -> McpServer:
    """The server with its keys' values back in."""
    keys = await get(store, box, server.name)
    return replace(
        server,
        env={k: keys.env.get(k, v) or v for k, v in server.env.items()},
        headers={k: keys.headers.get(k, v) or v for k, v in server.headers.items()},
    )


async def given(store: BaseStore, box: SecretBox, name: str, values: dict[str, str]) -> dict[str, str]:
    """Values for installing a plugin: the ones typed, and for a field left empty, its kept key."""
    kept = await get(store, box, name)
    saved = kept.env | kept.headers
    return {**values, **{k: v for k, v in saved.items() if not values.get(k, "").strip()}}


def _ref(name: str) -> str:
    return f"plugin_keys:{name}"


async def migrate(store: BaseStore, box: SecretBox) -> None:
    """Move keys saved in plain server records, from before they were encrypted, out of them. Such a
    plugin's record doesn't say which values are its fields, so all of them become keys until its
    next update or install says."""
    for server in await servers.load_all(store):
        if server.source and not server.keys:
            server = replace(server, keys=sorted({*server.env, *server.headers}))
        _, found = split(server)
        if any(found.env.values()) or any(found.headers.values()):
            await save(store, box, server)
