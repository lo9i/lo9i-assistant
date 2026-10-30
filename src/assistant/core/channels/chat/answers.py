"""A reply's choices (conversation/choices.py) as buttons in a chat, `ch:<choice>:<digest>`: pressing one sends its
text as the user's message, while that reply is still its conversation's last message. `digest` names the reply's
choices, so a press on an older reply's buttons isn't taken for the latest's."""

import hashlib
from dataclasses import dataclass

from assistant.core.channels.chat.port import Buttons

_CHOICE = "ch"


@dataclass(frozen=True)
class Pick:
    choice: int
    digest: str

    def of(self, offered: list[str]) -> str | None:
        """The choice it picks among the choices the conversation's last reply offers; None when that reply isn't the
        one the button was on."""
        if _digest(offered) != self.digest or not 0 <= self.choice < len(offered):
            return None
        return offered[self.choice]


def answer_buttons(offered: list[str]) -> Buttons:
    return [(choice, f"{_CHOICE}:{i}:{_digest(offered)}") for i, choice in enumerate(offered)]


def parse_pick(data: str) -> Pick | None:
    """None if `data` isn't an answer button."""
    action, _, rest = data.partition(":")
    choice, _, digest = rest.partition(":")
    if action != _CHOICE or not choice.isdigit() or not digest:
        return None
    return Pick(int(choice), digest)


def _digest(offered: list[str]) -> str:
    """Short, as Telegram's button data takes 64 bytes."""
    return hashlib.sha256("|".join(offered).encode()).hexdigest()[:8]
