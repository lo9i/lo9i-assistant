"""The offer_plugin tool: the agent offers a plugin from the assistant's extras that does what the
user asked for. Only the user installs it, in an app's dialog that takes any tokens it needs, so
they never pass through the chat or the model; the run waits for that like it waits for an approval
(core/events.py::PLUGIN_OFFER). Chat channels can't show the dialog, so there the agent points the
user to the app instead."""

from dataclasses import asdict
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import interrupt

from assistant.core.context import Context, require_store
from assistant.core.events import PLUGIN_OFFER
from assistant.core.mcp.install import FoundServer
from assistant.core.repositories import offers
from assistant.core.repositories.errors import RepositoryError
from assistant.core.tools.registry import register

# The apps, which show the install dialog.
_APPS = {"cli", "web"}
_IN_THE_APP = "Settings → Plugins in the web app, or /plugins in the terminal app"
_CHANNELS = "/channels in the terminal app, Settings → Accounts → Channels in the web app"


@register("skills")
@tool
async def offer_plugin(name: str, runtime: ToolRuntime[Context]) -> str:
    """Offer to install a plugin from the assistant's extras (see Plugins you can offer) that does
    what the user asked for, such as telegram for messages on Telegram. The user sees what it is and
    installs it, entering any tokens in the app; wait for their answer, then help with what's left."""
    store = require_store(runtime.store)
    try:
        plugin = await offers.find(store, name)
    except RepositoryError as e:
        return f"The extras can't be read right now: {e}"
    if plugin is None:
        return f"The extras have no plugin named {name}. They have: {', '.join(await offers.names(store)) or 'none'}."
    # Also how a resumed run ends once the user installed it: the tool runs again from the start.
    if plugin.installed:
        return f"{name} is installed.{_next_steps(plugin)}"
    if runtime.context.channel not in _APPS:
        channel = runtime.context.channel
        return f"Not offered: {channel} can't show the install. Ask the user to install {name} from {_IN_THE_APP}."
    interrupt(_request(plugin))
    return f"The user didn't install {name}."


def _request(plugin: Any) -> dict[str, Any]:
    kind = "server" if isinstance(plugin, FoundServer) else "skill"
    return {"kind": PLUGIN_OFFER, "name": plugin.name, "description": plugin.description, kind: asdict(plugin)}


def _next_steps(plugin: Any) -> str:
    if isinstance(plugin, FoundServer) and plugin.channel:
        return f" Its setup (such as a pairing code) shows in Channels: {_CHANNELS}."
    if isinstance(plugin, FoundServer):
        return " Its tools are there from the user's next message."
    return ""
