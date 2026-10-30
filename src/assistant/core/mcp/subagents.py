"""Named subagents plugins bring: `subagent:` in a server.yaml (format 6) gives one a name, what it's for, its
own instructions, the model it runs on and the tools it gets, and the assistant hands it tasks with
`delegate(task, agent=<name>)` (core/tools/delegate.py, core/subagent.py). It runs nothing of its own.

    subagent:
      name: researcher                 # what delegate's `agent` takes: a lowercase word
      description: Researches a question across many web pages and answers with its sources.
      prompt: prompt.md                # its instructions, a file in the plugin's folder
      model: worker                    # worker (default) or main: which of the user's models; or a model id
      tools: [web_search, web_extract] # the assistant's tools it gets, of those subagents may; all when absent
      plugins: [maps]                  # plugins whose read-only tools it gets besides the conversation's

Whatever it says, a named subagent gets only what any subagent may: tools that don't talk to the user, send,
schedule or save, and plugins' read-only tools."""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.store.base import BaseStore

from assistant.core.mcp import folders, servers

_NAME = re.compile(r"^[a-z][a-z0-9-]{1,23}$")


class UnknownSubagentError(Exception):
    """No installed plugin brings a subagent by that name; the text lists those there are."""


@dataclass(frozen=True)
class NamedSubagent:
    name: str
    description: str
    # Its instructions, read from its plugin's folder.
    prompt: str
    # main, worker, or a model id of the user's provider.
    model: str
    # The assistant's tools it gets, by name; empty for every one a subagent may use.
    tools: tuple[str, ...]
    # Plugins whose read-only tools it gets besides the conversation's.
    plugins: tuple[str, ...]
    # The plugin it came with.
    plugin: str


def parse(section: object, folder: Path) -> dict[str, Any]:
    """The `subagent:` section as the server's fields; none without one. Raises ValueError for one that can't be
    used: a missing part, a name the model can't type, a prompt that isn't a file in `folder`."""
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ValueError("its subagent must be a section with a name, a description and a prompt")
    name, description, prompt = (str(section.get(k) or "").strip() for k in ("name", "description", "prompt"))
    if not (name and description and prompt):
        raise ValueError("its subagent needs a name, a description and a prompt")
    if not _NAME.match(name):
        raise ValueError(f"its subagent name {name!r} must be a lowercase word, like researcher")
    if not _inside(folder, prompt):
        raise ValueError(f"its subagent prompt {prompt!r} isn't a file in its folder")
    tools, plugins = section.get("tools", []), section.get("plugins", [])
    if not _names(tools) or not _names(plugins):
        raise ValueError("its subagent's tools and plugins must be lists of names")
    return {
        "subagent_name": name,
        "subagent_description": " ".join(description.split()),
        "subagent_prompt": prompt,
        "subagent_model": str(section.get("model") or "worker").strip(),
        "subagent_tools": [str(t) for t in tools],
        "subagent_plugins": [str(p) for p in plugins],
    }


async def installed(store: BaseStore) -> list[NamedSubagent]:
    """The named subagents of the plugins installed and on, by name; one whose prompt can't be read is left out."""
    found = []
    for server in await servers.load_all(store):
        if not (server.subagent_name and server.enabled):
            continue
        if prompt := await asyncio.to_thread(_prompt, server.name, server.subagent_prompt):
            found.append(
                NamedSubagent(
                    server.subagent_name,
                    server.subagent_description,
                    prompt,
                    server.subagent_model,
                    tuple(server.subagent_tools),
                    tuple(server.subagent_plugins),
                    server.name,
                )
            )
    return sorted(found, key=lambda s: s.name)


def _prompt(plugin: str, path: str) -> str:
    folder = folders.code(plugin)
    if not _inside(folder, path):
        return ""
    return (folder / path).read_text(encoding="utf-8").strip()


def _inside(folder: Path, path: str) -> bool:
    """A file in `folder`, never outside it."""
    file = (folder / path).resolve()
    return file.is_file() and file.is_relative_to(folder.resolve())


def _names(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)
