"""What the Slack adapter does with each request from Slack: DMs, approval buttons and /new. Only
the owner (the user who installed the app) is answered; everyone else is ignored."""

import html
from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol

import httpx
from slack_sdk.web.async_client import AsyncWebClient

from assistant.core.agent import Session
from assistant.core.attachments import Attachment
from assistant.core.config import settings
from assistant.core.events import Event
from assistant.gateways.chat.approvals import parse_decision
from assistant.gateways.chat.turn import ChatTurn
from assistant.gateways.slack.media import UnsupportedMediaError, attachments_from
from assistant.gateways.slack.port import LIMITS, SlackChat

_CHANNEL = "slack"
# A plain message, or one with files. Edits, deletions and bot messages have other subtypes.
_MESSAGE_SUBTYPES = {None, "file_share"}


class Conversations(Protocol):
    """The AssistantService calls the handlers need."""

    async def session(self, user_id: str, channel: str) -> Session: ...
    def send(self, session: Session, text: str, attachments: Sequence[Attachment] = ()) -> AsyncIterator[Event]: ...
    def resume(self, session: Session, decisions: dict[str, dict[str, Any]]) -> AsyncIterator[Event]: ...
    async def new_channel_thread(self, user_id: str, channel: str) -> str: ...


class Handlers:
    def __init__(self, service: Conversations, client: AsyncWebClient, bot_token: str, owner_id: str) -> None:
        self._service = service
        self._client = client
        self._bot_token = bot_token
        self._owner_id = owner_id

    async def message(self, event: dict[str, Any]) -> None:
        if not self._is_owner_dm(event):
            return
        chat = SlackChat(self._client, event["channel"])
        attachments = await self._attachments(chat, event.get("files", []))
        if attachments is None:
            return
        text = html.unescape(event.get("text", ""))
        await ChatTurn(chat, LIMITS).render(self._service.send(await self._session(), text, attachments))

    async def approval(self, payload: dict[str, Any]) -> None:
        if payload.get("type") != "block_actions" or payload.get("user", {}).get("id") != self._owner_id:
            return
        decision = parse_decision(payload["actions"][0].get("value", ""), "Slack")
        if decision is None:
            return
        interrupt_id, answer = decision
        chat = SlackChat(self._client, payload["channel"]["id"])
        await chat.edit(payload["message"]["ts"], payload["message"].get("text", ""))
        await chat.send("Approved." if answer["approved"] else "Rejected.")
        await ChatTurn(chat, LIMITS).render(self._service.resume(await self._session(), {interrupt_id: answer}))

    async def command(self, payload: dict[str, Any]) -> dict[str, str]:
        """Slash commands. The reply is sent with the acknowledgement, visible only to the owner."""
        if payload.get("user_id") != self._owner_id:
            return {"text": "This assistant only answers the person who set it up."}
        if payload.get("command") == "/new":
            await self._service.new_channel_thread(settings.owner_id, _CHANNEL)
            return {"text": "Started a new conversation."}
        return {"text": f"Unknown command {payload.get('command')}."}

    async def _attachments(self, chat: SlackChat, files: list[dict[str, Any]]) -> list[Attachment] | None:
        """The message's files, or None after telling the owner why they can't be used."""
        try:
            return await attachments_from(files, self._bot_token)
        except UnsupportedMediaError as e:
            await chat.send(str(e))
        except httpx.HTTPError as e:
            await chat.send(f"Couldn't download the file from Slack: {e}")
        return None

    def _is_owner_dm(self, event: dict[str, Any]) -> bool:
        return (
            event.get("type") == "message"
            and event.get("channel_type") == "im"
            and event.get("subtype") in _MESSAGE_SUBTYPES
            and not event.get("bot_id")
            and event.get("user") == self._owner_id
        )

    async def _session(self) -> Session:
        return await self._service.session(settings.owner_id, _CHANNEL)
