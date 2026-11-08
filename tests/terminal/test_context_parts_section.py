"""/context: what a new conversation's context is made of, largest part first, as Settings → System shows it."""

from textual.widgets import Markdown, Static

from lo9i_terminal.tui.screens import ContextPartsSection
from tests.terminal.conftest import wait_for, wait_for_section


async def test_the_parts_show_largest_first_with_their_share(app, client):
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/context", "enter")
        section = await wait_for_section(pilot, app, ContextPartsSection)
        body = section.query_one("#context-parts-body", Markdown)
        await wait_for(pilot, lambda: "8% of the 150k window" in body.source)
        bars = str(section.query_one("#context-parts-bars", Static).render())
        assert bars.index("Saved facts") < bars.index("Skills")
        assert "3.1k" in bars and "78%" in bars
