"""The terminal app: a turn with tool calls, the approval dialog, memory panel and new conversation."""

import asyncio

from textual.widgets import Input, Markdown

from assistant.client import DaemonUnavailableError, clipboard
from assistant.core.attachments import Attachment
from assistant.core.events import ApprovalRequired, Cancelled, Done, TextDelta, ToolFinished, ToolStarted
from assistant_terminal.tui.attachments import AttachmentBar
from assistant_terminal.tui.screens import ApprovalScreen, QuestionScreen, SideConversationScreen
from assistant_terminal.tui.widgets import AssistantMessage, StoppedNote, ToolCall, UserMessage
from tests.terminal.conftest import wait_for


async def test_a_question_with_several_options_is_answered_with_the_picked_ones(app, client):
    client.waiting_for = {
        "kind": "question",
        "question": "Which?",
        "options": ["Google", "GitHub", "X"],
        "multiple": True,
    }
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"look me up", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, QuestionScreen))
        await pilot.press("space", "down", "down", "space")
        app.screen.query_one("#done").press()
        await wait_for(pilot, lambda: not app._busy)
        assert client.decisions == {"i1": {"choices": ["Google", "X"]}}


async def test_a_question_with_one_choice_answers_on_enter_and_esc_skips(app, client):
    client.waiting_for = {"kind": "question", "question": "Which one is you?", "options": ["Ana P.", "Ana R."]}
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"look me up", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, QuestionScreen))
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: not app._busy)
        assert client.decisions == {"i1": {"choices": ["Ana R."]}}
        await pilot.press(*"again", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, QuestionScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: not app._busy)
        assert client.decisions == {"i1": {"choices": None}}


async def test_turn_with_approval(app, client):
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"list files then clean up", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ApprovalScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: not app._busy)
        assert client.decisions == {"i1": {"approved": True, "reason": None}}
        chat = app.query_one("#chat")
        assert [type(w) for w in chat.children] == [UserMessage, ToolCall, ToolCall, AssistantMessage]
        assert [t.title for t in app.query(ToolCall)] == ["✓ bash(ls -la)", "✓ bash(rm -rf build)"]
        assert app.query_one(AssistantMessage).source == "## Done\n\nListed **1 file**."
        assert "backend engineer" in str(app.query_one("#memory-body").render())


async def test_new_conversation_clears_the_chat(app):
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"hi", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ApprovalScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: not app._busy)
        await pilot.press("ctrl+n")
        await wait_for(pilot, lambda: app.sub_title == "owner:new")
        assert len(app.query_one("#chat").children) == 0


async def test_home_goes_back_with_its_history(app):
    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        await wait_for(pilot, lambda: app.sub_title == "owner:new")
        await pilot.click("#prompt")
        await pilot.press(*"/home", "enter")
        await wait_for(pilot, lambda: app.sub_title == "owner:abc" and app.query(UserMessage))
        assert "plan my trip" in str(app.query_one(UserMessage).render())


async def test_taking_the_suggestion_moves_the_task_to_a_side_conversation(app, client, monkeypatch):
    request = {"kind": "side_conversation", "title": "Taxes", "brief": "Do them.", "first_message": "Carried over"}
    sent = []

    async def send(session, text, attachments=()):
        sent.append((session.thread_id, text))
        if len(sent) == 1:
            yield ApprovalRequired("i1", request)
        else:
            yield TextDelta("On it.")
            yield Done()

    async def resume(session, decisions):
        client.decisions = decisions
        yield TextDelta("Moved.")
        yield Done()

    monkeypatch.setattr(client, "send", send)
    monkeypatch.setattr(client, "resume", resume)
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"taxes", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, SideConversationScreen))
        await pilot.click("#move")
        await wait_for(pilot, lambda: len(sent) == 2 and not app._busy)
        assert client.decisions == {"i1": {"moved": True}}
        assert sent == [("owner:abc", "taxes"), ("owner:new", "Carried over")]
        assert [str(m.render()) for m in app.query(UserMessage)] == ["> Carried over"]


async def test_attachment_can_be_sent_without_text(app, client, tmp_path):
    note = tmp_path / "note.txt"
    note.write_text("hello")
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*f"/attach {note}", "enter")
        await pilot.press("enter")
        await wait_for(pilot, lambda: client.sent)
        assert client.sent[0] == ("", [("note.txt", "text/plain")])


