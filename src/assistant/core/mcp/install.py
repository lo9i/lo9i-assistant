"""MCP servers in a downloaded repository: finding them, installing them, and updating one later.

A server is a folder with a `server.yaml`, at the repository's root, in its folders, or in a
category's folder (`communications/telegram`, repositories/categories.py), which gives its category.
A `SKILL.md` next to it is the server's skill: how to use its tools. It's installed, updated and
removed with the server, under the server's name.

The folder is copied to `settings.mcp_dir/<name>` (core/mcp/folders.py), so a local server can run
code from it. In its commands, arguments and env values:

- `{dir}`: that folder. Updates replace it.
- `{data}`: a folder for its data, only the user's. Updates and removing the server keep it.
- `{socket}`: where its page listens, in `{data}`.
- `{bin}`: the scripts of its own Python environment, built with uv from its uv.lock when it's installed
  or updated (core/mcp/environment.py): `{bin}/my-server` runs as one process.
- `{uv}`: the uv the daemon found.
- `{python}`: the daemon's Python, for servers that need nothing beyond it.

    name: dav
    description: Calendar and contacts over CalDAV and CardDAV
    command: "{python}"            # or url: https://… for a remote server
    args: ["{dir}/server.py"]
    env: {CALDAV_URL: https://caldav.icloud.com}
    fields:                        # asked for when it's installed: env values, or headers for a URL
      - {key: DAV_USER, label: Apple ID}
      - {key: DAV_PASSWORD, label: App-specific password, secret: true, help: https://account.apple.com}
      - {key: DAV_CALENDAR, label: Calendar name, optional: true}   # may be left empty
    trusted: false
    include: []                    # tools the agent gets; empty means all but `exclude`
    exclude: []
    approve: [download]            # optional, format 5: tools that ask the user before each call, even on a
                                   # trusted server (names or globs); an update replaces them
    page:                          # optional: a web page, shown in the web app (core/mcp/pages.py); its
                                   # WebSockets pass through too, with no time limit (daemon/page_sockets.py);
                                   # it's told the app's theme: ?theme=light|dark on its first address, and a
                                   # {"type": "lo9i:theme", "theme"} message from its frame's parent on a change
      command: "{bin}/my-page"
      args: [--socket, "{socket}"]
    channel:                       # optional: a chat channel (core/channels/), with or without `command`
      command: "{bin}/my-channel"
      style: A phone chat. Short messages.   # how to write there, for the system prompt
      protocol: 2                  # the channel protocol it speaks (docs/channel-plugins.md); 1 if absent
    model_login: copilot           # optional: a login of lo9i's its server gets instead of its own (logins.py)
    ssh_agent: true                # optional: its processes get the user's ssh agent (ssh_agent.py)
    data_key: true                 # optional, format 4: a random key of its own, made when it's installed and
                                   # kept encrypted by lo9i (also when it's removed, with its data), that its
                                   # processes get in LO9I_DATA_KEY to encrypt what they keep in {data} (data_key.py)
    agent:                         # optional: a coding agent (docs/agent-plugins.md, core/agent_tasks/)
      command: claude              # /claude <folder> hands a conversation to it, /claude off back
      name: Claude Code
      worker: "{bin}/my-worker"    # run for each task, with the task's folder as its last argument
      args: []
    platforms: [macos]             # optional: the systems it runs on (repositories/platforms.py); all if absent
    format: 2                      # the plugin format it's written in (repositories/formats.py); 1 if absent
    category: communications       # outside a category's folder: what it's for (repositories/categories.py)
    icon: tv                       # optional: a Lucide icon's name, or an .svg file in its folder
                                   # (repositories/icons.py); its category's icon if absent
    steps:                         # optional: how to get what it asks for, shown when installing
      - In your provider's settings, create an app password.
    email:                         # optional: email providers it offers (core/integrations/email/providers.py)
      - {id: gmail, name: Gmail, host: smtp.gmail.com, port: 587, imap_host: imap.gmail.com,
         password_help: Gmail needs an app password., password_url: https://myaccount.google.com/apppasswords}
"""

