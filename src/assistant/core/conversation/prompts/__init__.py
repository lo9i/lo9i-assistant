"""Prompt texts, one Markdown file per prompt in this folder.

The user can edit the ones in EDITABLE (core/conversation/prompt_edits.py). An edit is a file of its own,
the persona's at `settings.persona_path` (SOUL.md) and the others under `settings.prompts_dir`, which
load() reads each time instead of the packaged text, so it applies without a restart.
"""

import logging
from functools import cache
from importlib.resources import files
from pathlib import Path

from assistant.core.config import settings

logger = logging.getLogger(__name__)

EDITABLE = ("persona", "operating", "channels")


class UnreadableEditError(Exception):
    """An edit that can't be read: not UTF-8, or not readable by the daemon."""


@cache
def default(name: str) -> str:
    """The packaged `<name>.md`, without surrounding whitespace."""
    return files(__package__).joinpath(f"{name}.md").read_text(encoding="utf-8").strip()


def load(name: str) -> str:
    """The user's edit of `<name>.md` when there is one, else the packaged text. An editable prompt's edit
    is read from disk on every call, so call it off the event loop for one of those. An edit that can't be
    read is logged and the packaged text used, so a broken file never stops the assistant; Settings → System
    prompt shows the problem and resets it."""
    try:
        return edited(name) or default(name)
    except UnreadableEditError as e:
        logger.warning("%s Using the built-in text.", e)
        return default(name)


def edited(name: str) -> str:
    """The user's edit of an editable prompt; empty when there is none. Raises UnreadableEditError."""
    if name not in EDITABLE:
        return ""
    path = edit_path(name)
    try:
        return path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    except (OSError, UnicodeDecodeError) as e:
        raise UnreadableEditError(f"Can't read {path}: {e}.") from e


def base_path(name: str) -> Path:
    """Where the built-in text an edit was made from is kept, to tell when the built-in one changed since."""
    return Path(settings.prompts_dir).expanduser() / f"{name}.base.md"


def edit_path(name: str) -> Path:
    """Where the user's edit of an editable prompt is kept."""
    if name == "persona":
        return Path(settings.persona_path).expanduser()
    return Path(settings.prompts_dir).expanduser() / f"{name}.md"