async def test_live_events_update_the_app(app, client):
    from assistant.core.events import Done, TextDelta
    from tests.terminal.conftest import wait_for

    async def other_terminal_run():
        yield TextDelta("It's Tuesday.")
        yield Done()

    async with app.run_test() as pilot:

        def memory() -> str:
            return str(app.query_one("#memory-body").render())

        client.memory.profile = {"work": ["programmer"]}  # e.g. an archive finishing after /new
        await client.bus.put(("memory", {}))
        await wait_for(pilot, lambda: "programmer" in memory())

        run = {"thread_id": "owner:abc", "channel": "cli", "text": "what day is it?"}
        await client.bus.put(("run", {**run, "run_id": "r0", "client_id": "me"}))  # this terminal's own
        client.runs["r1"] = other_terminal_run
        await client.bus.put(("run", {**run, "run_id": "r1", "client_id": "other"}))
        await wait_for(pilot, lambda: len(app.query(AssistantMessage)) == 1)
        assert len(app.query(UserMessage)) == 1
        assert "[cli] what day is it?" in str(app.query(UserMessage).first().render())


async def test_new_leaves_a_running_reply_and_reports_when_it_finishes(app, client):
    import asyncio

    from tests.terminal.conftest import wait_for

    async def never_ending(session, text, attachments=()):
        await asyncio.sleep(3600)
        yield

    client.send = never_ending
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"long task", "enter")
        await wait_for(pilot, lambda: app._busy)
        await pilot.press("ctrl+n")
        await wait_for(pilot, lambda: app.sub_title == "owner:new" and not app._busy)
        assert len(app.query_one("#chat").children) == 0
        before = len(app._notifications)
        await client.bus.put(
            (
                "run_finished",
                {"run_id": "r", "thread_id": "owner:abc", "channel": "cli", "status": "ok", "reply": "All done."},
            )
        )
        await wait_for(pilot, lambda: len(app._notifications) > before)
        assert any("Previous conversation finished: All done." in n.message for n in app._notifications)


async def test_an_unreachable_daemon_is_reported_and_the_app_keeps_running(app, client):
    async def send(session, text, attachments=()):
        raise DaemonUnavailableError("Lost the connection to the daemon.")
        yield

    client.send = send
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"hi", "enter")
        await wait_for(pilot, lambda: any("Lost the connection" in n.message for n in app._notifications))
        assert not app._busy and app.is_running


async def test_ctrl_v_attaches_a_screenshot_and_pastes_text(app, client, monkeypatch):
    pasted: list[Attachment | str] = [Attachment("pasted-120000.png", "image/png", b"png"), "what is this?"]

    async def paste():
        return pasted.pop(0)

    monkeypatch.setattr(clipboard, "paste", paste)
    app._can_paste = True
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press("ctrl+v", "ctrl+v")
        await wait_for(pilot, lambda: app.query_one("#prompt", Input).value == "what is this?")
        await pilot.press("enter")
        await wait_for(pilot, lambda: client.sent)
        assert client.sent[0] == ("what is this?", [("pasted-120000.png", "image/png")])


async def test_esc_stops_the_reply(app, client, monkeypatch):
    stopped = asyncio.Event()

    async def cancel(session):
        stopped.set()
        return True

    async def send(session, text, attachments=()):
        yield ToolStarted("bash", {"command": "sleep 30"})
        await stopped.wait()
        yield Cancelled()

    monkeypatch.setattr(client, "send", send)
    monkeypatch.setattr(client, "cancel", cancel)
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"wait", "enter")
        await wait_for(pilot, lambda: app.query(ToolCall))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.query(StoppedNote) and not app._busy)
        assert str(app.query_one(ToolCall).title).startswith("✗")


async def test_a_subagents_calls_show_inside_its_delegate_call(app, client, monkeypatch):
    async def send(session, text, attachments=()):
        yield ToolStarted("delegate", {"task": "look"}, id="d1")
        yield ToolStarted("bash", {"command": "ls"}, within="d1")
        yield ToolFinished("bash", "a.txt", within="d1")
        yield ToolFinished("delegate", "found a.txt")
        yield Done()

    monkeypatch.setattr(client, "send", send)
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"look", "enter")
        await wait_for(pilot, lambda: not app._busy and app.query(ToolCall))
        delegate, step = app.query(ToolCall)
        assert delegate.title == "✓ delegate(look) · 1 step" and step.title == "✓ bash(ls)"
        assert step.parent is not None and delegate in step.ancestors


