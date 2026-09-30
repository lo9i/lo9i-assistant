"""Telegram setup text (Markdown), shared by the setup screen and the plain REPL."""

from datetime import datetime

from assistant.core.agent import TelegramStatus

_CREATE_BOT = """## Connect Telegram

1. In Telegram, open **@BotFather** and send `/newbot`.
2. Choose a name, then a username ending in `bot`.
3. BotFather replies with a token like `123456789:AAH…`. Paste it below."""


def describe(status: TelegramStatus, error: str) -> str:
    if not status.connected:
        return _CREATE_BOT + (f"\n\n**{error}**" if error else "")
    lines = [f"## Telegram: @{status.bot_username}", _bot_state(status)]
    if status.pairing_code:
        expires = datetime.fromisoformat(status.pairing_expires).astimezone().strftime("%H:%M")
        lines.append(
            f"To pair your account, open https://t.me/{status.bot_username}, press **Start**, "
            f"and send this code: **`{status.pairing_code}`** (valid until {expires})."
        )
    lines.append(_paired(status))
    return "\n\n".join(lines)


def _bot_state(status: TelegramStatus) -> str:
    if status.bot_running:
        return "Bot: running ✓"
    return "Bot: **not running**. The Telegram service starts with the app; it may take a few seconds."


def _paired(status: TelegramStatus) -> str:
    if not status.paired_users:
        return "No account paired yet."
    return "Paired: " + ", ".join(status.paired_users) + " ✓"
