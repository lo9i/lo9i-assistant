"""Slack connection settings, stored as one Store record, and the checks that set them up.

One Slack app, created from `manifest`, gives three tokens: the app token opens the Socket Mode
connection (no public URL needed), the bot token chats in DMs, and the user token reads and posts in
the workspace as the user. The user token's owner is the only person the bot answers.
"""

import json
from dataclasses import asdict, dataclass

from langgraph.store.base import BaseStore
from slack_sdk.errors import SlackApiError, SlackClientError
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.web.async_slack_response import AsyncSlackResponse

_NAMESPACE = ("integrations",)
_KEY = "slack"

_BOT_SCOPES = ["chat:write", "commands", "files:read", "im:history", "im:read", "users:read"]
_USER_SCOPES = [
    "channels:history",
    "channels:read",
    "chat:write",
    "groups:history",
    "groups:read",
    "im:history",
    "im:read",
    "mpim:history",
    "mpim:read",
    "search:read",
    "users:read",
]


class SlackError(Exception):
    """A token was rejected or Slack couldn't be reached. The text says which and why."""


@dataclass
class SlackConfig:
    app_token: str = ""
    bot_token: str = ""
    user_token: str = ""
    team: str = ""
    # The Slack user who installed the app: the only one the bot answers.
    owner_id: str = ""
    owner_name: str = ""

    @property
    def connected(self) -> bool:
        return bool(self.app_token and self.bot_token and self.user_token)


async def load(store: BaseStore) -> SlackConfig:
    item = await store.aget(_NAMESPACE, _KEY)
    return SlackConfig(**item.value) if item else SlackConfig()


async def save(store: BaseStore, config: SlackConfig) -> None:
    await store.aput(_NAMESPACE, _KEY, asdict(config))


async def clear(store: BaseStore) -> None:
    await store.adelete(_NAMESPACE, _KEY)


def manifest(name: str) -> str:
    """The app manifest to paste in Slack's "Create New App → From a manifest"."""
    app = {
        "display_information": {"name": name, "description": "Personal assistant"},
        "features": {
            "app_home": {
                "home_tab_enabled": False,
                "messages_tab_enabled": True,
                "messages_tab_read_only_enabled": False,
            },
            "bot_user": {"display_name": name, "always_online": True},
            "slash_commands": [{"command": "/new", "description": "Start a new conversation", "should_escape": False}],
        },
        "oauth_config": {"scopes": {"bot": _BOT_SCOPES, "user": _USER_SCOPES}},
        "settings": {
            "event_subscriptions": {"bot_events": ["message.im"]},
            "interactivity": {"is_enabled": True},
            "org_deploy_enabled": False,
            "socket_mode_enabled": True,
            "token_rotation_enabled": False,
        },
    }
    return json.dumps(app, indent=2)


async def verify(app_token: str, bot_token: str, user_token: str) -> SlackConfig:
    """Checks each token with Slack and returns the settings to save. Raises SlackError."""
    _check_prefix("App token", app_token, "xapp-")
    _check_prefix("Bot token", bot_token, "xoxb-")
    _check_prefix("User token", user_token, "xoxp-")
    await _call("App token", AsyncWebClient(app_token.strip()), "apps.connections.open")
    bot = await _call("Bot token", AsyncWebClient(bot_token.strip()), "auth.test")
    user = await _call("User token", AsyncWebClient(user_token.strip()), "auth.test")
    if bot["team_id"] != user["team_id"]:
        raise SlackError("The bot token and the user token are from different workspaces.")
    tokens = app_token.strip(), bot_token.strip(), user_token.strip()
    return SlackConfig(*tokens, team=str(user["team"]), owner_id=str(user["user_id"]), owner_name=str(user["user"]))


def _check_prefix(label: str, token: str, prefix: str) -> None:
    if not token.strip().startswith(prefix):
        raise SlackError(f"{label} should start with {prefix}")


async def _call(label: str, client: AsyncWebClient, method: str) -> AsyncSlackResponse:
    try:
        return await client.api_call(method)
    except SlackApiError as e:
        raise SlackError(f"Slack rejected the {label.lower()}: {e.response.get('error', 'unknown error')}") from e
    except (SlackClientError, OSError) as e:
        raise SlackError(f"Couldn't reach Slack: {e}") from e
