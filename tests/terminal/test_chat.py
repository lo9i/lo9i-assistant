"""The terminal app: a turn with tool calls, the approval dialog, memory panel and new conversation."""

import asyncio
from dataclasses import replace

from textual.widgets import Button, Input, Markdown

from assistant.client import DaemonUnavailableError, clipboard
from assistant.core.attachments import Attachment
from assistant.core.conversations import Conversation
from assistant.core.events import (
    Cancelled,
    Dispatched,
    Done,
    TextDelta,
    Thinking,
    ToolFinished,
    ToolStarted,
)
from assistant_terminal.tui.attachments import AttachmentBar
from assistant_terminal.tui.screens import (
    ApprovalScreen,
    ConversationsScreen,
    JobsScreen,
    NotificationsScreen,
    QuestionScreen,
)
from assistant_terminal.tui.widgets import (
    AssistantMessage,
    StoppedNote,
    SystemNote,
    ThinkingNote,
    ToolCall,
    UserMessage,
)
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
        await wait_for(pilot, lambda: app.sub_title == "new conversation")
        assert len(app.query_one("#chat").children) == 0


async def test_the_subtitle_names_the_conversation_by_its_title_once_it_has_one(app, client):
    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        await wait_for(pilot, lambda: app.sub_title == "new conversation")
        at = "2026-10-01T09:00:00+00:00"
        client.conversations.items.append(Conversation(app._live.session.thread_id, "Trip to Rome", at, at))
        await client.bus.put(("conversations", {}))
        await wait_for(pilot, lambda: app.sub_title == "Trip to Rome")


async def test_the_app_opens_to_the_conversations_and_inbox_shows_them_again(app, client):
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: bool(app.query(SystemNote)))
        assert app.sub_title == "inbox"
        listed = app.query_one(SystemNote).source
        assert "**plan my trip**" in listed and "/conversations opens one" in listed
        await pilot.press("ctrl+n")
        await wait_for(pilot, lambda: app.sub_title == "new conversation")
        await pilot.click("#prompt")
        await pilot.press(*"/inbox", "enter")
        await wait_for(pilot, lambda: app.sub_title == "inbox" and app.query(SystemNote))
        assert not app.query(UserMessage)  # the list, not the inbox's own messages


async def test_sending_a_message_takes_the_list_away(app, client):
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: bool(app.query(SystemNote)))
        await pilot.click("#prompt")
        await pilot.press(*"hi", "enter")
        await wait_for(pilot, lambda: bool(app.query(UserMessage)))
        assert not app.query(SystemNote)


async def test_conversations_list_titles_and_open_one(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/conversations", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConversationsScreen))
        options = app.screen.query_one("#conversations-list")
        assert "plan my trip" in str(options.get_option_at_index(0).prompt)


async def test_a_notification_opens_the_conversation_its_work_started_in(app, client):
    at = "2026-10-01T09:00:00+00:00"
    client.conversations.items.append(Conversation("owner:trip", "Trip", at, at))
    client.notifications.items[0] = replace(client.notifications.items[0], thread_id="owner:trip")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/notifications", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, NotificationsScreen))
        await wait_for(pilot, lambda: all(n.read for n in client.notifications.items))
        await pilot.press("enter")
        await wait_for(pilot, lambda: app.sub_title == "Trip")


async def test_a_job_notification_opens_its_run_with_the_whole_reply_and_can_be_dismissed(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/notifications", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, NotificationsScreen))
        await pilot.press("down")
        await wait_for(pilot, lambda: str(app.screen.query_one("#open", Button).label) == "Open the job")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, JobsScreen))
        body = app.screen.query_one("#job-body", Markdown)
        await wait_for(pilot, lambda: "three headlines, the weather and the markets, in full" in body.source)
        await pilot.press("escape")
        await wait_for(pilot, lambda: isinstance(app.screen, NotificationsScreen))
        await pilot.click("#dismiss")
        await wait_for(pilot, lambda: [n.id for n in client.notifications.items] == ["n1"])


async def test_a_message_the_inbox_sends_on_is_sent_where_it_went(app, client):
    client.conversations.items.append(
        Conversation("owner:taxes", "Taxes", "2026-10-01T09:00:00+00:00", "2026-10-01T09:00:00+00:00")
    )
    client.dispatch_to = Dispatched("d1", "owner:taxes", "Taxes", "what about my taxes?", "→ Continued in “Taxes”.")
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"what about my taxes?", "enter")
        await wait_for(pilot, lambda: len(client.sent) == 2 and not app._busy)
        assert client.sent[1] == ("owner:taxes ← d1", [])
        assert app.sub_title == "Taxes"
        replies = [m.source for m in app.query(AssistantMessage)]
        assert replies[-1] == "On it."


