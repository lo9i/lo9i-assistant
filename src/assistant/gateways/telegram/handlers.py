"""Telegram update handlers: messages, /new, /start and approval buttons."""

from telegram import Update
from telegram.ext import ContextTypes

from assistant.core.agent import AssistantService, Session
from assistant.core.config import settings
from assistant.gateways.telegram.approvals import parse_decision
from assistant.gateways.telegram.auth import is_allowed
from assistant.gateways.telegram.media import UnsupportedMedia, attachments_from
from assistant.gateways.telegram.port import TelegramChat
from assistant.gateways.telegram.turn import TelegramTurn

_CHANNEL = "telegram"
_GREETING = "Hi! Send me a message, a photo or a document. /new starts a new conversation."


class Handlers:
    def __init__(self, service: AssistantService) -> None:
        self._service = service

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if is_allowed(update):
            await update.effective_message.reply_text(_GREETING)

    async def new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if is_allowed(update):
            await self._service.new_thread(settings.owner_id)
            await update.effective_message.reply_text("Started a new conversation.")

    async def message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update):
            return
        message = update.effective_message
        try:
            attachments = await attachments_from(message)
        except UnsupportedMedia as e:
            await message.reply_text(str(e))
            return
        text = message.text or message.caption or ""
        session = await self._session()
        await TelegramTurn(self._chat(update, context)).render(self._service.send(session, text, attachments))

    async def approval(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not is_allowed(update):
            await query.answer()
            return
        decision = parse_decision(query.data or "")
        await query.answer()
        if decision is None:
            return
        interrupt_id, answer = decision
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Approved." if answer["approved"] else "Rejected.")
        session = await self._session()
        await TelegramTurn(self._chat(update, context)).render(self._service.resume(session, {interrupt_id: answer}))

    async def _session(self) -> Session:
        return await self._service.session(settings.owner_id, _CHANNEL)

    @staticmethod
    def _chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> TelegramChat:
        return TelegramChat(context.bot, update.effective_chat.id)
