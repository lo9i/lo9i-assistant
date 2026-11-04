"""/keys: what removed plugins left kept, deleted after confirming."""

from textual.widgets import Button, Markdown

from assistant.core.agent import KeptKeys
from assistant_terminal.tui.screens import ConfirmScreen, KeptKeysListSection
from tests.terminal.conftest import wait_for, wait_for_section

HELLO = KeptKeys("hello", ["HELLO_TOKEN", "HELLO_USER"])
TOKEN = KeptKeys("", [], "https://github.com/me/private-plugins", "me/private-plugins")


async def test_kept_keys_and_tokens_are_listed_and_deleted_after_confirming(app, client):
    client.repositories.kept = [HELLO, TOKEN]
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/keys", "enter")
        screen = await wait_for_section(pilot, app, KeptKeysListSection)

        def body() -> str:
            return screen.query_one("#keys-body", Markdown).source

        await wait_for(pilot, lambda: "`HELLO_TOKEN`" in body())
        screen.query_one("#delete", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: client.repositories.kept == [TOKEN] and "me/private-plugins" in body())
        screen.query_one("#delete", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: "Nothing kept" in body())
        assert not screen.query_one("#delete").display
