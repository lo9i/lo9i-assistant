"""The system prompt texts the user can edit from the app (Settings → System prompt): the persona, the
operating instructions and the channel hints. The others are left out: they are templates the code fills
in, or say how a feature works, so an edit could break it.

An edit is kept as a file (prompts.edit_path) and used instead of the built-in text. Saving the built-in
text, or resetting, removes the file, so a later update of the built-in text applies again. Each epoch
records a digest of the texts its system prompt was built with (epochs.py); when it changes, the next
user message starts a new epoch with nothing summarized, as with a rename.
"""

import asyncio
import hashlib
import os
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass

from assistant.core.conversation import prompts
from assistant.core.conversation.prompts import UnreadableEditError

_ABOUT = {
    "persona": ("Persona", "Who the assistant is and how it behaves. It opens the system prompt."),
    "operating": (
        "Operating instructions",
        "How it works: where it runs, conversations and the inbox, keeping memory, checking before it claims "
        "something.",
    ),
    "channels": (
        "Channels",
        "How to write in each app. The chat channels installed as plugins add their own lines after it.",
    ),
}


@dataclass(frozen=True)
class PromptSection:
    name: str
    title: str
    description: str
    # What the assistant uses: the user's edit, or the built-in text.
    text: str
    default: str
    # There is an edit, so it can be reset: a different text, or a file that can't be read.
    edited: bool
    # Why the edit can't be used (a file that isn't UTF-8 or can't be read); the built-in text is used meanwhile.
    problem: str = ""


class UnknownPromptError(LookupError):
    """A prompt that isn't one the user can edit."""


class PromptEditError(ValueError):
    """An empty text, or an edit that can't be written or deleted."""


async def sections() -> list[PromptSection]:
    return [await section(name) for name in prompts.EDITABLE]


async def section(name: str) -> PromptSection:
    """Raises UnknownPromptError."""
    title, description = _about(name)
    default = prompts.default(name)
    try:
        text = await asyncio.to_thread(prompts.edited, name) or default
    except UnreadableEditError as e:
        return PromptSection(name, title, description, default, default, True, str(e))
    return PromptSection(name, title, description, text, default, text != default)


async def save(name: str, text: str) -> PromptSection:
    """Used from the next user message in each conversation. Saving over an edit that can't be read replaces
    it. Raises UnknownPromptError, PromptEditError."""
    _about(name)
    text = text.strip()
    if not text:
        raise PromptEditError("The text can't be empty. Reset it to use the built-in one.")
    if text == prompts.default(name):
        return await reset(name)
    await _changing(name, asyncio.to_thread(_write, name, text))
    return await section(name)


async def reset(name: str) -> PromptSection:
    """Back to the built-in text, also when the edit can't be read. Raises UnknownPromptError, PromptEditError."""
    _about(name)
    await _changing(name, asyncio.to_thread(prompts.edit_path(name).unlink, missing_ok=True))
    return await section(name)


async def _changing(name: str, change: Awaitable[None]) -> None:
    try:
        await change
    except OSError as e:
        raise PromptEditError(f"Can't change {prompts.edit_path(name)}: {e.strerror or e}.") from e


async def current() -> dict[str, str]:
    """The texts in use, by name."""
    return {name: await asyncio.to_thread(prompts.load, name) for name in prompts.EDITABLE}


def digest(texts: Mapping[str, str]) -> str:
    """Tells whether the texts changed, without keeping them in every checkpoint."""
    joined = "\0".join(f"{name}\0{texts[name]}" for name in sorted(texts))
    return hashlib.sha256(joined.encode()).hexdigest()


def _about(name: str) -> tuple[str, str]:
    if name not in _ABOUT:
        raise UnknownPromptError(f"No editable prompt named {name}. Choose one of: {', '.join(prompts.EDITABLE)}.")
    return _ABOUT[name]


def _write(name: str, text: str) -> None:
    """Written whole and then moved into place, so a turn starting meanwhile never reads half of it."""
    path = prompts.edit_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(f"{text}\n", encoding="utf-8")
    os.replace(partial, path)
