"""The apps' About you step, at first run and from Settings: the user's name, the language and length of
replies, and what they mainly want help with. Each answer is one profile item starting with its own label,
so the step reads its answers back from the profile (to show them again, and to know there's no name yet),
and the get-to-know-you offer (core/conversation/introduction.py) knows when nothing else is there."""

from dataclasses import dataclass, field
from typing import Literal

from assistant.core.memory.profile import MAX_ITEMS, Profile, Section

HelpTopic = Literal["email", "calendar", "coding", "expenses", "media", "hosts"]
ReplyLength = Literal["short", "detailed"]

# How each answer reads in the profile, which the system prompt shows in English.
_TOPICS: dict[HelpTopic, str] = {
    "email": "email",
    "calendar": "calendar",
    "coding": "coding",
    "expenses": "expenses",
    "media": "movies and YouTube",
    "hosts": "servers and hosts",
}
_LENGTHS: dict[ReplyLength, str] = {"short": "short and to the point", "detailed": "detailed, with explanations"}

_NAME = "Name: "
_LANGUAGE = "Reply language: "
_LENGTH = "Reply length: "
_HELP = "Wants help with: "
_OTHER_HELP = "Also wants help with: "
_LABELS: list[tuple[Section, str]] = [
    ("about", _NAME),
    ("how_to_reply", _LANGUAGE),
    ("how_to_reply", _LENGTH),
    ("goals", _HELP),
    ("goals", _OTHER_HELP),
]


@dataclass(frozen=True)
class AboutYou:
    """The step's answers; only the name is required to save them."""

    name: str = ""
    language: str = ""
    reply_length: ReplyLength | None = None
    help_with: list[HelpTopic] = field(default_factory=list)
    other_help: str = ""


def name(profile: Profile) -> str:
    """The user's name as the profile says it ("Name: …"), or ""."""
    return _value(profile.about, _NAME)


def read(profile: Profile) -> AboutYou:
    """The answers the profile holds, to show the step with them again."""
    length = _value(profile.how_to_reply, _LENGTH)
    topics: dict[str, HelpTopic] = {text: topic for topic, text in _TOPICS.items()}
    return AboutYou(
        name=name(profile),
        language=_value(profile.how_to_reply, _LANGUAGE),
        reply_length=next((key for key, text in _LENGTHS.items() if text == length), None),
        help_with=[topics[t] for t in _value(profile.goals, _HELP).split(", ") if t in topics],
        other_help=_value(profile.goals, _OTHER_HELP),
    )


def written(profile: Profile, answers: AboutYou) -> tuple[Profile, list[str]]:
    """The profile with the answers in place of the ones it had: each where its item was, a new one first in
    its section, an empty one taken out. Items pushed past a section's limit come back too, to keep as facts."""
    sections = profile.model_dump()
    overflow: list[str] = []
    for (section, label), value in reversed(list(zip(_LABELS, _values(answers), strict=True))):
        items = _replaced(sections[section], label, value)
        sections[section] = items[:MAX_ITEMS]
        overflow += items[MAX_ITEMS:]
    return Profile.model_validate(sections), overflow


def only_answers(profile: Profile) -> bool:
    """Whether the profile holds nothing but the step's answers, or nothing at all."""
    return all(_labelled(item) for items in profile.model_dump().values() for item in items)


def _values(answers: AboutYou) -> list[str]:
    """In the order of _LABELS."""
    return [
        answers.name.strip(),
        answers.language.strip(),
        _LENGTHS[answers.reply_length] if answers.reply_length else "",
        ", ".join(_TOPICS[t] for t in dict.fromkeys(answers.help_with)),
        answers.other_help.strip(),
    ]


def _replaced(items: list[str], label: str, value: str) -> list[str]:
    new = [f"{label}{value}"] if value else []
    at = next((i for i, item in enumerate(items) if _starts(item, label)), None)
    return [*new, *items] if at is None else [*items[:at], *new, *items[at + 1 :]]


def _value(items: list[str], label: str) -> str:
    return next((item[len(label) :].strip() for item in items if _starts(item, label)), "")


def _labelled(item: str) -> bool:
    return any(_starts(item, label) for _, label in _LABELS)


def _starts(item: str, label: str) -> bool:
    """The assistant may write the name's label in another case ("name: Ana")."""
    return item.lower().startswith(label.lower())