import asyncio
import contextlib
import logging
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
from assistant.core.mcp import data_key, environment, folders, keys, logins, servers, ssh_agent
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.repositories import categories, formats, icons, platforms
from assistant.core.repositories import source as folder_source
from assistant.core.repositories.checkout import checkout, default_name
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.folders import SERVER_FILE, SKILL_FILE, put, subfolders
from assistant.core.repositories.source import Source
from assistant.core.secret_store import SecretBox
from assistant.core.skills import store as skills
from assistant.core.skills.errors import SkillError
from assistant.core.uv import find as find_uv

logger = logging.getLogger(__name__)

_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_COMMAND = re.compile(r"^[a-z][a-z0-9-]{1,23}$")


@dataclass(frozen=True)
class ServerField:
    """A value the user gives when installing: an env value of a local server, a header of a remote one."""

    key: str
    label: str
    secret: bool = False
    # Where to get it, such as a page that creates the password.
    help: str = ""
    # It may be left empty.
    optional: bool = False


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
    # How to get what it asks for, one step each (`steps:`), shown in the install dialogs.
    steps: list[str] = field(default_factory=list)
    # A login of lo9i's its server uses instead of one of its own, like "copilot" (core/mcp/logins.py),
    # for the install dialogs to say; "" for none.
    model_login: str = ""
    # The command of the agent it adds, like "claude" for /claude (core/conversation/handoffs.py); "" for none.
    agent: str = ""
    # Its processes get the user's ssh agent (core/mcp/ssh_agent.py), for the install dialogs to say.
    ssh_agent: bool = False
    # What the apps show beside it (repositories/icons.py).
    icon: icons.PluginIcon = field(default_factory=icons.PluginIcon)


@dataclass(frozen=True)
class Candidate:
    found: FoundServer
    # The server as written in server.yaml, placeholders and fields not filled in yet.
    template: McpServer
    folder: Path
    # Relative to the repository root.
    path: str
    # The systems it runs on; empty for all (repositories/platforms.py).
    platforms: list[str] = field(default_factory=list)
    # The plugin format it's written in (repositories/formats.py).
    format: int = 1

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
            agent_worker=fill(t.agent_worker),
            agent_args=[fill(a) for a in t.agent_args],
            source=url,
            keys=sorted(given),
            icon=asdict(self.found.icon),
        )
        if any("{uv}" in text for text in _commands(filled)) or (self.needs_environment and find_uv() is None):
            raise McpServerError(f"{t.name} runs with uv, and the assistant can't find uv on this computer.")
        return filled

    @property
    def usable_here(self) -> bool:
        """It runs on this system, and this daemon reads its format."""
        return platforms.runs_here(self.platforms) and formats.readable(self.format)

    @property
    def needs_environment(self) -> bool:
        """It runs scripts of its own environment, which installing builds."""
        return any(environment.PLACEHOLDER in text for text in _commands(self.template))


@dataclass(frozen=True)
class ServerValues:
    """A server to install, with the values the user gave for its fields."""

    name: str
    values: dict[str, str] = field(default_factory=dict)


def find(root: Path, url: str) -> tuple[dict[str, Candidate], list[str]]:
    """The repository's servers that run on this system, by name, and what's wrong with each server.yaml
    that can't work, on any system: that one is left out, never the rest of the repository."""
    folders = [root, *subfolders(root), *categories.plugin_folders(root)]
    found: list[Candidate] = []
    problems: list[str] = []
    for folder in folders:
        try:
            candidate = _candidate(root, folder, default_name(url) if folder == root else folder.name)
        except RepositoryError as e:
            problems.append(str(e))
            continue
        if candidate is not None and candidate.usable_here:
            found.append(candidate)
    return {c.found.name: c for c in found}, problems


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
    if candidate.needs_environment:
        await environment.build(name, folders.code(name))
    await asyncio.to_thread(folders.data(name).mkdir, 0o700, True, True)
    await asyncio.to_thread(_put_skill, candidate, replace(source, server=name))
    return server


