"""The offer_plugin tool: the agent offers a plugin from the assistant's extras that does what the
user asked for. Only the user installs it, in an app's dialog that takes any tokens it needs, so
they never pass through the chat or the model; the run waits for that like it waits for an approval
(core/events.py::PLUGIN_OFFER). Right after, the app goes on to the plugin's setup (its email
accounts, a channel's pairing, signing in), which open_plugin_setup opens again later (PLUGIN_SETUP), with its
settings (the values its fields were given). Chat
channels can't show either, so there the agent points the user to the app instead."""

from dataclasses import asdict
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.store.base import BaseStore
from langgraph.types import interrupt

from assistant.core import i18n
from assistant.core.context import Context, require_secrets, require_store
from assistant.core.events import PLUGIN_OFFER, PLUGIN_SETUP, QUESTION
from assistant.core.integrations.email import accounts as email_accounts
from assistant.core.mcp import plugin_oauth, plugin_settings, servers
from assistant.core.mcp.install import FoundServer, ServerValues, in_language
from assistant.core.mcp.servers import McpServerError
from assistant.core.repositories import contents, offers
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.known import EXTRAS
from assistant.core.secret_store import SecretBox
from assistant.core.tools.registry import register

# The apps, which show the install dialog.
_APPS = {"cli", "web"}
_IN_THE_APP = "Settings → Plugins in the web app, or /plugins in the terminal app"
# How long offer_plugin waits for a server the user just installed. Its first start builds its environment.
_START_SECONDS = 120


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
        return f"{name} is installed.{await _next_steps(plugin, runtime.context)}"
    if runtime.context.channel not in _APPS:
        channel = runtime.context.channel
        return f"Not offered: {channel} can't show the install. Ask the user to install {name} from {_IN_THE_APP}."
    interrupt(_request(await _shown(store, plugin)))
    return f"The user didn't install {name}."


@register("skills")
@tool
async def open_plugin_setup(name: str, runtime: ToolRuntime[Context]) -> str:
    """Open an installed plugin's setup right here in the conversation: an email plugin's accounts
    (add one, change a sign-in), a chat channel's pairing, a plugin's sign-in (Google), and its settings
    (a new token, another account for what it asked for when installed). Use it instead of sending the
    user to Plugins. The user's passwords and tokens are typed in the app, never in the chat."""
    store = require_store(runtime.store)
    try:
        plugin = await offers.find(store, name)
    except RepositoryError as e:
        return f"The extras can't be read right now: {e}"
    if not isinstance(plugin, FoundServer) or not plugin.installed:
        return f"{name} isn't an installed plugin. Offer it with offer_plugin first."
    if not await _has_setup(store, plugin):
        return f"{name} has nothing to set up here.{await _next_steps(plugin, runtime.context)}"
    if runtime.context.channel not in _APPS:
        return f"Not opened: {runtime.context.channel} can't show it. Ask the user to open {name} in {_IN_THE_APP}."
    shown = await _shown(store, plugin)
    interrupt({"kind": PLUGIN_SETUP, "name": name, "description": shown.description, "server": asdict(shown)})
    return await _setup_state(store, require_secrets(runtime.context), plugin)


async def _shown[T](store: BaseStore, plugin: T) -> T:
    """A server's description, steps and fields in the language chosen, for the apps' dialog."""
    if not isinstance(plugin, FoundServer):
        return plugin
    return in_language(plugin, (await i18n.chosen(store)).language)


def _request(plugin: Any) -> dict[str, Any]:
    kind = "server" if isinstance(plugin, FoundServer) else "skill"
    return {"kind": PLUGIN_OFFER, "name": plugin.name, "description": plugin.description, kind: asdict(plugin)}


