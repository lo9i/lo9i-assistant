"""Where the briefing and the nightly review look: the read-only tools of the extras' plugins that hold the user's day
(PLUGINS) and their mail while an account can be read (search_email). A plugin not installed, turned off or not
connected has no tools, so its part is left out of what's asked, and so is mail without an account: nothing is asked
of a source the user doesn't have."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.store.base import BaseStore

from assistant.core.integrations.email import accounts
from assistant.core.proactive.writing import MAIL_TOOLS

PLUGINS = ("calendar", "expenses", "billing")
MAIL = "mail"


class ReadOnlyTools(Protocol):
    """The plugins' tools that only read (core/plugin_tools.py)."""

    def read_only_definitions(self) -> list[dict[str, Any]]: ...

    def plugin_of(self, name: str) -> str | None: ...


@dataclass(frozen=True)
class Sources:
    # The definitions of the tools gathering is offered.
    tools: list[dict[str, Any]]
    # The plugins in PLUGINS that have tools, and MAIL while an account can be read.
    names: list[str]
    # The accounts that can be read, as "label <address>".
    accounts: list[str]


async def available(store: BaseStore, tools: ReadOnlyTools) -> Sources:
    plugins = [d for d in tools.read_only_definitions() if tools.plugin_of(d["function"]["name"]) in PLUGINS]
    names = sorted({p for d in plugins if (p := tools.plugin_of(d["function"]["name"]))})
    readable = [f"{c.label} <{c.sender}>" for c in await accounts.list_accounts(store) if c.can_read]
    if not readable:
        return Sources(plugins, names, [])
    return Sources([*plugins, *(convert_to_openai_tool(t) for t in MAIL_TOOLS)], [*names, MAIL], readable)


def asked(sources: Sources, asks: Mapping[str, str], **values: str) -> str:
    """What gathering is asked: a line for each source, mail last."""
    lines = [asks[name].format(accounts=", ".join(sources.accounts), **values) for name in sources.names]
    return "\n".join(f"- {line}" for line in lines)
