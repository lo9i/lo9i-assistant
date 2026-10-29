"""The profile's sections (core/memory/profile.py) by name, for /profile and the plain REPL."""

from assistant_terminal.i18n import t, translatable

_SECTIONS = {
    "about": translatable("About"),
    "people": translatable("People"),
    "how_to_reply": translatable("How to reply"),
    "routine": translatable("Routine"),
    "goals": translatable("Goals"),
    "interests": translatable("Interests"),
    "dislikes": translatable("Dislikes"),
    "work": translatable("Work"),
}


def section_label(section: str) -> str:
    """ "how_to_reply" → "How to reply"; one the app doesn't know by its key."""
    return t(_SECTIONS[section]) if section in _SECTIONS else section.replace("_", " ").capitalize()
