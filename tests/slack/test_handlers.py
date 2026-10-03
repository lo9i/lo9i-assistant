"""The adapter answers only the owner's DMs, turns buttons into approval decisions, and handles /new."""

from unittest.mock import create_autospec

from slack_sdk.web.async_client import AsyncWebClient

from assistant.core.agent import Session
from assistant.core.events import ApprovalRequired, Done, TextDelta
from assistant.gateways.slack.handlers import Handlers


class _Service:
    def __init__(self):
        self.sent, self.resumed, self.new_threads = [], [], 0
        self.waiting = []

    async def session(self, user_id, channel):
        return Session(user_id, channel, "t1")

    async def send(self, session, text, attachments=()):
        self.sent.append((session, text, attachments))
        yield TextDelta("Hello")
        yield Done()

    async def resume(self, session, decisions):
        self.resumed.append(decisions)
        yield Done()

    async def new_channel_thread(self, user_id, channel):
        self.new_threads += 1
        return "t2"

    async def pending_approvals(self, thread_id):
        return self.waiting


def _handlers():
    client = create_autospec(AsyncWebClient, instance=True)
    client.chat_postMessage.return_value = {"ts": "9.0"}
    service = _Service()
    return Handlers(service, client, "xoxb-1", "U1"), service, client


def _dm(**fields):
    return {"type": "message", "channel_type": "im", "channel": "D1", "user": "U1", "text": "a &lt; b", **fields}


async def test_the_owners_dm_runs_a_turn():
    handlers, service, client = _handlers()
    await handlers.message(_dm())
    assert service.sent == [(Session("owner", "slack", "t1"), "a < b", [])]
    # A draft first, then the final version as Markdown.
    assert client.chat_update.call_args.kwargs["blocks"] == [{"type": "markdown", "text": "Hello"}]


async def test_others_edits_and_bots_are_ignored():
    handlers, service, _ = _handlers()
    for event in (_dm(user="U2"), _dm(subtype="message_changed"), _dm(bot_id="B1"), _dm(channel_type="channel")):
        await handlers.message(event)
    assert service.sent == []


async def test_video_is_refused():
    handlers, service, client = _handlers()
    await handlers.message(_dm(files=[{"id": "F1", "mimetype": "video/mp4", "url_private_download": "https://x"}]))
    assert service.sent == [] and "Video" in client.chat_postMessage.call_args.kwargs["text"]


async def test_an_approval_button_resumes_the_run():
    handlers, service, client = _handlers()
    payload = {
        "type": "block_actions",
        "user": {"id": "U1"},
        "actions": [{"value": "r:abc"}],
        "channel": {"id": "D1"},
        "message": {"ts": "5.0", "text": "Approve bash?"},
    }
    await handlers.approval(payload)
    assert service.resumed == [{"abc": {"approved": False, "reason": "rejected in Slack"}}]
    assert client.chat_update.call_args.kwargs["blocks"] == []  # buttons removed
    await handlers.approval({**payload, "user": {"id": "U2"}})
    assert len(service.resumed) == 1


async def test_new_starts_a_conversation_for_the_owner_only():
    handlers, service, _ = _handlers()
    assert (await handlers.command({"user_id": "U1", "command": "/new"}))["text"] == "Started a new conversation."
    assert "only answers" in (await handlers.command({"user_id": "U2", "command": "/new"}))["text"]
    assert service.new_threads == 1


def _press(value):
    return {
        "type": "block_actions",
        "user": {"id": "U1"},
        "actions": [{"value": value}],
        "channel": {"id": "D1"},
        "message": {"ts": "5.0", "text": "Which sources?"},
    }


_SOURCES = {"kind": "question", "question": "Which sources?", "options": ["Google", "GitHub", "X"], "multiple": True}


async def test_question_toggles_redraw_the_buttons_and_done_answers():
    handlers, service, client = _handlers()
    service.waiting = [ApprovalRequired("q1", _SOURCES)]
    await handlers.approval(_press("qt:q1:0:2"))
    labels = [e["text"]["text"] for e in client.chat_update.call_args.kwargs["blocks"][-1]["elements"]]
    assert labels == ["☐ Google", "☐ GitHub", "☑ X", "✅ Done"]
    assert service.resumed == []
    await handlers.approval(_press("qd:q1:5"))
    assert service.resumed == [{"q1": {"choices": ["Google", "X"]}}]
    assert "Picked: Google, X." in client.chat_postMessage.call_args_list[0].kwargs["text"]


async def test_a_question_no_longer_waiting_is_said_so():
    handlers, service, client = _handlers()
    await handlers.approval(_press("qp:q1:0"))
    assert service.resumed == []
    assert "isn't waiting" in client.chat_postMessage.call_args.kwargs["text"]