async def update(store: BaseStore, box: SecretBox, name: str, tokens: dict[str, str] | None = None) -> McpServer:
    """Install the server again from its repository, keeping the values the user gave (its keys) and
    their choices (on or off, trusted, tools). `tokens`: private repositories' tokens, by address."""
    current = await keys.fill(store, box, await servers.load(store, name))
    source = await asyncio.to_thread(folder_source.read, folders.code(name))
    if not current.source or source is None:
        raise McpServerError(f"{name} wasn't installed from a repository, so there's nothing to update it from.")
    async with checkout(source.url, (tokens or {}).get(source.url, "")) as (root, commit):
        candidate = await asyncio.to_thread(_find_at, root, source.url, source.path, name)
        values = current.headers if current.url else current.env
        if (missing := _missing(candidate, values)) is not None:
            raise McpServerError(f"The new version of {name} needs {missing.label}: remove it and install it again.")
        new = await install(candidate, values, source.url, commit)
    kept = replace(
        new, enabled=current.enabled, trusted=current.trusted, include=current.include, exclude=current.exclude
    )
    await data_key.ensure(store, box, kept)
    await keys.save(store, box, kept)
    return kept


def installed_version(name: str) -> str:
    """The version of the server installed here from a repository; "" when it declared none."""
    record = folder_source.read(folders.code(name))
    return record.version if record else ""


async def add_missing_icons(store: BaseStore) -> None:
    """Give servers installed before icons existed the icon their installed folder declares, so the apps
    stop showing the generic one before their next update. Run at start; once a record has its icon,
    it's left alone. Only the icon is written, so their keys aren't read; a folder that can't be read is
    logged and its server left without one, which never stops the start."""
    for server in await servers.load_all(store):
        if not server.source or server.icon:
            continue
        icon = await asyncio.to_thread(_readable_icon, server.name)
        if icon is not None:
            await servers.set_icon(store, server.name, asdict(icon))


def _readable_icon(name: str) -> icons.PluginIcon | None:
    try:
        return installed_icon(name)
    except (OSError, yaml.YAMLError, ValueError) as e:
        logger.warning("Couldn't read the icon %s's folder declares: %s", name, e)
        return None


def installed_icon(name: str) -> icons.PluginIcon | None:
    """The icon the server installed here declares in its folder, or its category's; None when its folder
    or its server.yaml can't say."""
    folder = folders.code(name)
    source = folder_source.read(folder)
    manifest = folder / SERVER_FILE
    if source is None or not manifest.is_file():
        return None
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        category = _category(data, _template(data, name), categories.of_path(source.path))
        return icons.or_category(icons.parse(data.get("icon"), folder), category)
    except (yaml.YAMLError, TypeError, ValueError, McpServerError):
        return None


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
    return next((f for f in candidate.found.fields if not f.optional and not values.get(f.key, "").strip()), None)


def _find_at(root: Path, url: str, path: str, name: str) -> Candidate:
    """The server where it was installed from, or wherever the repository moved it."""
    candidate = _candidate(root, root / path, name)
    if candidate is not None and candidate.found.name == name:
        if not platforms.runs_here(candidate.platforms):
            raise McpServerError(f"The new version of {name} doesn't run on {platforms.current()}.")
        if not formats.readable(candidate.format):
            raise McpServerError(f"The new version of {name} needs a newer lo9i: update the assistant first.")
        return candidate
    moved = find(root, url)[0].get(name)
    if moved is None:
        raise McpServerError(f"The repository doesn't have {name} any more.")
    return moved


def read(root: Path, folder: Path) -> Candidate | None:
    """The server in a repository's folder, named after it, or None when it has no server.yaml. Raises
    RepositoryError for one that can't work, on any system."""
    return _candidate(root, folder, folder.name)


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
    found = _found(data, template, folder, categories.of_folder(root, folder))
    if "libraries" in data:
        raise ValueError("it uses libraries:, which lo9i doesn't install: a plugin has all its code in its folder")
    systems = platforms.parse(data.get("platforms"))
    version = formats.parse(data.get("format"))
    if version < 2 and any(environment.PLACEHOLDER in text for text in _commands(template)):
        raise ValueError(f"it uses {environment.PLACEHOLDER}, which needs format: 2")
    if version < 3 and template.agent_worker:
        raise ValueError("its agent section has a worker, which needs format: 3")
    if version < 4 and template.data_key:
        raise ValueError("it asks for a data_key, which needs format: 4")
    if version < 5 and template.approve:
        raise ValueError("it has tools that ask first (approve:), which needs format: 5")
    return Candidate(found, template, folder, folder.relative_to(root).as_posix(), systems, version)


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
        approve=_tool_patterns(data.get("approve", [])),
        page_command=str(data.get("page", {}).get("command", "")),
        page_args=[str(a) for a in data.get("page", {}).get("args", [])],
        channel_command=str(data.get("channel", {}).get("command", "")),
        channel_args=[str(a) for a in data.get("channel", {}).get("args", [])],
        channel_style=str(data.get("channel", {}).get("style", "")).strip(),
        channel_protocol=_channel_protocol(data.get("channel", {}).get("protocol")),
        email_providers=[asdict(p) for p in email_providers.parse(data.get("email"), name)],
        model_login=logins.parse(data.get("model_login")),
        ssh_agent=ssh_agent.parse(data.get("ssh_agent")),
        data_key=data_key.parse(data.get("data_key")),
        **_agent(data.get("agent")),
    )