async def test_move_asks_in_the_inbox_and_sends_the_message_where_it_goes_now(app, client):
    client.conversations.items.append(
        Conversation("owner:taxes", "Taxes", "2026-10-01T09:00:00+00:00", "2026-10-01T09:00:00+00:00")
    )
    client.dispatch_to = Dispatched("d1", "owner:taxes", "Taxes", "what about my taxes?", "→ Moved it to “Taxes”.")
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/move", "enter")
        await wait_for(pilot, lambda: len(client.sent) == 2 and not app._busy)
        assert client.sent == [("owner:abc moves ", []), ("owner:taxes ← d1", [])]
        assert app.sub_title == "Taxes"


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
        await wait_for(pilot, lambda: app.sub_title == "new conversation" and not app._busy)
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
        assert app.sub_title == "new conversation" and client.sent[0][0] == "Get to know me."


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


async def test_a_handed_off_agents_steps_show_as_lines_inside_its_call(app, client, monkeypatch):
    async def send(session, text, attachments=()):
        yield ToolStarted("Claude Code", {"folder": "/repo"}, id="h1")
        yield ToolStarted("Bash: pytest", {}, within="h1")
        yield ToolFinished("Bash: pytest", "", within="h1")
        yield ToolFinished("Claude Code", "Replied, working in /repo")
        yield Done()

    monkeypatch.setattr(client, "send", send)
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"run the tests", "enter")
        await wait_for(pilot, lambda: not app._busy and app.query(ToolCall))
        call, step = app.query(ToolCall)
        assert call.title == "✓ Claude Code(/repo) · 1 step" and step.title == "✓ Bash: pytest"


async def test_a_handed_off_agent_shows_its_thinking_text_and_tool_calls_in_order(app, client, monkeypatch):
    async def send(session, text, attachments=()):
        yield Thinking("The test expects a list.")
        yield Thinking("\nLet me check.")  # it streams: one note
        yield TextDelta("Running the tests.")
        yield ToolStarted("Bash", {"detail": "pytest -q"}, id="t1")
        yield ToolFinished("Bash", "1 failed")
        yield TextDelta("Fixed it.")
        yield Done()

    monkeypatch.setattr(client, "send", send)
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"run the tests", "enter")
        await wait_for(pilot, lambda: not app._busy and app.query(ToolCall))
        chat = app.query_one("#chat")
        shown = [type(w) for w in chat.children]
        assert shown[-4:] == [ThinkingNote, AssistantMessage, ToolCall, AssistantMessage]
        note = app.query_one(ThinkingNote)
        assert note.title == "✻ The test expects a list."
        note.collapsed = False
        await pilot.pause()
        assert note.title == "✻ Thinking"  # the whole text shows below, so the first line isn't repeated
        assert app.query_one(ToolCall).title == "✓ Bash(pytest -q)"


async def test_an_approval_a_run_started_elsewhere_waits_for_is_asked_on_opening_its_conversation(app, client):
    from assistant.core.agent import Conversation
    from assistant.core.events import ApprovalRequired

    at = "2030-01-01T09:00:00+00:00"
    client.conversations.items.append(Conversation("owner:b", "clean up", at, at))
    request = {"tool": "bash", "command": "rm -rf build", "reason": "recursive delete"}
    client.conversations.waiting["owner:b"] = [ApprovalRequired("i9", request)]
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/conversations", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConversationsScreen))
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ApprovalScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: client.decisions is not None and not app._busy)
        assert client.decisions == {"i9": {"approved": True, "reason": None}}


