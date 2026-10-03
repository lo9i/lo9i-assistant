from textual.widgets import Button, Input, Markdown, Select

from assistant_terminal.tui.screens import ModelScreen
from tests.terminal.conftest import wait_for


async def _open(pilot, app) -> ModelScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/model", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, ModelScreen))
    return app.screen


async def test_switch_to_copilot_after_a_failed_test_then_back_to_env(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app)

        def body() -> str:
            return screen.query_one("#model-body", Markdown).source

        await wait_for(pilot, lambda: "Anthropic (from .env)" in body())
        assert not screen.query_one("#reset").display
        screen.query_one("#model-provider", Select).value = "copilot"
        main = screen.query_one("#model-main", Input)
        await wait_for(pilot, lambda: main.value == "claude-opus-5.5" and len(_fields(screen)) == 1)
        [key] = _fields(screen)
        assert key.password and key.placeholder == "GitHub token"
        key.value = "bad"
        screen.query_one("#save", Button).press()
        await wait_for(pilot, lambda: "401 invalid key" in body())
        _fields(screen)[0].value = "gh-token"
        screen.query_one("#save", Button).press()
        await wait_for(pilot, lambda: "GitHub Copilot (set here)" in body())
        assert client.model.saved == ("copilot", {"api_key": "gh-token"}, "claude-opus-5.5", "claude-sonnet-5.5")
        await wait_for(pilot, lambda: _fields(screen)[0].value == "")  # never kept on screen
        assert "saved; leave empty" in _fields(screen)[0].placeholder
        screen.query_one("#reset", Button).press()
        await wait_for(pilot, lambda: "Anthropic (from .env)" in body())


def _fields(screen) -> list[Input]:
    return list(screen.query("#model-fields Input").results(Input))


async def test_each_provider_asks_for_its_own_fields(app, client):
    async with app.run_test(size=(110, 50)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#model-provider", Select).value = "openai"
        await wait_for(pilot, lambda: len(_fields(screen)) == 2)
        assert _fields(screen)[1].placeholder == "Server URL (optional)" and not _fields(screen)[1].password
        assert screen.query_one("#model-main", Input).value == ""
        screen.query_one("#model-provider", Select).value = "bedrock_converse"
        await wait_for(pilot, lambda: len(_fields(screen)) == 3)
        assert [f.password for f in _fields(screen)] == [False, True, True]
        screen.query_one("#model-provider", Select).value = "groq"
        help_text = screen.query_one("#model-help", Markdown)
        await wait_for(pilot, lambda: "Saving installs `langchain-groq" in help_text.source)
        _fields(screen)[0].value = "gsk"
        for name, value in (("main", "llama"), ("worker", "llama")):
            screen.query_one(f"#model-{name}", Input).value = value
        screen.query_one("#save", Button).press()
        await wait_for(pilot, lambda: client.model.saved == ("groq", {"api_key": "gsk"}, "llama", "llama"))
