"""The Telegram adapter: runs the bot with long polling inside the daemon. The token comes from the
database (set from /telegram), so it waits until Telegram is connected and restarts the bot when
the token changes."""

import asyncio
import contextlib
import logging

from telegram.error import InvalidToken, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, Updater, filters

from assistant.core.agent import AssistantService
from assistant.gateways.telegram.handlers import Handlers
from assistant.gateways.telegram.name import BotName
from assistant.gateways.telegram.sender import TelegramSender
from telegram import Update

logger = logging.getLogger(__name__)

_MESSAGES = filters.TEXT & ~filters.COMMAND | filters.PHOTO | filters.Document.ALL | filters.VOICE | filters.AUDIO
_CHANNEL = "telegram"
# How often to check the database for a new, changed or removed token.
_CHECK_SECONDS = 5


def build_application(service: AssistantService, token: str) -> Application:
    handlers = Handlers(service)
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("new", handlers.new))
    app.add_handler(CallbackQueryHandler(handlers.approval))
    app.add_handler(MessageHandler(_MESSAGES, handlers.message))
    return app


class _Supervisor:
    """Keeps one bot running for the token currently stored in the database."""

    def __init__(self, service: AssistantService) -> None:
        self._service = service
        self._token = ""
        self._app: Application | None = None
        self._name = BotName(service)

    async def apply_name(self) -> None:
        if self._app is not None:
            await self._name.apply(self._app.bot)

    async def sync(self) -> None:
        token = await self._service.telegram_token()
        if token == self._token:
            return
        await self.stop()
        self._token = token
        if token:
            await self._start(token)

    async def stop(self) -> None:
        if self._app is None:
            return
        self._service.outbox.unregister(_CHANNEL)
        with contextlib.suppress(TelegramError):
            if self._app.updater is not None:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        self._app = None
        self._service.bus.publish("integrations")
        logger.info("Telegram bot stopped.")

    async def _start(self, token: str) -> None:
        app = build_application(self._service, token)
        try:
            await app.initialize()
            await app.start()
            await _updater(app).start_polling(allowed_updates=Update.ALL_TYPES)
        except (InvalidToken, TelegramError) as e:
            logger.error("Telegram bot didn't start: %s", e)
            return
        self._app = app
        self._name.forget()
        await self._name.apply(app.bot)
        self._service.outbox.register(_CHANNEL, TelegramSender(app.bot, self._service))
        self._service.bus.publish("integrations")
        logger.info("Telegram bot running as @%s.", app.bot.username)


class TelegramAdapter:
    """Keeps the Telegram bot in sync with the token stored in the database (set from /telegram)."""

    name = "telegram"

    def __init__(self, service: AssistantService) -> None:
        self._service = service

    async def run(self, stop: asyncio.Event) -> None:
        supervisor = _Supervisor(self._service)
        renames = asyncio.create_task(self._follow_renames(supervisor))
        try:
            while not stop.is_set():
                await self._service.telegram_heartbeat()
                await supervisor.sync()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=_CHECK_SECONDS)
        finally:
            renames.cancel()
            await supervisor.stop()

    async def _follow_renames(self, supervisor: _Supervisor) -> None:
        """The assistant's name is a setting; a change renames the bot right away."""
        async for event in self._service.bus.subscribe():
            if event.kind == "settings":
                await supervisor.apply_name()


def _updater(app: Application) -> Updater:
    """Applications from `build_application` always poll, so they have an updater."""
    if app.updater is None:
        raise RuntimeError("The Telegram application was built without an updater.")
    return app.updater