async def test_attached_files_show_as_tags_that_can_be_removed(app, client, tmp_path):
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text(name)
    async with app.run_test() as pilot:
        bar = app.query_one(AttachmentBar)
        await pilot.click("#prompt")
        for name in ("a.txt", "b.txt", "c.txt"):
            app.query_one("#prompt", Input).value = f"/attach {tmp_path / name}"
            await pilot.press("enter")
        await wait_for(pilot, lambda: len(bar.pending) == 3)
        assert str(bar.query(".tag").first().render()) == "[a.txt 5 B]"
        await pilot.press("x", "backspace")  # edits the text, keeps the files
        assert len(bar.pending) == 3
        await pilot.press("backspace", "backspace")  # empty box: removes the last files
        assert [a.name for a in bar.pending] == ["a.txt"]
        await pilot.press("enter")
        await wait_for(pilot, lambda: client.sent)
        assert client.sent[0] == ("", [("a.txt", "text/plain")]) and not bar.pending


async def test_get_to_know_me_starts_its_own_conversation(app, client):
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/get-to-know-me", "enter")
        await wait_for(pilot, lambda: bool(client.sent))
        assert app.sub_title == "owner:new" and client.sent[0][0] == "Get to know me."


async def test_a_plugin_the_agent_offers_is_installed_in_the_dialog(app, client):
    from dataclasses import asdict

    from assistant.core.agent import FoundServer, ServerField
    from assistant_terminal.tui.screens import ChannelSetupScreen, RepositoryInstallScreen

    fields = [ServerField("TELEGRAM_TOKEN", "Bot token", secret=True)]
    steps = ["Open @BotFather and send /newbot."]
    telegram = FoundServer("telegram", "Chat on Telegram", "channel", fields, False, channel=True, steps=steps)
    client.waiting_for = {
        "kind": "plugin",
        "name": "telegram",
        "description": telegram.description,
        "server": asdict(telegram),
    }
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"message me on Telegram", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, RepositoryInstallScreen))
        message = app.screen.query_one("#repository-message", Markdown)
        await wait_for(pilot, lambda: "1. Open @BotFather and send /newbot." in message.source)
        app.screen.query(Input).first().value = "123:abc"
        app.screen.query_one("#install").press()
        # Then its setup, in the conversation too.
        await wait_for(pilot, lambda: isinstance(app.screen, ChannelSetupScreen))
        app.screen.query_one("#done").press()
        await wait_for(pilot, lambda: not app._busy)
        assert client.decisions == {"i1": {"installed": True}}
        assert [(s.name, s.values) for s in client.repositories.installed[0][2]] == [
            ("telegram", {"TELEGRAM_TOKEN": "123:abc"})
        ]
        await pilot.press(*"again", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, RepositoryInstallScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: not app._busy)
        assert client.decisions == {"i1": {"installed": False}}


async def test_files_dropped_on_the_window_are_attached_and_text_is_typed(app, client, tmp_path):
    from textual import events

    photo = tmp_path / "My Photo.png"
    photo.write_bytes(b"png")
    async with app.run_test(size=(120, 36)) as pilot:
        prompt = app.query_one("#prompt", Input)
        prompt.post_message(events.Paste(str(photo).replace(" ", "\\ ") + " "))
        await wait_for(pilot, lambda: bool(app.query_one(AttachmentBar).pending))
        assert [a.name for a in app.query_one(AttachmentBar).pending] == ["My Photo.png"]
        assert prompt.value == ""
        prompt.post_message(events.Paste("just text"))
        await wait_for(pilot, lambda: prompt.value == "just text")


async def test_the_agent_opens_a_plugins_setup_in_the_conversation(app, client):
    from dataclasses import asdict

    from assistant.core.agent import FoundServer
    from assistant_terminal.tui.screens import EmailScreen

    gmail = FoundServer("gmail", "Send and read Gmail", "none", [], False, installed=True, email=True)
    client.waiting_for = {
        "kind": "plugin_setup",
        "name": "gmail",
        "description": gmail.description,
        "server": asdict(gmail),
    }
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"set up my Gmail", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EmailScreen) and app.screen._plugin == "gmail")
        await pilot.press("escape")
        await wait_for(pilot, lambda: not app._busy)
        assert client.decisions == {"i1": {"done": True}}