def _tool_patterns(value: object) -> list[str]:
    """Raises ValueError for anything but a list of tool names: a lone name is refused, not read letter by
    letter, since a tool left out of `approve` would run without asking."""
    if not isinstance(value, list) or not all(isinstance(t, str) and t.strip() for t in value):
        raise ValueError("its approve must be a list of tool names")
    return [t.strip() for t in value]


def _found(data: dict[str, Any], template: McpServer, folder: Path, category_folder: str) -> FoundServer:
    """Raises ValueError for fields, a skill or a category that can't be used."""
    channel, email = bool(template.channel_command), bool(template.email_providers)
    category = _category(data, template, category_folder)
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
        category=category,
        email=email,
        steps=[str(s).strip() for s in data.get("steps", []) if str(s).strip()],
        model_login=template.model_login,
        agent=template.agent_command,
        ssh_agent=template.ssh_agent,
        icon=icons.or_category(icons.parse(data.get("icon"), folder), category),
    )


def _category(data: dict[str, Any], template: McpServer, category_folder: str) -> str:
    """Raises ValueError for a category that isn't in the list or that its sections don't allow."""
    has = {"channel": bool(template.channel_command), "email": bool(template.email_providers)}
    return categories.parse(data.get("category"), {s for s, present in has.items() if present}, category_folder)


def _channel_protocol(value: object) -> int:
    """Raises ValueError for anything but a whole number from 1."""
    if value is None:
        return 1
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("its channel protocol must be a whole number from 1")
    return value


def _commands(server: McpServer) -> list[str]:
    """Everything the server runs, with its arguments."""
    return [
        server.command,
        *server.args,
        server.page_command,
        *server.page_args,
        server.channel_command,
        *server.channel_args,
        server.agent_worker,
        *server.agent_args,
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


def _agent(section: object) -> dict[str, Any]:
    """The `agent:` section as the server's fields; none without it. Raises ValueError for one missing a
    part or with a command the apps can't offer."""
    if not section:
        return {}
    if not isinstance(section, dict):
        raise ValueError(_AGENT_PARTS)
    parts = {key: str(section.get(key) or "").strip() for key in ("command", "name", "worker")}
    if not all(parts.values()):
        raise ValueError(_AGENT_PARTS)
    if not _COMMAND.match(parts["command"]):
        raise ValueError(f"its agent command {parts['command']!r} must be a lowercase word, like claude")
    args = [str(a) for a in section.get("args", [])]
    return {
        "agent_command": parts["command"],
        "agent_name": parts["name"],
        "agent_worker": parts["worker"],
        "agent_args": args,
    }


_AGENT_PARTS = "its agent section must have command, name and worker"


def _field(data: dict[str, Any]) -> ServerField:
    key = str(data["key"])
    if not _KEY.match(key):
        raise ValueError(f"{key!r} isn't a valid field key")
    label, help_url = str(data.get("label", key)), str(data.get("help", ""))
    return ServerField(key, label, bool(data.get("secret", False)), help_url, bool(data.get("optional", False)))


def _filler(name: str) -> Callable[[str], str]:
    places = {
        "{dir}": str(folders.code(name)),
        "{data}": str(folders.data(name)),
        "{socket}": str(folders.page_socket(name)),
        "{python}": sys.executable,
        environment.PLACEHOLDER: str(environment.scripts(folders.code(name))),
    }
    if (uv := find_uv()) is not None:
        places["{uv}"] = uv

    def fill(text: str) -> str:
        for placeholder, value in places.items():
            text = text.replace(placeholder, value)
        return text

    return fill
