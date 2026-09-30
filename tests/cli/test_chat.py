"""The terminal app: a turn with tool calls, the approval dialog, memory panel and new conversation."""

from assistant.client import DaemonUnavailableError
from assistant.gateways.cli.tui.screens import ApprovalScreen
from assistant.gateways.cli.tui.widgets import AssistantMessage, ToolCall, UserMessage
from tests.cli.conftest import wait_for


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
    from tests.cli.conftest import wait_for

    async def telegram_run():
        yield TextDelta("It's Tuesday.")
        yield Done()

    async with app.run_test() as pilot:

        def memory() -> str:
            return str(app.query_one("#memory-body").render())

        client.memory.profile = {"work": ["programmer"]}  # e.g. an archive finishing after /new
        await client.bus.put(("memory", {}))
        await wait_for(pilot, lambda: "programmer" in memory())

        client.runs["r1"] = telegram_run  # a message sent from Telegram
        await client.bus.put(
            ("run", {"run_id": "r1", "thread_id": "owner:abc", "channel": "telegram", "text": "what day is it?"})
        )
        await wait_for(pilot, lambda: len(app.query(AssistantMessage)) == 1)
        assert "[telegram] what day is it?" in str(app.query(UserMessage).first().render())

        client.active_thread = "owner:other"  # /new from Telegram
        await client.bus.put(("threads", {}))
        await wait_for(pilot, lambda: app.sub_title == "owner:other")
        assert len(app.query_one("#chat").children) == 0


async def test_new_leaves_a_running_reply_and_reports_when_it_finishes(app, client):
    import asyncio

    from tests.cli.conftest import wait_for

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
