"""/mouse: the choice is saved for the next start, and switched on the fly when Textual allows it."""

from textual.app import App
from textual.drivers.linux_driver import LinuxDriver

from assistant.gateways.cli.preferences import Preferences
from assistant.gateways.cli.tui.mouse import switch_mouse
from assistant.gateways.cli.tui.widgets import MouseStatus
from tests.cli.conftest import wait_for


def test_preferences_are_kept_across_sessions(tmp_path):
    path = tmp_path / "cli_preferences.json"
    assert Preferences(path).mouse
    Preferences(path).set_mouse(False)
    assert not Preferences(path).mouse
    path.write_text("not json")
    assert Preferences(path).mouse


async def test_the_terminal_driver_still_switches_mouse_capture(monkeypatch):
    """Guards the private Textual driver internals `switch_mouse` relies on."""
    app = App()
    driver = LinuxDriver(app, mouse=False)
    written: list[str] = []
    monkeypatch.setattr(driver, "write", written.append)
    monkeypatch.setattr(driver, "flush", lambda: None)
    app._driver = driver
    assert switch_mouse(app, True) and "\x1b[?1000h" in written and driver._mouse
    assert switch_mouse(app, False) and "\x1b[?1000l" in written and not driver._mouse


async def test_mouse_command_saves_and_asks_for_a_restart_when_it_cant_switch(app, tmp_path):
    async with app.run_test() as pilot:  # The test driver has no mouse switch.
        await pilot.click("#prompt")
        await pilot.press(*"/mouse off", "enter")
        await wait_for(pilot, lambda: not Preferences(tmp_path / "cli_preferences.json").mouse)
        assert any("next start" in str(n.message) for n in app._notifications)
        assert str(app.query_one(MouseStatus).render()) == "mouse on (off after restart)"
