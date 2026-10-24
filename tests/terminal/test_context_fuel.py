"""How full the conversation's context is, in the footer, as the web app's status bar shows it."""

from assistant.core.agent import ConversationStats
from assistant_terminal.context_text import compact, detail, fuel
from assistant_terminal.tui.widgets import ContextFuel
from tests.terminal.conftest import wait_for


def _stats(tokens: int, limit: int, agent: str = "") -> ConversationStats:
    return ConversationStats("t", 0, 0, 0, 0, 0, 0, None, None, tokens, limit, agent)


def test_the_bar_fills_and_turns_yellow_then_red():
    assert fuel(_stats(0, 200_000)).plain == "" and fuel(_stats(10, 0)).plain == ""
    quarter = fuel(_stats(50_000, 200_000))
    assert quarter.plain == "▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱ 25%" and "cyan" in str(quarter.spans[0].style)
    assert "#e5b931" in str(fuel(_stats(130_000, 200_000)).spans[0].style)
    assert fuel(_stats(400_000, 200_000)).plain.endswith("▰ 100%")
    assert fuel(_stats(90_000, 200_000, "Claude Code")).plain.startswith("Claude Code ▰")


def test_the_figures_say_whose_context_it_is():
    assert (
        detail(_stats(45_200, 200_000)) == "Context: 45k / 200k tokens. Older messages are summarized when it's full."
    )
    assert detail(_stats(1_500, 1_000_000, "Claude Code")).startswith("Claude Code's context: 1.5k / 1.0M tokens")
    assert (compact(999), compact(1_234), compact(45_600)) == ("999", "1.2k", "46k")


async def test_the_footer_shows_the_context_and_follows_each_reply(app, client):
    client.conversations.context["owner:abc"] = (50_000, 200_000, "")
    async with app.run_test(size=(120, 40)) as pilot:
        shown = app.query_one(ContextFuel)
        await wait_for(pilot, lambda: "25%" in str(shown.render()))
        client.conversations.context["owner:abc"] = (100_000, 200_000, "")
        await client.bus.put(
            ("run_finished", {"run_id": "r", "thread_id": "owner:abc", "channel": "web", "status": "ok", "reply": ""})
        )
        await wait_for(pilot, lambda: "50%" in str(shown.render()))
