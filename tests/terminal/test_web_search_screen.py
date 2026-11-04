from textual.widgets import Input, Markdown

from assistant_terminal.tui.screens import WebSearchSection
from tests.terminal.conftest import wait_for, wait_for_section


async def test_set_and_remove_the_brave_key(app, client):
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/websearch", "enter")
        await wait_for_section(pilot, app, WebSearchSection)

        def body() -> str:
            return app.screen.query_one("#web-search-body", Markdown).source

        key = app.screen.query_one("#web-search-key", Input)
        assert key.password and "public engines" in body()
        key.focus()
        key.value = "bad"
        await pilot.press("enter")
        await wait_for(pilot, lambda: "Unauthorized" in body())
        key.value = "GOOD"
        await pilot.press("enter")
        await wait_for(pilot, lambda: "use the Brave Search API" in body())
        assert key.value == "" and not key.display
        await pilot.click("#remove")
        await wait_for(pilot, lambda: not client.web_search.state.brave_key_set and key.display)
