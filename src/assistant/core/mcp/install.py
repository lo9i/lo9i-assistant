"""MCP servers in a downloaded repository: finding them, installing them, and updating one later.

A server is a folder with a `server.yaml`, at the repository's root, in its folders, or under
`mcp/` (MCP servers and chat channels) or `plugins/` (plugins without a process, such as mail
providers). A `SKILL.md` next to it is the server's skill: how to use its tools. It's installed, updated
and removed with the server, under the server's name.

The folder is copied to `settings.mcp_dir/<name>` (core/mcp/folders.py), so a local server can run
code from it. In its commands, arguments and env values:

- `{dir}`: that folder. Updates replace it.
- `{data}`: a folder for its data, only the user's. Updates and removing the server keep it.
- `{socket}`: where its page listens, in `{data}`.
- `{uv}`: the uv the daemon found, to run the server in its own environment (`uv run --project {dir}`).
- `{python}`: the daemon's Python, for servers that need nothing beyond it.

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
    page:                          # optional: a web page, shown in the web app (core/mcp/pages.py)
      command: "{uv}"
      args: [run, --project, "{dir}", my-page, --socket, "{socket}"]
    channel:                       # optional: a chat channel (core/channels/), with or without `command`
      command: "{uv}"
      args: [run, --project, "{dir}", my-channel]
      style: A phone chat. Short messages.   # how to write there, for the system prompt
    libraries: [lo9i-chat]         # folders under lib/ in the repository it uses (folders.library)
    category: communications       # what it's for, to group it in the apps (repositories/categories.py)
    email:                         # optional: email providers it offers (core/integrations/email/providers.py)
      - {id: gmail, name: Gmail, host: smtp.gmail.com, port: 587, imap_host: imap.gmail.com,
         password_help: Gmail needs an app password., password_url: https://myaccount.google.com/apppasswords}
"""

import asyncio
import contextlib
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from langgraph.store.base import BaseStore

from assistant.core.integrations.email import providers as email_providers
from assistant.core.mcp import folders, servers
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.repositories import categories
from assistant.core.repositories import source as folder_source
from assistant.core.repositories.checkout import checkout, default_name
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.folders import SERVER_FILE, SKILL_FILE, put, subfolders, valid_path
from assistant.core.repositories.source import Source
from assistant.core.skills import store as skills
from assistant.core.skills.errors import SkillError
from assistant.core.uv import find as find_uv

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
    # It comes with a skill (a SKILL.md next to its server.yaml).
    skill: bool = False
    # It comes with a web page.
    page: bool = False
    # It's a chat channel.
    channel: bool = False
    # Fields the daemon already has values for (core/channels/legacy.py): they may be left empty.
    known_fields: list[str] = field(default_factory=list)
    # Installed here from the same repository.
    installed: bool = False
    # `version:` in its server.yaml, and the one installed here; "" when none is declared or installed.
    version: str = ""
    installed_version: str = ""
    # What it's for, to group it in the apps (repositories/categories.py).
    category: str = categories.DEFAULT
    # It offers email providers (an `email:` section).
    email: bool = False


@dataclass(frozen=True)
class Candidate:
    found: FoundServer
    # The server as written in server.yaml, placeholders and fields not filled in yet.
    template: McpServer
    folder: Path
    # Relative to the repository root.
    path: str
    # The repository's folders of the libraries it uses (folders.library).
    libraries: list[Path] = field(default_factory=list)

    def server(self, values: dict[str, str], url: str) -> McpServer:
        """The server with its placeholders and fields filled in. Raises McpServerError if it needs
        uv and the daemon can't find it."""
        given = {f.key: values.get(f.key, "") for f in self.found.fields}
        t = self.template
        fill = _filler(t.name)
        filled = replace(
            t,
            command=fill(t.command),
            args=[fill(a) for a in t.args],
            env={k: fill(v) for k, v in t.env.items()} | ({} if t.url else given),
            headers=t.headers | (given if t.url else {}),
            page_command=fill(t.page_command),
            page_args=[fill(a) for a in t.page_args],
            channel_command=fill(t.channel_command),
            channel_args=[fill(a) for a in t.channel_args],
            source=url,
        )
        if any("{uv}" in text for text in _commands(filled)):
            raise McpServerError(f"{t.name} runs with uv, and the assistant can't find uv on this computer.")
        return filled


