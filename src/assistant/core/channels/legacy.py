"""Telegram and Slack settings from before they were plugins, handed to the plugins when the user
installs them: the tokens fill the install's empty fields, Telegram's paired accounts go to the
plugin's data folder as `import.json` (the plugin reads and deletes it), and the old records go."""

import asyncio
import json
from typing import Any

from langgraph.store.base import BaseStore

from assistant.core.mcp import folders
from assistant.core.mcp.install import ServerValues

_NAMESPACE = ("integrations",)
# The old record's key -> the plugin's field for each token in it.
_FIELDS = {
    "telegram": {"token": "TELEGRAM_TOKEN"},
    "slack": {"app_token": "SLACK_APP_TOKEN", "bot_token": "SLACK_BOT_TOKEN", "user_token": "SLACK_USER_TOKEN"},
}
_OTHER_KEYS = {"telegram": ["telegram_heartbeat"], "slack": []}
IMPORT_FILE = "import.json"


async def fill(store: BaseStore, wanted: ServerValues) -> ServerValues:
    """The values to install with: the ones given, and the old tokens for fields left empty."""
    old = await _record(store, wanted.name)
    if not old:
        return wanted
    tokens = {field: str(old.get(key, "")) for key, field in _FIELDS[wanted.name].items()}
    given = {k: v for k, v in wanted.values.items() if v.strip()}
    return ServerValues(wanted.name, {**wanted.values, **{k: v for k, v in tokens.items() if v}, **given})


async def known_fields(store: BaseStore, name: str) -> list[str]:
    """The plugin's fields the old record has values for."""
    old = await _record(store, name)
    return sorted(field for key, field in _FIELDS.get(name, {}).items() if old.get(key))


async def hand_over(store: BaseStore, name: str) -> None:
    """After installing the plugin: pass on what only the old record has, then remove it."""
    old = await _record(store, name)
    if not old:
        return
    if name == "telegram" and old.get("users"):
        await asyncio.to_thread(_write_import, name, {"users": old["users"]})
    for key in [name, *_OTHER_KEYS[name]]:
        await store.adelete(_NAMESPACE, key)


async def _record(store: BaseStore, name: str) -> dict[str, Any]:
    if name not in _FIELDS:
        return {}
    item = await store.aget(_NAMESPACE, name)
    return dict(item.value) if item else {}


def _write_import(name: str, data: dict[str, Any]) -> None:
    path = folders.data(name) / IMPORT_FILE
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(0o600)
