"""Builds the bot and runs it with long polling until SIGINT or SIGTERM."""

import asyncio
import logging
import signal

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from assistant.core.agent import AssistantService
from assistant.core.config import settings
from assistant.gateways.telegram.handlers import Handlers

logger = logging.getLogger(__name__)

_MESSAGES = filters.TEXT & ~filters.COMMAND | filters.PHOTO | filters.Document.ALL | filters.VOICE | filters.AUDIO


def build_application(service: AssistantService) -> Application:
    handlers = Handlers(service)
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("new", handlers.new))
    app.add_handler(CallbackQueryHandler(handlers.approval))
    app.add_handler(MessageHandler(_MESSAGES, handlers.message))
    return app


async def _serve(app: Application) -> None:
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram bot running (long polling).")
        await stop.wait()
        await app.updater.stop()
        await app.stop()


async def _main() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (create a bot with @BotFather).")
    if not settings.telegram_allowed_user_ids:
        logger.warning("TELEGRAM_ALLOWED_USER_IDS is empty: every message will be ignored and its user id logged.")
    async with AssistantService.open() as service:
        await _serve(build_application(service))


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(_main())