@dataclass(frozen=True)
class ServerValues:
    """A server to install, with the values the user gave for its fields."""

    name: str
    values: dict[str, str] = field(default_factory=dict)


def find(root: Path, url: str) -> dict[str, Candidate]:
    """The repository's servers by name. Raises RepositoryError for a server.yaml that can't work."""
    folders = [root, *subfolders(root), *subfolders(root / "mcp"), *subfolders(root / "plugins")]
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
        if candidate.found.skill and await asyncio.to_thread(_skill_taken, item.name):
            raise McpServerError(f"{item.name} comes with a skill, and you already have a skill named {item.name}.")


async def install(candidate: Candidate, values: dict[str, str], url: str, commit: str) -> McpServer:
    """Copy the server's folder in, make its data folder, and return its settings, filled in. The
    caller saves them."""
    name = candidate.found.name
    server = candidate.server(values, url)
    source = Source(url, candidate.path, commit, version=candidate.found.version)
    await asyncio.to_thread(put, candidate.folder, folders.code(name), source)
    for library in candidate.libraries:
        await asyncio.to_thread(
            put, library, folders.library(library.name), replace(source, path=f"lib/{library.name}")
        )
    await asyncio.to_thread(folders.data(name).mkdir, 0o700, True, True)
    await asyncio.to_thread(_put_skill, candidate, replace(source, server=name))
    return server


async def update(store: BaseStore, name: str) -> McpServer:
    """Install the server again from its repository, keeping the values the user gave and their
    choices (on or off, trusted, tools)."""
    current = await servers.load(store, name)
    source = await asyncio.to_thread(folder_source.read, folders.code(name))
    if not current.source or source is None:
        raise McpServerError(f"{name} wasn't installed from a repository, so there's nothing to update it from.")
    async with checkout(source.url) as (root, commit):
        candidate = await asyncio.to_thread(_find_at, root, source.url, source.path, name)
        values = current.headers if current.url else current.env
        if (missing := _missing(candidate, values)) is not None:
            raise McpServerError(f"The new version of {name} needs {missing.label}: remove it and install it again.")
        new = await install(candidate, values, source.url, commit)
    kept = replace(
        new, enabled=current.enabled, trusted=current.trusted, include=current.include, exclude=current.exclude
    )
    await servers.save(store, kept)
    return kept


def installed_version(name: str) -> str:
    """The version of the server installed here from a repository; "" when it declared none."""
    record = folder_source.read(folders.code(name))
    return record.version if record else ""


def uninstall(name: str) -> None:
    """Delete the server's installed code and its skill, if it has them. Its data stays, for
    installing it again, unless `delete_data` is called too."""
    shutil.rmtree(folders.code(name), ignore_errors=True)
    _remove_skill(name)


def delete_data(name: str) -> None:
    """Delete the server's data folder: what it saved, and its page's socket."""
    shutil.rmtree(folders.data(name), ignore_errors=True)


def _put_skill(candidate: Candidate, source: Source) -> None:
    """Install the server's skill, or remove the one an earlier version had."""
    if candidate.found.skill:
        skills.put(candidate.found.name, candidate.folder, source, only=[SKILL_FILE])
    else:
        _remove_skill(candidate.found.name)


def _remove_skill(name: str) -> None:
    with contextlib.suppress(SkillError):
        if skills.load(name).server == name:
            skills.delete(name, server=name)


def _skill_taken(name: str) -> bool:
    """Another skill has the name the server's skill would get."""
    try:
        return skills.load(name).server != name
    except SkillError:
        return False


def _missing(candidate: Candidate, values: dict[str, str]) -> ServerField | None:
    return next((f for f in candidate.found.fields if not values.get(f.key, "").strip()), None)


def _find_at(root: Path, url: str, path: str, name: str) -> Candidate:
    """The server where it was installed from, or wherever the repository moved it."""
    candidate = _candidate(root, root / path, name)
    if candidate is not None and candidate.found.name == name:
        return candidate
    moved = find(root, url).get(name)
    if moved is None:
        raise McpServerError(f"The repository doesn't have {name} any more.")
    return moved


