"""Slack workspace tools: search, read and post as the user, with the user token from /slack.
Posting always needs approval (denied in scheduled runs)."""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from slack_sdk.web.async_client import AsyncWebClient

from assistant.core.config import settings
from assistant.core.context import Context, require_store
from assistant.core.integrations.slack import connection
from assistant.core.integrations.slack.connection import SlackError
from assistant.core.integrations.slack.workspace import Workspace
from assistant.core.skills import store as skills
from assistant.core.tools.approval import ask
from assistant.core.tools.registry import register

_NOT_SET_UP = f"Slack isn't set up. Load the {skills.SETUP} skill and give the user its steps for Slack."


@register("slack")
@tool
async def slack_search(query: str, runtime: ToolRuntime[Context], count: int = 20) -> str:
    """Search messages in the user's Slack workspace, newest first. Slack search syntax works, for
    example `budget in:#finance from:@ana after:2026-09-01`."""
    workspace = await _workspace(runtime)
    if workspace is None:
        return _NOT_SET_UP
    try:
        lines = await workspace.search(query, count)
    except SlackError as e:
        return str(e)
    return "\n\n".join(lines) or "No messages found."


@register("slack")
@tool
async def slack_read(channel: str, runtime: ToolRuntime[Context], thread: str | None = None, limit: int = 30) -> str:
    """Read the latest messages of a Slack channel (a name like #general, or an id), oldest first.
    With `thread` (a message's ts), read that thread's replies instead."""
    workspace = await _workspace(runtime)
    if workspace is None:
        return _NOT_SET_UP
    try:
        lines = await workspace.history(channel, thread, limit)
    except SlackError as e:
        return str(e)
    return "\n\n".join(lines) or "No messages."


@register("slack")
@tool
async def slack_post(channel: str, text: str, runtime: ToolRuntime[Context], thread: str | None = None) -> str:
    """Post a message in Slack as the user, in a channel (a name like #general, or an id), or as a
    reply in `thread` (a message's ts). The user approves every post."""
    workspace = await _workspace(runtime)
    if workspace is None:
        return _NOT_SET_UP
    where = f"{channel} (thread {thread})" if thread else channel
    rejection = ask(
        {"tool": "slack_post", "command": f"In {where}:\n{text}", "reason": f"post in {channel} as you"},
        runtime.context,
    )
    if rejection:
        return rejection
    try:
        return f"Posted: {await workspace.post(channel, text, thread)}"
    except SlackError as e:
        return str(e)


async def _workspace(runtime: ToolRuntime[Context]) -> Workspace | None:
    config = await connection.load(require_store(runtime.store))
    return Workspace(AsyncWebClient(config.user_token), settings.timezone) if config.connected else None
