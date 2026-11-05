from textual.widgets import Button, Markdown, Select, SelectionList

from lo9i_terminal.tui.screens import SpeechToTextSection, SpokenRepliesSection
from tests.terminal.conftest import wait_for, wait_for_section


async def test_speech_to_text_and_spoken_replies_are_saved(app, client):
    async with app.run_test(size=(110, 50)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/audio", "enter")
        screen = await wait_for_section(pilot, app, SpeechToTextSection)
        spoken = await wait_for_section(pilot, app, SpokenRepliesSection)  # its card beside it, as the web app's

        def body() -> str:
            return screen.query_one("#audio-body", Markdown).source

        def spoken_body() -> str:
            return spoken.query_one("#spoken-body", Markdown).source

        await wait_for(pilot, lambda: "`small`, accurate, detected as Spanish, English" in body())
        screen.query_one("#audio-model", Select).value = "tiny"
        screen.query_one("#audio-decoding", Select).value = "fast"
        screen.query_one("#audio-languages", SelectionList).deselect("en")
        screen.query_one("#save-stt", Button).press()
        await wait_for(pilot, lambda: "`tiny`, fast, detected as Spanish" in body())
        assert (client.speech.state.model, client.speech.state.decoding) == ("tiny", "fast")
        screen.query_one("#audio-languages", SelectionList).deselect("es")
        screen.query_one("#save-stt", Button).press()
        await wait_for(pilot, lambda: "at least one language" in body())
        spoken.query_one("#audio-spoken", Select).value = "voice"
        spoken.query_one("#audio-voice", Select).value = "af_heart"
        spoken.query_one("#save-replies", Button).press()
        await wait_for(pilot, lambda: "Speak replies to voice messages" in spoken_body())
        assert (client.speech.state.spoken_replies, client.speech.state.voice) == ("voice", "af_heart")
