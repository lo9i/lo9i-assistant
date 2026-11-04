"""Terminal app preferences the user changes from inside the app (/mouse, F4 for the sidebar), kept by the client
across sessions in a small JSON file."""

import json
from pathlib import Path


class Preferences:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._values = self._load()

    @property
    def mouse(self) -> bool:
        """Clicks in the app. Off inside a multiplexer (tmux, herdr) lets it keep mouse control of
        its panes, and lets a plain drag select text."""
        return bool(self._values.get("mouse", True))

    def set_mouse(self, on: bool) -> None:
        self._values["mouse"] = on
        self._save()

    @property
    def sidebar_collapsed(self) -> bool:
        """The navigation on the left shown by its glyphs only (F4), leaving the page more room."""
        return bool(self._values.get("sidebar_collapsed", False))

    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        self._values["sidebar_collapsed"] = collapsed
        self._save()

    def _load(self) -> dict[str, object]:
        """A missing or unreadable file means the defaults; the next change rewrites it."""
        try:
            values = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return values if isinstance(values, dict) else {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._values, indent=2) + "\n", encoding="utf-8")