async def test_a_run_that_ends_in_this_conversation_is_asked_about_when_it_waits(app, client):
    from assistant.core.events import ApprovalRequired

    request = {"tool": "bash", "command": "rm -rf build", "reason": "recursive delete"}
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        client.conversations.waiting[app._live.session.thread_id] = [ApprovalRequired("i8", request)]
        run = {"run_id": "r1", "thread_id": app._live.session.thread_id, "channel": "telegram", "status": "ok"}
        await client.bus.put(("run_finished", run | {"reply": ""}))
        await wait_for(pilot, lambda: isinstance(app.screen, ApprovalScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: client.decisions is not None and not app._busy)
        assert client.decisions["i8"]["approved"] is False


async def test_a_follow_up_run_shows_what_it_follows_up_on_as_it_starts(app, client):
    from assistant_terminal.tui.widgets import FollowUpNote

    async def follow_up():
        yield TextDelta("The conversion failed; I'll retry with a smaller file.")
        yield Done()

    client.runs["r2"] = follow_up
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        thread_id = app._live.session.thread_id
        run = {"run_id": "r2", "thread_id": thread_id, "channel": "web", "client_id": "", "text": ""}
        await client.bus.put(("run", run | {"notice": "⚠️ convert: it failed"}))
        await wait_for(pilot, lambda: app.query(FollowUpNote) and app.query(AssistantMessage))
        assert "convert: it failed" in str(app.query_one(FollowUpNote).render())


async def test_a_conversation_opened_while_its_reply_runs_shows_it_from_its_start_once(app, client):
    from assistant.core.agent import ShownMessage

    release = asyncio.Event()

    async def running():
        yield TextDelta("Booking the hotel.")
        await release.wait()
        yield Done()

    client.conversations.items.append(replace(client.conversations.items[0], thread_id="owner:trip", title="Trip"))
    client.conversations.said["owner:trip"] = [ShownMessage("user", "find flights"), ShownMessage("assistant", "Two.")]
    run = {"run_id": "r1", "thread_id": "owner:trip", "channel": "telegram", "client_id": "", "text": "and a hotel"}
    client.conversations.in_progress["owner:trip"] = [run]
    client.runs["r1"] = running
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        await app._resume("owner:trip")
        await wait_for(pilot, lambda: len(app.query(AssistantMessage)) == 2)
        await client.bus.put(("run", run))  # its announcement, heard after: it shows once
        release.set()
        await pilot.pause(0.3)
        users = [str(m.render()) for m in app.query(UserMessage)]
        assert users == ["> find flights", "> [telegram] and a hotel"]
        assert len(app.query(AssistantMessage)) == 2


async def test_the_inbox_shows_its_reply_in_progress_at_start(app, client):
    async def running():
        yield TextDelta("It's 4 pm.")
        yield Done()

    run = {"run_id": "r1", "thread_id": "owner:abc", "channel": "web", "client_id": "", "text": "what time is it?"}
    client.conversations.in_progress["owner:abc"] = [run]
    client.runs["r1"] = running
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: app.query(AssistantMessage))
        assert "[web] what time is it?" in str(app.query(UserMessage).last().render())


def _waiting_in_b(client):
    """A conversation whose run waits on an approval, as `owner:b`."""
    from assistant.core.agent import Conversation
    from assistant.core.events import ApprovalRequired

    at = "2030-01-01T09:00:00+00:00"
    client.conversations.items.append(Conversation("owner:b", "clean up", at, at))
    request = {"tool": "bash", "command": "rm -rf build", "reason": "recursive delete"}
    client.conversations.waiting["owner:b"] = [ApprovalRequired("i9", request)]


async def _answer_in_b(app, pilot):
    await app._resume("owner:b")
    await wait_for(pilot, lambda: isinstance(app.screen, ApprovalScreen))
    await pilot.press("y")


async def test_leaving_while_an_answered_approval_runs_stops_showing_it(app, client):
    from assistant.core.events import ApprovalRequired

    _waiting_in_b(client)
    release, resumed = asyncio.Event(), []

    async def resume(session, decisions):
        resumed.append(session.thread_id)
        yield TextDelta("Cleaning ")
        await release.wait()
        yield TextDelta("up.")
        yield ApprovalRequired("i10", {"tool": "bash", "command": "rm -rf dist", "reason": "again"})

    client.resume = resume
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        await _answer_in_b(app, pilot)
        await wait_for(pilot, lambda: app.query(AssistantMessage))
        await pilot.press(*"/new", "enter")
        await wait_for(pilot, lambda: app.sub_title == "new conversation" and not app._busy)
        release.set()
        await pilot.pause(0.3)
        assert not app.query(AssistantMessage)
        assert not isinstance(app.screen, ApprovalScreen)
        assert resumed == ["owner:b"]
        await pilot.press(*"hi", "enter")
        await wait_for(pilot, lambda: client.sent and client.sent[-1][0] == "hi")