@register("email", group="email")
@tool
async def set_up_email(runtime: ToolRuntime[Context]) -> str:
    """Set up the user's email when no account is connected (or they want one with another
    provider): asks which provider their account is with, installs that mail provider's plugin, and
    opens its accounts here for the user to connect. Passwords are typed in the app, never in the chat."""
    store = require_store(runtime.store)
    if runtime.context.channel not in _APPS:
        return f"Not here: {runtime.context.channel} can't show it. Ask the user to set up email in {_IN_THE_APP}."
    try:
        providers = {_provider_label(p): p for p in await offers.email_providers(store)}
    except RepositoryError as e:
        return f"The extras can't be read right now: {e}"
    plugin = providers.get(_picked(interrupt(_provider_question(list(providers)))))
    if plugin is None:
        return "The user didn't pick a provider."
    # The tool runs again from the start once the setup closes, so it installs only the first time.
    if not plugin.installed:
        if not _runs_nothing(plugin):
            return f"{plugin.name} runs code on this computer: offer it with offer_plugin instead."
        await contents.install(store, require_secrets(runtime.context), EXTRAS, [], [ServerValues(plugin.name)])
    shown = await _shown(store, plugin)
    server = asdict(shown) | {"installed": True}
    interrupt({"kind": PLUGIN_SETUP, "name": plugin.name, "description": shown.description, "server": server})
    return await _setup_state(store, require_secrets(runtime.context), plugin)


def _provider_question(options: list[str]) -> dict[str, Any]:
    return {"kind": QUESTION, "question": "Which email provider is your account with?", "options": options}


def _picked(answer: Any) -> str:
    choices = answer.get("choices") if isinstance(answer, dict) else None
    return choices[0] if choices else ""


def _provider_label(plugin: FoundServer) -> str:
    """ "Gmail" from "Send and read Gmail"; "Mail on any other server" for the custom one."""
    text = plugin.description.removeprefix("Send and read ").split(",")[0].strip() or plugin.name
    return text[:1].upper() + text[1:]


def _runs_nothing(plugin: FoundServer) -> bool:
    """A mail provider plugin only holds presets: no tools, page or channel run. Picking it in the
    question is the user's say-so; anything that runs code is installed only from its dialog."""
    return plugin.transport == "none" and not (plugin.page or plugin.channel or plugin.skill)


async def _has_setup(store: BaseStore, plugin: FoundServer) -> bool:
    """Email accounts, a channel's pairing, signing in, or settings: fields of its own, as installed."""
    if plugin.email or plugin.channel or plugin.oauth:
        return True
    try:
        return plugin_settings.has_settings(await servers.load(store, plugin.name))
    except McpServerError:
        return False


async def _setup_state(store: BaseStore, box: SecretBox, plugin: FoundServer) -> str:
    """What the setup left, for the model to go on from."""
    if plugin.oauth:
        login = await plugin_oauth.login(store, box, plugin.name)
        provider = plugin_oauth.PROVIDERS[plugin.oauth].name
        if login is None:
            return f"The user closed {plugin.name}'s setup without signing in to {provider}."
        return f"The user closed {plugin.name}'s setup, signed in to {provider} as {login.account or 'their account'}."
    if plugin.email:
        mine = [a.handle for a in await email_accounts.plugin_accounts(store, plugin.name)]
        listed = ", ".join(mine) if mine else "none yet"
        return f"The user closed {plugin.name}'s setup. Its email accounts: {listed}."
    if plugin.channel:
        return f"The user closed {plugin.name}'s setup. Ask them whether pairing worked if it matters."
    return f"The user closed {plugin.name}'s setup. Settings they saved apply now."


async def _next_steps(plugin: Any, context: Context) -> str:
    if isinstance(plugin, FoundServer) and (plugin.channel or plugin.email):
        # After an install from the chat the app has just shown the setup, so only offer it again.
        return " If it isn't set up yet (email accounts, a channel's pairing), open_plugin_setup opens it here."
    if not isinstance(plugin, FoundServer):
        return ""
    if plugin.oauth:
        # Its tools work once it's signed in, which its setup does.
        signing_in = " If it isn't signed in yet, open_plugin_setup opens its sign-in here."
        return signing_in + await _tools_ready(plugin, context)
    if plugin.agent and plugin.transport == "none":
        # Its task tools come right after this call, like a server's (graph.py, _installed_node).
        return f" Its coding agent is ready: start_task hands it tasks, and /{plugin.agent} hands it a conversation."
    return await _tools_ready(plugin, context)


async def _tools_ready(plugin: FoundServer, context: Context) -> str:
    status = await context.mcp.started(plugin.name, _START_SECONDS) if context.mcp else "off"
    # Once it's connected, the graph gives this run its tools after this call (graph.py, _installed_node).
    if status in ("connected", "idle"):
        return " Its tools are available now."
    if status in ("connecting", "failed"):
        return " It's still starting (the first start sets it up); its tools are there from the user's next message."
    return " Its tools are there from the user's next message."
