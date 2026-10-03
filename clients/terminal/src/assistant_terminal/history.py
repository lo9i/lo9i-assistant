"""What the user typed in the chat, kept across sessions like a shell history, one entry per line.
Up and Down walk it; the text being typed is kept and comes back after the newest entry."""

from pathlib import Path


class History:
    def __init__(self, path: Path, limit: int) -> None:
        self._path = path
        self._limit = limit
        self._entries = self._load()
        self._position = len(self._entries)
        self._draft = ""

    def add(self, entry: str) -> None:
        """Remember a submitted entry (not a repeat of the last one) and stop browsing."""
        self._position = len(self._entries)
        if not entry or "\n" in entry or (self._entries and self._entries[-1] == entry):
            return
        self._entries = [*self._entries, entry][-self._limit :]
        self._position = len(self._entries)
        self._save()

    def previous(self, current: str) -> str | None:
        """The entry before the one shown, or None at the oldest. `current` is kept as the draft
        when browsing starts."""
        if self._position == 0:
            return None
        if self._position == len(self._entries):
            self._draft = current
        self._position -= 1
        return self._entries[self._position]

    def next(self) -> str | None:
        """The entry after the one shown, the draft after the newest, or None when not browsing."""
        if self._position == len(self._entries):
            return None
        self._position += 1
        return self._draft if self._position == len(self._entries) else self._entries[self._position]

    def is_recalled(self, text: str) -> bool:
        """True while `text` is exactly the entry browsing put in the input (not the draft)."""
        return self._position < len(self._entries) and text == self._entries[self._position]

    def _load(self) -> list[str]:
        if not self._path.is_file():
            return []
        return self._path.read_text(encoding="utf-8").splitlines()[-self._limit :]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("".join(f"{e}\n" for e in self._entries), encoding="utf-8")
