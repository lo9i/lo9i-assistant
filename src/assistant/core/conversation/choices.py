"""Answer buttons: a reply that ends with a question with a few clear answers lists them in a marker at its
end, `<!-- choices: Yes | No -->` (prompts/operating.md). The marker never shows; its choices do, while the reply
is the conversation's last message: as buttons under the reply in the web app (clients/web/src/lib/chat/choices.ts)
and the chat channels (core/channels/chat/answers.py), numbered under it in the terminal app. History keeps it, so the
model sees what it wrote."""

import re

_MARKER = re.compile(r"<!--\s*choices:.*?-->", re.IGNORECASE | re.DOTALL)
_ENDING = re.compile(r"<!--\s*choices:((?:(?!-->).)*)-->\s*\Z", re.IGNORECASE | re.DOTALL)
# A comment still open at the end, or its first characters: while the reply streams it may become a marker.
_OPENING = re.compile(r"(<!--(?:(?!-->).)*|<!-?)\Z", re.DOTALL)


def offered(text: str) -> list[str]:
    """The choices the marker at the end of `text` lists; none without one."""
    ending = _ENDING.search(text)
    return [choice.strip() for choice in ending.group(1).split("|") if choice.strip()] if ending else []


def without_markers(text: str) -> str:
    """`text` as the user reads it: without its markers, nor what may be the start of one at its end."""
    return _OPENING.sub("", _MARKER.sub("", text))


class Streamed:
    """A reply's text as it streams, for a view that only appends: `add` gives back what's new to show.
    A marker's first characters wait until the text after them shows whether they are one."""

    def __init__(self) -> None:
        self._text = ""
        self._shown = ""

    def add(self, text: str) -> str:
        self._text += text
        # Markers only ever come out of what was held back, so what's shown is always the start of this.
        shown = without_markers(self._text)
        new, self._shown = shown[len(self._shown) :], shown
        return new
