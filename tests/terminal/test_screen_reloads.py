"""Each screen that reloads says which daemon events change what it shows (`RELOADS_ON`), and reloads on those
only (AssistantApp.reload_screen)."""

import inspect
from typing import cast

from assistant_terminal.tui import screens
from assistant_terminal.tui.live import LiveApp, handlers


class _App:
    """Records which screens an event reloads; the rest of what the app does is left out."""

    def __init__(self) -> None:
        self.reloaded: list[str] = []

    def reload_screen(self, kind: str) -> None:
        self.reloaded.append(kind)

    def __getattr__(self, name: str):
        async def nothing(*_):
            return None

        return nothing


def _reloading() -> list[type]:
    return [cls for _, cls in inspect.getmembers(screens, inspect.isclass) if hasattr(cls, "reload")]


def test_every_screen_that_reloads_names_events_the_app_hears():
    heard = set(handlers(cast(LiveApp, _App())))
    for screen in _reloading():
        reloads_on = getattr(screen, "RELOADS_ON", None)
        assert reloads_on, f"{screen.__name__} reloads but doesn't say on which events"
        assert reloads_on <= heard, f"{screen.__name__} waits for events no handler passes on"


async def test_skills_memory_and_health_checks_reload_the_screens_showing_them():
    app = _App()
    on = handlers(cast(LiveApp, app))
    for kind in ("skills", "memory", "doctor"):
        result = on[kind]({})
        if result is not None:
            await result
    assert app.reloaded == ["skills", "memory", "doctor"]
    assert "skills" in screens.PluginsScreen.RELOADS_ON and "skills" in screens.SkillsScreen.RELOADS_ON
