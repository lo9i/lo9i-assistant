"""The repositories the apps install plugins from: the assistant's extras, built in and the only
official one, and the ones the user adds (Settings → Plugins, /plugins), which aren't. The added ones
are one Store record; a private one's token is a secret (secret_store.py), given to git for every
download from it. Removing one leaves what was installed from it: an installed plugin remembers its
repository (source.py), and a private one's token is kept while a plugin from it is installed, so
those keep updating. Once the last of them is removed, the user is asked whether to keep or delete
the token, with the plugin's own keys (`after_removal`, core/mcp/keys.py)."""

import asyncio
from dataclasses import dataclass

from langgraph.store.base import BaseStore

from assistant.core import secret_store
from assistant.core.mcp import keys, servers
from assistant.core.repositories import cache, contents
from assistant.core.repositories.checkout import check_url
from assistant.core.repositories.contents import RepositoryContents
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.known import EXTRAS
from assistant.core.secret_store import SecretBox, SecretError
from assistant.core.skills import store as skills

_NAMESPACE = ("settings",)
_KEY = "plugin_repositories"


@dataclass(frozen=True)
class Repository:
    url: str
    # "lo9i/lo9i-assistant-extras": its path, for lists.
    name: str
    official: bool
    # Read with a token the user gave.
    private: bool = False


@dataclass
class RepositoryPlugins:
    """What one repository offers, or why it couldn't be read."""

    repository: Repository
    contents: RepositoryContents | None
    error: str = ""


@dataclass(frozen=True)
class KeptKeys:
    """What a removed plugin left kept, for the user to keep or delete: its keys' names, and the
    token of the private repository it came from when nothing else needs that any more."""

    plugin: str
    keys: list[str]
    # The repository's address and name; "" when its token isn't left over.
    repository: str = ""
    repository_name: str = ""


async def listed(store: BaseStore) -> list[Repository]:
    """The extras first, then the added ones in the order they were added."""
    urls, private = await _added(store)
    return [_repository(EXTRAS), *(_repository(url, url in private) for url in urls)]


async def add(store: BaseStore, box: SecretBox, url: str, token: str = "") -> Repository:
    """`token` reads a private repository; without one, a token kept from before is used. Raises
    RepositoryError when it's listed already, can't be read, or offers no plugins."""
    url, token = url.strip(), token.strip()
    check_url(url)
    if any(_same(url, r.url) for r in await listed(store)):
        raise RepositoryError(f"{name_of(url)} is listed already.")
    urls, private = await _added(store)
    kept = next((u for u in private if _same(url, u)), None)
    token = token or (await _token_of(store, box, kept) if kept else "")
    await contents.browse(store, url, token)
    private = [u for u in private if u != kept]
    if kept:
        await secret_store.delete(store, _secret(kept))
    if token:
        await secret_store.put(store, box, _secret(url), token)
    await _save(store, [*urls, url], [*private, url] if token else private)
    return _repository(url, bool(token))


async def remove(store: BaseStore, url: str) -> None:
    """Raises RepositoryError for the extras, which are built in, or a repository not listed."""
    if _same(url, EXTRAS):
        raise RepositoryError("The assistant's extras are built in and can't be removed.")
    urls, private = await _added(store)
    found = next((u for u in urls if _same(url, u)), None)
    if found is None:
        raise RepositoryError(f"{name_of(url)} isn't listed.")
    if await in_use(store, found):
        # Its plugins update with its token: kept, unlisted, until the last of them is removed.
        await _save(store, [u for u in urls if u != found], private)
    else:
        await _save(store, [u for u in urls if u != found], [u for u in private if u != found])
        await secret_store.delete(store, _secret(found))
    await cache.forget(store, found)


async def in_use(store: BaseStore, url: str) -> bool:
    """Whether an installed MCP server or skill comes from the repository."""
    if any(_same(url, s.source) for s in await servers.load_all(store) if s.source):
        return True
    installed = await asyncio.to_thread(skills.list_skills)
    return any(s.source and _same(url, s.source) for s in installed)