def _candidate(root: Path, folder: Path, name: str) -> Candidate | None:
    manifest = folder / SERVER_FILE
    if folder.is_symlink() or not manifest.is_file():
        return None
    where = manifest.relative_to(root).as_posix()
    try:
        return _parse(yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}, name, root, folder)
    except (yaml.YAMLError, TypeError, ValueError, McpServerError) as e:
        raise RepositoryError(f"{where} can't be used: {e}") from e


def _parse(data: dict[str, Any], name: str, root: Path, folder: Path) -> Candidate:
    template = _template(data, name)
    servers.validate(template)
    found = _found(data, template, folder)
    libraries = [_library(root, str(n)) for n in data.get("libraries", [])]
    return Candidate(found, template, folder, folder.relative_to(root).as_posix(), libraries)


def _template(data: dict[str, Any], name: str) -> McpServer:
    return McpServer(
        name=str(data.get("name", name)),
        command=str(data.get("command", "")),
        args=[str(a) for a in data.get("args", [])],
        env={str(k): str(v) for k, v in data.get("env", {}).items()},
        url=str(data.get("url", "")),
        headers={str(k): str(v) for k, v in data.get("headers", {}).items()},
        trusted=bool(data.get("trusted", False)),
        include=[str(t) for t in data.get("include", [])],
        exclude=[str(t) for t in data.get("exclude", [])],
        page_command=str(data.get("page", {}).get("command", "")),
        page_args=[str(a) for a in data.get("page", {}).get("args", [])],
        channel_command=str(data.get("channel", {}).get("command", "")),
        channel_args=[str(a) for a in data.get("channel", {}).get("args", [])],
        channel_style=str(data.get("channel", {}).get("style", "")).strip(),
        email_providers=[asdict(p) for p in email_providers.parse(data.get("email"), name)],
    )


def _found(data: dict[str, Any], template: McpServer, folder: Path) -> FoundServer:
    """Raises ValueError for fields, a skill or a category that can't be used."""
    channel, email = bool(template.channel_command), bool(template.email_providers)
    sections = {s for s, has in (("channel", channel), ("email", email)) if has}
    return FoundServer(
        template.name,
        str(data.get("description", "")),
        template.transport,
        [_field(f) for f in data.get("fields", [])],
        template.trusted,
        _check_skill(folder, template.name),
        bool(template.page_command),
        channel,
        version=str(data.get("version", "")),
        category=categories.parse(data.get("category"), sections),
        email=email,
    )


def _library(root: Path, name: str) -> Path:
    """Raises ValueError for a library the repository doesn't have under lib/."""
    folder = root / "lib" / name
    if "/" in name or not valid_path(name) or folder.is_symlink() or not folder.is_dir():
        raise ValueError(f"it uses the library {name!r}, which isn't a folder under lib/")
    return folder


def _commands(server: McpServer) -> list[str]:
    """Everything the server runs, with its arguments."""
    return [
        server.command,
        *server.args,
        server.page_command,
        *server.page_args,
        server.channel_command,
        *server.channel_args,
    ]


def _check_skill(folder: Path, name: str) -> bool:
    """Whether the server comes with a skill. Raises ValueError for one that can't be installed under
    the server's name."""
    skill = skills.read(folder, name) if (folder / SKILL_FILE).is_file() else None
    if skill is None:
        return False
    if skill.name != name or not skills.valid_name(name):
        raise ValueError(f"its SKILL.md must be named {name}, a skill name (lowercase letters, digits, -)")
    if skill.problems:
        raise ValueError(f"its skill has problems: {' '.join(skill.problems)}")
    return True


def _field(data: dict[str, Any]) -> ServerField:
    key = str(data["key"])
    if not _KEY.match(key):
        raise ValueError(f"{key!r} isn't a valid field key")
    return ServerField(key, str(data.get("label", key)), bool(data.get("secret", False)), str(data.get("help", "")))


def _filler(name: str) -> Callable[[str], str]:
    places = {
        "{dir}": str(folders.code(name)),
        "{data}": str(folders.data(name)),
        "{socket}": str(folders.page_socket(name)),
        "{python}": sys.executable,
    }
    if (uv := find_uv()) is not None:
        places["{uv}"] = uv

    def fill(text: str) -> str:
        for placeholder, value in places.items():
            text = text.replace(placeholder, value)
        return text

    return fill
