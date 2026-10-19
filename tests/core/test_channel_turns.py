"""How a run looks in a channel's chat: status messages for tools, the streamed reply tagged with its
conversation, approval and question buttons, and long replies split."""

import asyncio

from assistant.core.channels.chat.approvals import job_approval_buttons, parse_decision, parse_job_decision
from assistant.core.channels.chat.port import ChatLimits
from assistant.core.channels.chat.questions import (
    answered_text,
    choices,
    parse_press,
    question_buttons,
    question_text,
)
from assistant.core.channels.chat.split import split_text
from assistant.core.channels.chat.turn import ChatTurn
from assistant.core.events import (
    ApprovalRequired,
    Done,
    Error,
    TextDelta,
    Thinking,
    ToolFinished,
    ToolStarted,
    Transcribed,
)

LIMITS = ChatLimits(edit_seconds=0, draft_limit=3500, message_limit=3500)
_QUESTION = {"kind": "question", "question": "Which sources?", "options": ["Google", "GitHub", "X"], "multiple": True}


class FakeChat:
    """Records what a turn does with a chat."""

    def __init__(self) -> None:
        self.messages: dict[str, str] = {}
        self.log: list[tuple] = []
        self.voices: list[bytes] = []

    async def send(self, text, *, markdown=False, buttons=None):
        message = str(len(self.messages) + 1)
        self.messages[message] = text
        self.log.append(("send", message, text, markdown, buttons))
        return message

    async def edit(self, message, text, *, markdown=False, buttons=None):
        self.messages[message] = text
        self.log.append(("edit", message, text, markdown, buttons))

    async def typing(self):
        pass

    async def voice(self, ogg_opus):
        self.voices.append(ogg_opus)


async def _render(*events, tag: str = "") -> tuple[FakeChat, ChatTurn]:
    async def stream():
        for event in events:
            await asyncio.sleep(0)
            yield event

    chat = FakeChat()
    turn = ChatTurn(chat, LIMITS, "t1", tag)
    await turn.render(stream())
    return chat, turn


async def test_rendering_order_and_final_markdown():
    chat, turn = await _render(
        Transcribed("busca la documentación", "es"),
        ToolStarted("web_search", {"query": "langgraph"}),
        ToolFinished("web_search", "results"),
        Thinking("the docs are on GitHub"),
        TextDelta("The package is "),
        TextDelta("**langgraph-checkpoint-sqlite**."),
        ToolStarted("bash", {"command": "rm -rf build"}),
        ApprovalRequired("abc", {"tool": "bash", "command": "rm -rf build", "reason": "recursive delete"}),
        Error("boom"),
        Done(),
    )
    assert turn.final_text == ""  # the reply came before the last tool call
    assert chat.messages["1"] == "🎤 I heard (es): busca la documentación"
    assert chat.messages["2"] == "✓ web_search(langgraph)"
    assert chat.messages["3"] == "The package is **langgraph-checkpoint-sqlite**."  # thinking isn't shown
    assert ("edit", "3", chat.messages["3"], True, None) in chat.log
    assert chat.messages["4"] == "⏺ bash(rm -rf build)"  # a new status message below the reply
    approval = next(entry for entry in chat.log if entry[0] == "send" and entry[4])
    assert approval[2] == "Approve bash? (recursive delete)\n\nrm -rf build"
    assert approval[4] == [("✅ Approve", "a:abc"), ("❌ Reject", "r:abc")]
    assert list(chat.messages.values())[-1] == "⚠️ boom"


async def test_the_final_text_is_the_answer_after_the_last_tool():
    _, turn = await _render(
        TextDelta("Let me check. "),
        ToolStarted("web_search", {"query": "x"}),
        ToolFinished("web_search", "results"),
        TextDelta("It's sunny."),
        Done(),
    )
    assert turn.final_text == "It's sunny."


async def test_a_long_reply_is_split_to_fit_the_channel():
    chat, _ = await _render(TextDelta("para one\n\n" + "x" * 5000 + "\n\nend"), Done())
    assert len(chat.messages) > 1 and all(len(m) <= 3500 for m in chat.messages.values())


async def test_a_question_shows_its_buttons():
    chat, _ = await _render(ApprovalRequired("q1", _QUESTION), Done())
    [question] = [entry for entry in chat.log if entry[0] == "send"]
    assert (question[2], question[4]) == (question_text(_QUESTION), question_buttons("q1", _QUESTION))


async def test_the_first_reply_is_tagged_with_its_conversation():
    chat, turn = await _render(
        TextDelta("Booked."), ToolStarted("bash", {"command": "ls"}), TextDelta("Done."), Done(), tag="watchlist"
    )
    assert list(chat.messages.values()) == ["[watchlist] Booked.", "⏺ bash(ls)", "Done."]
    assert turn.final_text == "Done." and turn.thread_id == "t1"


def test_toggles_carry_the_picks_and_done_answers_with_them():
    first = parse_press(question_buttons("q1", _QUESTION)[2][1])  # tick X
    assert first is not None and not first.answers
    buttons = question_buttons("q1", _QUESTION, first.picked)
    assert [label for label, _ in buttons] == ["☐ Google", "☐ GitHub", "☑ X", "✅ Done"]
    second = parse_press(buttons[0][1])  # tick Google
    assert second is not None
    done = parse_press(question_buttons("q1", _QUESTION, second.picked)[-1][1])
    assert done is not None and done.answers and choices(_QUESTION, done.picked) == ["Google", "X"]
    assert answered_text(choices(_QUESTION, done.picked)) == "Picked: Google, X."
    one = {**_QUESTION, "multiple": False}
    assert question_buttons("q1", one)[0] == ("Google", "qp:q1:0")
    assert parse_press("a:i1") is None and parse_press("qp:q1:x") is None and parse_press("qt:q1") is None


def test_buttons_are_told_apart_by_their_data():
    assert parse_decision("a:abc", "Telegram") == ("abc", {"approved": True, "reason": ""})
    assert parse_decision("r:abc", "Telegram") == ("abc", {"approved": False, "reason": "rejected in Telegram"})
    assert [data for _, data in job_approval_buttons("i1")] == ["ja:i1", "jr:i1"]
    assert parse_job_decision("jr:i1", "Slack") == ("i1", {"approved": False, "reason": "rejected in Slack"})
    assert parse_job_decision("a:i1", "Telegram") is None and parse_decision("ja:i1", "Telegram") is None


def test_split_text_respects_the_limit():
    parts = split_text("para one\n\n" + "x" * 5000 + "\n\nend", limit=3500)
    assert all(len(p) <= 3500 for p in parts) and "".join(parts).replace("\n", "").endswith("end")


async def test_a_subagents_calls_go_indented_under_the_call_that_started_it():
    chat, _ = await _render(
        ToolStarted("delegate", {"task": "find the bug"}, id="d1"),
        ToolStarted("web_search", {"query": "x"}, id="w1"),
        ToolStarted("bash", {"command": "ls"}, id="b1", within="d1"),
        ToolStarted("read_file", {"path": "a.py"}, id="r1", within="d1"),
        ToolFinished("bash", "a.py", within="d1"),
        ToolFinished("read_file", "...", within="d1"),
        ToolFinished("delegate", "found it"),
        ToolFinished("web_search", "results"),
        Done(),
    )
    assert chat.messages["1"] == ("✓ delegate(find the bug)\n    ✓ bash(ls)\n    ✓ read_file(a.py)\n✓ web_search(x)")
