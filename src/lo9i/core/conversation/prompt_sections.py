"""A section of the system prompt and the items it lists (a skill, a fact, a profile section), built together so the
text the model gets and its breakdown (the doctor's, core/doctor/context.py) can't drift apart."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

PromptPart = Literal[
    "persona",
    "name",
    "operating",
    "channels",
    "skills",
    "plugin_tools",
    "subagents",
    "pinned",
    "accounts",
    "plugins",
    "profile",
    "facts",
    "recent",
    "summary",
]

# How much of a text names an item that has no name of its own (a paragraph before any heading).
_NAME_CHARS = 60


@dataclass(frozen=True)
class PromptItem:
    """`text`: what the prompt holds for it; `detail`: what says what it is, when its name doesn't."""

    name: str
    text: str
    detail: str = ""


@dataclass(frozen=True)
class PromptSection:
    part: PromptPart
    text: str
    items: tuple[PromptItem, ...] = ()


def listed(part: PromptPart, head: str, items: Sequence[PromptItem], empty: str) -> PromptSection:
    """A section of one item a line after `head`, or `empty` without any."""
    lines = "\n".join(item.text for item in items)
    return PromptSection(part, f"{head}{lines or empty}", tuple(items))


def by_heading(part: PromptPart, text: str) -> PromptSection:
    """A text the user can edit, its items the parts its headings start."""
    return PromptSection(part, text, tuple(headed(text)))


def headed(text: str) -> list[PromptItem]:
    """The text in parts, each from a heading to the next; what comes before the first is named by its start."""
    chunks: list[list[str]] = []
    for line in text.splitlines():
        if line.startswith("#") or not chunks:
            chunks.append([])
        chunks[-1].append(line)
    return [_chunk(lines) for lines in chunks if "".join(lines).strip()]


def _chunk(lines: list[str]) -> PromptItem:
    first = next(line for line in lines if line.strip())
    name = first.lstrip("#").strip() if first.startswith("#") else _start(first)
    return PromptItem(name, "\n".join(lines))


def _start(line: str) -> str:
    line = line.strip()
    return line if len(line) <= _NAME_CHARS else line[:_NAME_CHARS].rstrip() + "…"
