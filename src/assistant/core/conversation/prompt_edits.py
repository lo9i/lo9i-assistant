"""The system prompt texts the user can edit from the app (Settings → System prompt): the persona, the
operating instructions and the channel hints. The others are left out: they are templates the code fills
in, or say how a feature works, so an edit could break it.

An edit is kept as a file (prompts.edit_path) and used instead of the built-in text. Saving the built-in
text, or resetting, removes the file, so a later update of the built-in text applies again. The built-in text
an edit was made from is kept beside it (prompts.base_path): when an update changes the built-in text, the edit
still hides it, so the section says what changed (`built_in_changes`) until the user saves the edit again, keeps
it as it is (`keep`) or resets it. Each epoch
records a digest of the texts its system prompt was built with (epochs.py); when it changes, the next
user message starts a new epoch with nothing summarized, as with a rename.
"""

import asyncio
import difflib
import hashlib
import logging
import os
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from pathlib import Path

from assistant.core.conversation import prompts
from assistant.core.conversation.prompts import UnreadableEditError

logger = logging.getLogger(__name__)

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
    # How the built-in text changed since the edit was made from it, as a unified diff; "" when it didn't (or
    # there's no edit).
    built_in_changes: str = ""


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
    edited = text != default
    changes = await asyncio.to_thread(_changes_since_edit, name, default) if edited else ""
    return PromptSection(name, title, description, text, default, edited, built_in_changes=changes)


async def save(name: str, text: str) -> PromptSection:
    """Used from the next user message in each conversation. Saving over an edit that can't be read replaces
    it. Raises UnknownPromptError, PromptEditError."""
    _about(name)
    text = text.strip()
    if not text:
        raise PromptEditError("The text can't be empty. Reset it to use the built-in one.")
    if text == prompts.default(name):
        return await reset(name)
    await _changing(name, asyncio.to_thread(_write, prompts.edit_path(name), text))
    await asyncio.to_thread(_record_base, name)
    return await section(name)


async def keep(name: str) -> PromptSection:
    """Keeps the edit as it is after the built-in text changed: the change is seen, and not said again. Raises
    UnknownPromptError, PromptEditError."""
    _about(name)
    await _changing(name, asyncio.to_thread(_keep_base, name, replace=True))
    return await section(name)


async def reset(name: str) -> PromptSection:
    """Back to the built-in text, also when the edit can't be read. Raises UnknownPromptError, PromptEditError."""
    _about(name)
    await _changing(name, asyncio.to_thread(prompts.edit_path(name).unlink, missing_ok=True))
    await _changing(name, asyncio.to_thread(prompts.base_path(name).unlink, missing_ok=True))
    return await section(name)


async def keep_bases() -> None:
    """For edits made before the built-in text they came from was kept, or by hand: the one in use now, so a later
    change of it is said. Run at start; one that can't be written is logged and tried again at the next start, as
    it only tells of changes and must never stop the assistant."""
    for name in prompts.EDITABLE:
        try:
            await asyncio.to_thread(_keep_base, name, replace=False)
        except OSError as e:
            logger.warning("Can't record the built-in %s text its edit came from: %s", name, e)


def _record_base(name: str) -> None:
    """After saving an edit, which is in use from then on whether or not this works. A failure is logged and the
    record of an earlier edit goes with it, so no change the user has seen is said again."""
    try:
        _write(prompts.base_path(name), prompts.default(name))
    except OSError as e:
        logger.warning("Can't record the built-in %s text its edit came from: %s", name, e)
        _forget_base(name)


def _forget_base(name: str) -> None:
    try:
        prompts.base_path(name).unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Can't remove %s: %s", prompts.base_path(name), e)


def _keep_base(name: str, replace: bool) -> None:
    """Records the built-in text in use now as the one the edit came from, when there's an edit; with `replace`
    false, only when none was recorded."""
    if prompts.edit_path(name).is_file() and (replace or not prompts.base_path(name).is_file()):
        _write(prompts.base_path(name), prompts.default(name))


def _changes_since_edit(name: str, default: str) -> str:
    """The built-in text's change since the edit was made from it, as a unified diff; "" when there's none."""
    path = prompts.base_path(name)
    try:
        base = path.read_text(encoding="utf-8").strip() if path.is_file() else default
    except (OSError, UnicodeDecodeError):
        return ""
    lines = difflib.unified_diff(base.splitlines(), default.splitlines(), "when you edited it", "now", lineterm="", n=1)
    return "\n".join(lines)


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


def _write(path: Path, text: str) -> None:
    """Written whole and then moved into place, so a turn starting meanwhile never reads half of it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(f"{text}\n", encoding="utf-8")
    os.replace(partial, path)