async def test_leaving_while_the_approvals_are_read_asks_nothing_in_the_next_conversation(app, client):
    _waiting_in_b(client)
    reading = asyncio.Event()
    pending = client.conversations.pending_approvals

    async def slow(thread_id):
        await reading.wait()
        return await pending(thread_id)

    client.conversations.pending_approvals = slow
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        await app._resume("owner:b")
        await pilot.press(*"/new", "enter")
        await wait_for(pilot, lambda: app.sub_title == "new conversation")
        reading.set()
        await pilot.pause(0.3)
        assert not isinstance(app.screen, ApprovalScreen)
        assert client.decisions is None


async def test_a_run_finished_while_an_approval_is_asked_doesnt_replace_the_dialog(app, client):
    _waiting_in_b(client)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        await app._resume("owner:b")
        await wait_for(pilot, lambda: isinstance(app.screen, ApprovalScreen))
        run = {"run_id": "r1", "thread_id": "owner:b", "channel": "telegram", "status": "ok", "reply": ""}
        await client.bus.put(("run_finished", run))
        await pilot.pause(0.2)
        await pilot.press("y")
        await wait_for(pilot, lambda: client.decisions is not None and not app._busy)
        assert client.decisions == {"i9": {"approved": True, "reason": None}}
        assert not isinstance(app.screen, ApprovalScreen)
        # The answered run went on to its end here: memory read again after it.
        assert "backend engineer" in str(app.query_one("#memory-body").render())


async def test_the_run_finished_of_the_answer_running_here_lets_it_end(app, client):
    _waiting_in_b(client)
    release = asyncio.Event()

    async def resume(session, decisions):
        client.decisions = decisions
        yield TextDelta("Cleaned up.")
        await release.wait()
        client.memory.profile = {"work": ["backend engineer"]}
        yield Done()

    client.resume = resume
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        await _answer_in_b(app, pilot)
        await wait_for(pilot, lambda: app.query(AssistantMessage))
        run = {"run_id": "r2", "thread_id": "owner:b", "channel": "cli", "status": "ok", "reply": "Cleaned up."}
        await client.bus.put(("run_finished", run))
        await pilot.pause(0.2)
        release.set()
        await wait_for(pilot, lambda: "backend engineer" in str(app.query_one("#memory-body").render()))
        assert not app._busy


async def test_an_approval_answered_in_another_app_closes_the_dialog_and_shows_its_run(app, client):
    _waiting_in_b(client)

    async def answered_there():
        yield TextDelta("Deleted build.")
        yield Done()

    client.runs["r3"] = answered_there
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        await app._resume("owner:b")
        await wait_for(pilot, lambda: isinstance(app.screen, ApprovalScreen))
        run = {"run_id": "r3", "thread_id": "owner:b", "channel": "web", "client_id": "other", "text": ""}
        await client.bus.put(("run", run))
        await wait_for(pilot, lambda: not isinstance(app.screen, ApprovalScreen) and not app._busy)
        await wait_for(pilot, lambda: app.query(AssistantMessage))
        assert client.decisions is None


async def test_a_run_started_as_the_app_starts_shows_though_it_began_before_listening(app, client):
    async def running():
        yield TextDelta("It's 4 pm.")
        yield Done()

    run = {"run_id": "r1", "thread_id": "owner:abc", "channel": "web", "client_id": "", "text": "what time is it?"}
    client.runs["r1"] = running
    events = client.events

    def started_just_before_the_stream_opened(on_open=lambda: None, on_lost=lambda: None):
        # The run began after the app read the conversations, before it listened: its announcement is gone.
        client.conversations.in_progress["owner:abc"] = [run]
        return events(on_open, on_lost)

    client.events = started_just_before_the_stream_opened
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_for(pilot, lambda: app.query(AssistantMessage))
        assert "[web] what time is it?" in str(app.query(UserMessage).last().render())


async def test_an_unreachable_daemon_while_reading_the_agents_keeps_the_events_coming(app, client):
    async def unreachable():
        raise DaemonUnavailableError("Lost the connection to the daemon.")

    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        client.conversations.agents = unreachable
        await client.bus.put(("mcp", {}))
        await wait_for(pilot, lambda: any("Lost the connection" in str(n.message) for n in app._notifications))
        client.memory.profile = {"work": ["programmer"]}
        await client.bus.put(("memory", {}))
        await wait_for(pilot, lambda: "programmer" in str(app.query_one("#memory-body").render()))
