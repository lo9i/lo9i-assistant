"""The assistant's persona (H1): who it is and how it behaves.

Read from `settings.persona_path` (default ~/.lo9i/SOUL.md) when the file exists, so it can be
changed without editing code; otherwise `prompts/persona.md`. Read when an epoch starts, so edits
apply from the next epoch.
"""

import asyncio
from pathlib import Path

from assistant.core.config import settings
from assistant.core.conversation import prompts

DEFAULT_PERSONA = prompts.load("persona")


async def load_persona() -> str:
    return await asyncio.to_thread(_read_persona) or DEFAULT_PERSONA


def _read_persona() -> str:
    path = Path(settings.persona_path).expanduser()
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""
