"""How a run looks in Telegram: status messages for tools, the streamed reply, approval buttons."""

import asyncio

import pytest

from assistant.core.events import ApprovalRequired, Done, Error, TextDelta, ToolFinished, ToolStarted, Transcribed
from assistant.gateways.telegram import turn as turn_module
from assistant.gateways.telegram.turn import TelegramTurn


class FakeChat:
    def __init__(self):
        self.messages, self.log, self._next = {}, [], 0

    async def send(self, text, *, markdown=False, buttons=None):
        self._next += 1
        self.messages[self._next] = text
        self.log.append(("send", self._next, text, markdown, buttons))
        return self._next

    async def edit(self, message_id, text, *, markdown=False):
        self.messages[message_id] = text
        self.log.append(("edit", message_id, text, markdown))

    async def typing(self):
        pass


@pytest.fixture(autouse=True)
def fast_edits(monkeypatch):
    monkeypatch.setattr(turn_module, "_EDIT_INTERVAL", 0)


async def _events():
    yield Transcribed("busca la documentación", "es")
    yield ToolStarted("web_search", {"query": "langgraph"})
    yield ToolFinished("web_search", "results")
    for word in ["The package is ", "**langgraph-checkpoint-sqlite**."]:
        await asyncio.sleep(0)
        yield TextDelta(word)
    yield ToolStarted("bash", {"command": "rm -rf build"})
    yield ApprovalRequired("abc", {"tool": "bash", "command": "rm -rf build", "reason": "recursive delete"})
    yield Error("boom")
    yield Done()


async def test_rendering_order_and_final_markdown():
    chat = FakeChat()
    await TelegramTurn(chat).render(_events())
    assert chat.messages[1] == "🎤 I heard (es): busca la documentación"
    assert chat.messages[2] == "✓ web_search(langgraph)"
    assert chat.messages[3] == "The package is **langgraph-checkpoint-sqlite**."
    assert ("edit", 3, chat.messages[3], True) in chat.log
    assert chat.messages[4] == "⏺ bash(rm -rf build)"  # a new status message below the reply
    approval = next(entry for entry in chat.log if entry[0] == "send" and entry[4])
    assert approval[2] == "Approve bash? (recursive delete)\n\nrm -rf build"
    assert approval[4] == [("✅ Approve", "a:abc"), ("❌ Reject", "r:abc")]
    assert list(chat.messages.values())[-1] == "⚠️ boom"
