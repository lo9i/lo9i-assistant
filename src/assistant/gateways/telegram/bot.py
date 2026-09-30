"""The Telegram adapter: runs the bot with long polling inside the daemon. The token comes from the
database (set from /telegram), so it waits until Telegram is connected and restarts the bot when
the token changes."""

import asyncio
import contextlib
import logging

from telegram import Update
from telegram.error import InvalidToken, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from assistant.core.agent import AssistantService
from assistant.gateways.telegram.handlers import Handlers

logger = logging.getLogger(__name__)

_MESSAGES = filters.TEXT & ~filters.COMMAND | filters.PHOTO | filters.Document.ALL | filters.VOICE | filters.AUDIO
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
        with contextlib.suppress(TelegramError):
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        self._app = None
        logger.info("Telegram bot stopped.")

    async def _start(self, token: str) -> None:
        app = build_application(self._service, token)
        try:
            await app.initialize()
            await app.start()
            await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        except (InvalidToken, TelegramError) as e:
            logger.error("Telegram bot didn't start: %s", e)
            return
        self._app = app
        logger.info("Telegram bot running as @%s.", app.bot.username)


class TelegramAdapter:
    """Keeps the Telegram bot in sync with the token stored in the database (set from /telegram)."""

    name = "telegram"

    def __init__(self, service: AssistantService) -> None:
        self._service = service

    async def run(self, stop: asyncio.Event) -> None:
        supervisor = _Supervisor(self._service)
        try:
            while not stop.is_set():
                await self._service.telegram_heartbeat()
                await supervisor.sync()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=_CHECK_SECONDS)
        finally:
            await supervisor.stop()
