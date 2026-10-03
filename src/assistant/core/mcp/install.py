"""MCP servers in a downloaded repository: finding them, installing them, and updating one later.

A server is a folder with a `server.yaml`, at the repository's root, in its folders, or under
`mcp/`. Its folder is copied to `settings.mcp_dir/<name>`, so a local server can run code from it:
`{dir}` in its command, arguments and env values is that folder, `{python}` the daemon's Python.

    name: dav
    description: Calendar and contacts over CalDAV and CardDAV
    command: "{python}"            # or url: https://… for a remote server
    args: ["{dir}/server.py"]
    env: {CALDAV_URL: https://caldav.icloud.com}
    fields:                        # asked for when it's installed: env values, or headers for a URL
      - {key: DAV_USER, label: Apple ID}
      - {key: DAV_PASSWORD, label: App-specific password, secret: true, help: https://account.apple.com}
    trusted: false
    include: []                    # tools the agent gets; empty means all but `exclude`
    exclude: []
"""

import asyncio
import re
import shutil
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.mcp import servers
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.repositories import source as folder_source
from assistant.core.repositories.checkout import checkout, default_name
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.folders import put, subfolders
from assistant.core.repositories.source import Source

MANIFEST = "server.yaml"
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class ServerField:
    """A value the user gives when installing: an env value of a local server, a header of a remote one."""

    key: str
    label: str
    secret: bool = False
    # Where to get it, such as a page that creates the password.
    help: str = ""


@dataclass(frozen=True)
class FoundServer:
    """An MCP server in a repository, before it's installed."""

    name: str
    description: str
    # stdio (a local command) or http (a URL)
    transport: str
    fields: list[ServerField]
    trusted: bool


@dataclass(frozen=True)
class Candidate:
    found: FoundServer
    # The server as written in server.yaml, placeholders and fields not filled in yet.
    template: McpServer
    folder: Path
    # Relative to the repository root.
    path: str

    def server(self, folder: Path, values: dict[str, str], url: str) -> McpServer:
        given = {f.key: values.get(f.key, "") for f in self.found.fields}
        t = self.template
        if t.command:
            env = {k: _fill(v, folder) for k, v in t.env.items()} | given
            return replace(
                t, command=_fill(t.command, folder), args=[_fill(a, folder) for a in t.args], env=env, source=url
            )
        return replace(t, headers=t.headers | given, source=url)


@dataclass(frozen=True)
class ServerValues:
    """A server to install, with the values the user gave for its fields."""

    name: str
    values: dict[str, str] = field(default_factory=dict)


def find(root: Path, url: str) -> dict[str, Candidate]:
    """The repository's servers by name. Raises RepositoryError for a server.yaml that can't work."""
    folders = [root, *subfolders(root), *subfolders(root / "mcp")]
    found = [_candidate(root, f, default_name(url) if f == root else f.name) for f in folders]
    return {c.found.name: c for c in found if c is not None}


async def check(store: BaseStore, wanted: list[ServerValues], found: dict[str, Candidate], url: str) -> None:
    """Raises McpServerError if a server isn't in the repository, its name is taken, or a field is empty."""
    existing = {s.name: s for s in await servers.load_all(store)}
    for item in wanted:
        candidate = found.get(item.name)
        if candidate is None:
            raise McpServerError(f"The repository has no MCP server named {item.name}.")
        if item.name in existing and existing[item.name].source != url:
            raise McpServerError(
                f"There's already an MCP server named {item.name}. Remove it first to install this one."
            )
        if (missing := _missing(candidate, item.values)) is not None:
            raise McpServerError(f"{item.name} needs {missing.label}.")


async def install(candidate: Candidate, values: dict[str, str], url: str, commit: str) -> McpServer:
    """Copy the server's folder in and return its settings, filled in. The caller saves them."""
    target = _folder(candidate.found.name)
    await asyncio.to_thread(put, candidate.folder, target, Source(url, candidate.path, commit))
    return candidate.server(target, values, url)


async def update(store: BaseStore, name: str) -> McpServer:
    """Install the server again from its repository, keeping the values the user gave and their
    choices (on or off, trusted, tools)."""
    current = await servers.load(store, name)
    source = await asyncio.to_thread(folder_source.read, _folder(name))
    if not current.source or source is None:
        raise McpServerError(f"{name} wasn't installed from a repository, so there's nothing to update it from.")
    async with checkout(source.url) as (root, commit):
        candidate = await asyncio.to_thread(_find_at, root, source.path, name)
        values = current.env if current.command else current.headers
        if (missing := _missing(candidate, values)) is not None:
            raise McpServerError(f"The new version of {name} needs {missing.label}: remove it and install it again.")
        new = await install(candidate, values, source.url, commit)
    kept = replace(
        new, enabled=current.enabled, trusted=current.trusted, include=current.include, exclude=current.exclude
    )
    await servers.save(store, kept)
    return kept


def uninstall(name: str) -> None:
    """Delete the server's installed folder, if it has one."""
    shutil.rmtree(_folder(name), ignore_errors=True)


def _missing(candidate: Candidate, values: dict[str, str]) -> ServerField | None:
    return next((f for f in candidate.found.fields if not values.get(f.key, "").strip()), None)


def _find_at(root: Path, path: str, name: str) -> Candidate:
    candidate = _candidate(root, root / path, name)
    if candidate is None or candidate.found.name != name:
        raise McpServerError(f"The repository doesn't have {name} at {path} any more.")
    return candidate


def _candidate(root: Path, folder: Path, name: str) -> Candidate | None:
    manifest = folder / MANIFEST
    if folder.is_symlink() or not manifest.is_file():
        return None
    where = manifest.relative_to(root).as_posix()
    try:
        return _parse(yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}, name, root, folder)
    except (yaml.YAMLError, TypeError, ValueError, McpServerError) as e:
        raise RepositoryError(f"{where} can't be used: {e}") from e


def _parse(data: dict[str, Any], name: str, root: Path, folder: Path) -> Candidate:
    template = McpServer(
        name=str(data.get("name", name)),
        command=str(data.get("command", "")),
        args=[str(a) for a in data.get("args", [])],
        env={str(k): str(v) for k, v in data.get("env", {}).items()},
        url=str(data.get("url", "")),
        headers={str(k): str(v) for k, v in data.get("headers", {}).items()},
        trusted=bool(data.get("trusted", False)),
        include=[str(t) for t in data.get("include", [])],
        exclude=[str(t) for t in data.get("exclude", [])],
    )
    servers.validate(template)
    fields = [_field(f) for f in data.get("fields", [])]
    found = FoundServer(template.name, str(data.get("description", "")), template.transport, fields, template.trusted)
    return Candidate(found, template, folder, folder.relative_to(root).as_posix())


def _field(data: dict[str, Any]) -> ServerField:
    key = str(data["key"])
    if not _KEY.match(key):
        raise ValueError(f"{key!r} isn't a valid field key")
    return ServerField(key, str(data.get("label", key)), bool(data.get("secret", False)), str(data.get("help", "")))


def _fill(text: str, folder: Path) -> str:
    return text.replace("{dir}", str(folder)).replace("{python}", sys.executable)


def _folder(name: str) -> Path:
    return Path(settings.mcp_dir).expanduser() / name
