"""The offer_plugin tool: the agent offers a plugin from the assistant's extras that does what the
user asked for. Only the user installs it, in an app's dialog that takes any tokens it needs, so
they never pass through the chat or the model; the run waits for that like it waits for an approval
(core/events.py::PLUGIN_OFFER). Right after, the app goes on to the plugin's setup (its email
accounts, a channel's pairing), which open_plugin_setup opens again later (PLUGIN_SETUP). Chat
channels can't show either, so there the agent points the user to the app instead."""

from dataclasses import asdict
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.store.base import BaseStore
from langgraph.types import interrupt

from assistant.core.context import Context, require_store
from assistant.core.events import PLUGIN_OFFER, PLUGIN_SETUP
from assistant.core.integrations.email import accounts as email_accounts
from assistant.core.mcp.install import FoundServer
from assistant.core.repositories import offers
from assistant.core.repositories.errors import RepositoryError
from assistant.core.tools.registry import register

# The apps, which show the install dialog.
_APPS = {"cli", "web"}
_IN_THE_APP = "Settings → Plugins in the web app, or /plugins in the terminal app"


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


@register("skills")
@tool
async def open_plugin_setup(name: str, runtime: ToolRuntime[Context]) -> str:
    """Open an installed plugin's setup right here in the conversation: an email plugin's accounts
    (add one, change a sign-in), a chat channel's pairing. Use it instead of sending the user to
    Plugins. The user's passwords and tokens are typed in the app, never in the chat."""
    store = require_store(runtime.store)
    try:
        plugin = await offers.find(store, name)
    except RepositoryError as e:
        return f"The extras can't be read right now: {e}"
    if not isinstance(plugin, FoundServer) or not plugin.installed:
        return f"{name} isn't an installed plugin. Offer it with offer_plugin first."
    if not (plugin.email or plugin.channel):
        return f"{name} has nothing to set up here.{_next_steps(plugin)}"
    if runtime.context.channel not in _APPS:
        return f"Not opened: {runtime.context.channel} can't show it. Ask the user to open {name} in {_IN_THE_APP}."
    interrupt({"kind": PLUGIN_SETUP, "name": name, "description": plugin.description, "server": asdict(plugin)})
    return await _setup_state(store, plugin)


def _request(plugin: Any) -> dict[str, Any]:
    kind = "server" if isinstance(plugin, FoundServer) else "skill"
    return {"kind": PLUGIN_OFFER, "name": plugin.name, "description": plugin.description, kind: asdict(plugin)}


async def _setup_state(store: BaseStore, plugin: FoundServer) -> str:
    """What the setup left, for the model to go on from."""
    if not plugin.email:
        return f"The user closed {plugin.name}'s setup. Ask them whether pairing worked if it matters."
    mine = [a.handle for a in await email_accounts.plugin_accounts(store, plugin.name)]
    listed = ", ".join(mine) if mine else "none yet"
    return f"The user closed {plugin.name}'s setup. Its email accounts: {listed}."


def _next_steps(plugin: Any) -> str:
    if isinstance(plugin, FoundServer) and (plugin.channel or plugin.email):
        # After an install from the chat the app has just shown the setup, so only offer it again.
        return " If it isn't set up yet (email accounts, a channel's pairing), open_plugin_setup opens it here."
    if isinstance(plugin, FoundServer):
        return " Its tools are there from the user's next message."
    return ""
