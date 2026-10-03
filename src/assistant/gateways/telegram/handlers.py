"""Telegram update handlers: messages, /new, /start and approval buttons."""

from typing import Any

from telegram.ext import ContextTypes

from assistant.core.agent import AssistantService, Session, SynthesisError
from assistant.core.config import settings
from assistant.core.events import is_question
from assistant.gateways.chat.approvals import parse_decision, parse_job_decision
from assistant.gateways.chat.questions import Press, answered_text, choices, parse_press, question_buttons
from assistant.gateways.chat.turn import ChatTurn
from assistant.gateways.telegram.auth import is_allowed, try_pairing
from assistant.gateways.telegram.media import UnsupportedMediaError, attachments_from
from assistant.gateways.telegram.port import LIMITS, TelegramChat, markup
from telegram import CallbackQuery, Message, Update

_CHANNEL = "telegram"
_GREETING = "Hi! Send me a message, a voice note, a photo or a document. /new starts a new conversation."


class Handlers:
    def __init__(self, service: AssistantService) -> None:
        self._service = service

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is not None and await is_allowed(self._service, update):
            await message.reply_text(_GREETING)

    async def new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is not None and await is_allowed(self._service, update):
            await self._service.new_channel_thread(settings.owner_id, _CHANNEL)
            await message.reply_text("Started a new conversation.")

    async def message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or await try_pairing(self._service, update) or not await is_allowed(self._service, update):
            return
        try:
            attachments = await attachments_from(message)
        except UnsupportedMediaError as e:
            await message.reply_text(str(e))
            return
        text = message.text or message.caption or ""
        session = await self._session()
        chat = self._chat(update, context)
        turn = ChatTurn(chat, LIMITS)
        await turn.render(self._service.send(session, text, attachments))
        await self._speak(chat, turn.final_text, after_voice_message=bool(message.voice or message.audio))

    async def approval(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            return
        if not await is_allowed(self._service, update):
            await query.answer()
            return
        await query.answer()
        if job_decision := parse_job_decision(query.data or "", "Telegram"):
            await self._answer_job(query, *job_decision)
            return
        if press := parse_press(query.data or ""):
            await self._answer_question(query, press, self._chat(update, context))
            return
        decision = parse_decision(query.data or "", "Telegram")
        if decision is None:
            return
        interrupt_id, answer = decision
        await query.edit_message_reply_markup(reply_markup=None)
        if isinstance(query.message, Message):
            await query.message.reply_text("Approved." if answer["approved"] else "Rejected.")
        session = await self._session()
        await ChatTurn(self._chat(update, context), LIMITS).render(
            self._service.resume(session, {interrupt_id: answer})
        )

    async def _answer_question(self, query: CallbackQuery, press: Press, chat: TelegramChat) -> None:
        """A toggle only redraws the buttons; a pick or Done answers and the run goes on."""
        session = await self._session()
        request = await self._waiting_question(session, press.interrupt_id)
        if request is None:
            await query.edit_message_reply_markup(reply_markup=None)
            await chat.send("This question isn't waiting for an answer any more.")
            return
        if not press.answers:
            await query.edit_message_reply_markup(
                reply_markup=markup(question_buttons(press.interrupt_id, request, press.picked))
            )
            return
        picked = choices(request, press.picked)
        await query.edit_message_reply_markup(reply_markup=None)
        await chat.send(answered_text(picked))
        await ChatTurn(chat, LIMITS).render(self._service.resume(session, {press.interrupt_id: {"choices": picked}}))

    async def _waiting_question(self, session: Session, interrupt_id: str) -> dict[str, Any] | None:
        waiting = await self._service.pending_approvals(session.thread_id)
        return next((a.request for a in waiting if a.interrupt_id == interrupt_id and is_question(a.request)), None)

    async def _answer_job(self, query: CallbackQuery, interrupt_id: str, answer: dict[str, Any]) -> None:
        """A scheduled job's request: the job's run continues on its own, nothing to show here."""
        await query.edit_message_reply_markup(reply_markup=None)
        if not self._service.approvals.answer(interrupt_id, answer):
            reply = "This request isn't waiting any more: the job's run already went on without it."
        else:
            reply = "Approved. The job goes on." if answer["approved"] else "Rejected. The job goes on without it."
        if isinstance(query.message, Message):
            await query.message.reply_text(reply)

    async def _speak(self, chat: TelegramChat, reply: str, after_voice_message: bool) -> None:
        """Also sends the reply as a voice note when Settings → Audio says so."""
        if not reply or not await self._service.speaks_reply(after_voice_message):
            return
        try:
            await chat.send_voice(await self._service.speak(reply, "ogg"))
        except SynthesisError as e:
            await chat.send(f"⚠️ {e}")

    async def _session(self) -> Session:
        return await self._service.session(settings.owner_id, _CHANNEL)

    @staticmethod
    def _chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> TelegramChat:
        chat = update.effective_chat
        if chat is None:
            raise ValueError("Telegram update without a chat.")
        return TelegramChat(context.bot, chat.id)
