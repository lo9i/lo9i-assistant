"""Logins of lo9i's that a plugin can use instead of one of its own. `model_login: copilot` in its
server.yaml gives its MCP server the GitHub token of the Copilot model provider (Settings → Model) as
LO9I_COPILOT_GITHUB_TOKEN, so a coding agent plugin runs on the user's Copilot plan with nothing to
enter. The token is added when the hub starts the server, never saved with the plugin, and follows the
model settings: changing them reconnects the servers that use it (McpHub.reload)."""

from collections.abc import Callable
from dataclasses import replace

from assistant.core.i18n import said
from assistant.core.llm.choice import ModelChoice
from assistant.core.mcp.servers import McpServer

# The logins a plugin can ask for, and the env variable each one reaches it in.
ENV = {"copilot": "LO9I_COPILOT_GITHUB_TOKEN"}

# The logins lo9i has now, by kind; empty when the model provider isn't one a plugin can use.
SharedLogins = Callable[[], dict[str, str]]


def parse(value: object) -> str:
    """The login a server.yaml asks for, or "" for none. Raises ValueError for an unknown one."""
    name = str(value or "")
    if name and name not in ENV:
        raise ValueError(said("its model_login {name!r} isn't one of {logins}", name=name, logins=", ".join(ENV)))
    return name


def of_model(model: ModelChoice) -> dict[str, str]:
    """What the model settings can share: the Copilot provider's GitHub token."""
    token = model.values.get("api_key", "") if model.provider == "copilot" else ""
    return {"copilot": token} if token else {}


def with_login(server: McpServer, logins: dict[str, str]) -> McpServer:
    """The server with the login it asks for in its env, when lo9i has it."""
    token = logins.get(server.model_login, "") if server.model_login else ""
    return replace(server, env={**server.env, ENV[server.model_login]: token}) if token else server