async def after_removal(store: BaseStore, plugin: str, source: str) -> KeptKeys | None:
    """What a plugin just removed left kept: its keys, and its private repository's token when the
    repository isn't listed and nothing installed comes from it any more. None when nothing is."""
    names = await keys.names(store, plugin)
    _, private = await _added(store)
    orphan = bool(
        source
        and any(_same(source, u) for u in private)
        and not any(_same(source, r.url) for r in await listed(store))
        and not await in_use(store, source)
    )
    if not names and not orphan:
        return None
    return KeptKeys(plugin, names, source if orphan else "", name_of(source) if orphan else "")


async def forget(store: BaseStore, plugin: str, repository: str) -> None:
    """Delete what a removed plugin left kept: its keys when it isn't installed again, and the token
    of `repository` when it isn't listed and nothing installed comes from it."""
    if plugin not in {s.name for s in await servers.load_all(store)}:
        await keys.delete(store, plugin)
    if not repository or any(_same(repository, r.url) for r in await listed(store)):
        return
    if await in_use(store, repository):
        return
    urls, private = await _added(store)
    found = next((u for u in private if _same(repository, u)), None)
    if found:
        await _save(store, urls, [u for u in private if u != found])
        await secret_store.delete(store, _secret(found))


async def _token_of(store: BaseStore, box: SecretBox, url: str) -> str:
    try:
        return await secret_store.get(store, box, _secret(url))
    except SecretError:
        return ""


async def token(store: BaseStore, box: SecretBox, url: str) -> str:
    """The token a repository was added with, while it's listed or a plugin from it is installed;
    "" for a public one."""
    return next((t for u, t in (await tokens(store, box)).items() if _same(url, u)), "")


async def tokens(store: BaseStore, box: SecretBox) -> dict[str, str]:
    """The private repositories' tokens, by address, for updating plugins installed from them. One
    the key file can no longer read is left out: its repository then says it can't be read."""
    found = {url: await _token_of(store, box, url) for url in (await _added(store))[1]}
    return {url: t for url, t in found.items() if t}


async def plugins(store: BaseStore, box: SecretBox) -> list[RepositoryPlugins]:
    """What every listed repository offers, read at the same time. One that can't be read says why
    and doesn't keep the others from showing."""
    keys = await tokens(store, box)
    return list(await asyncio.gather(*(_plugins(store, r, keys.get(r.url, "")) for r in await listed(store))))


async def _plugins(store: BaseStore, repository: Repository, token: str) -> RepositoryPlugins:
    try:
        return RepositoryPlugins(repository, await contents.browse(store, repository.url, token))
    except RepositoryError as e:
        return RepositoryPlugins(repository, None, str(e))


def name_of(url: str) -> str:
    """https://github.com/me/plugins.git → me/plugins."""
    path = url.split("://", 1)[-1].split("/", 1)[-1]
    return path.rstrip("/").removesuffix(".git") or url


def _repository(url: str, private: bool = False) -> Repository:
    return Repository(url, name_of(url), _same(url, EXTRAS), private)


def _same(a: str, b: str) -> bool:
    def key(url: str) -> str:
        return url.strip().rstrip("/").removesuffix(".git").lower()

    return key(a) == key(b)


def _secret(url: str) -> str:
    return f"plugin_repository:{url}"


async def _added(store: BaseStore) -> tuple[list[str], list[str]]:
    """The added repositories' addresses, and those of the private ones among them."""
    item = await store.aget(_NAMESPACE, _KEY)
    value = item.value if item else {}
    return list(value.get("urls", [])), list(value.get("private", []))


async def _save(store: BaseStore, urls: list[str], private: list[str]) -> None:
    await store.aput(_NAMESPACE, _KEY, {"urls": urls, "private": private})
