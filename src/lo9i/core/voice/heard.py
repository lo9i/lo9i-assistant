"""What's said in a call, as lines in the order it was said. The call's events (daemon/voice_calls.py) tell the
items of its conversation as they're added, and their words later: the voice's when its transcript is done, the
user's when the transcription of what they said completes, which runs apart from the model and may finish after the
voice already answered. A line comes out once its words and those of every item before it are known."""

from dataclasses import dataclass
from typing import Any, Literal

Who = Literal["user", "voice"]

_ROLES: dict[str, Who] = {"user": "user", "assistant": "voice"}


@dataclass(frozen=True)
class Line:
    who: Who
    text: str


class Heard:
    def __init__(self) -> None:
        # The call's message items not yet out, in the call's order, with their words once known.
        self._items: list[str] = []
        self._who: dict[str, Who] = {}
        self._words: dict[str, str] = {}

    def added(self, item: dict[str, Any]) -> None:
        """An item the call added (`conversation.item.added`): only messages of the user and the voice are lines."""
        who = _ROLES.get(item.get("role", ""))
        if item.get("type") == "message" and who is not None and item.get("id") not in self._who:
            self._items.append(item["id"])
            self._who[item["id"]] = who

    def heard(self, item_id: str, who: Who, text: str) -> None:
        """The words of an item; one whose addition never came goes after those known. Words already known stay."""
        if item_id not in self._who:
            self.added({"type": "message", "id": item_id, "role": "user" if who == "user" else "assistant"})
        self._words.setdefault(item_id, text.strip())

    def ready(self) -> list[Line]:
        """The lines whose words, and those of every line before them, are known; each comes out once."""
        done = 0
        while done < len(self._items) and self._items[done] in self._words:
            done += 1
        return self._take(self._items[:done])

    def rest(self) -> list[Line]:
        """At the call's end: every line whose words are known, in order; those never heard are left out."""
        return self._take([item for item in self._items if item in self._words])

    def _take(self, items: list[str]) -> list[Line]:
        lines = [Line(self._who[item], self._words[item]) for item in items]
        taken = set(items)
        self._items = [item for item in self._items if item not in taken]
        return [line for line in lines if line.text]
