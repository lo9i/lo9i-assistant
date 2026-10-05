"""Which systems a plugin runs on: `platforms:` in its server.yaml, or in a skill's SKILL.md header, from a
fixed list. A plugin that declares none runs everywhere. On a system it doesn't run on, a repository's
plugin isn't found at all (core/mcp/install.py, core/skills/install.py), so the apps don't list it, the
agent doesn't offer it, and it can't be installed or updated there."""

import sys

PLATFORMS = ("linux", "macos")
# sys.platform's names for them.
_SYSTEMS = {"darwin": "macos", "linux": "linux"}


def current() -> str:
    """This system, as plugins name it; another system keeps sys.platform's name, which no plugin lists."""
    return _SYSTEMS.get(sys.platform, sys.platform)


def parse(value: object) -> list[str]:
    """The platforms a plugin declares: one name or a list. Raises ValueError for a name not in the list."""
    if value is None:
        return []
    if not isinstance(value, str | list):
        raise ValueError("its platforms must be a name or a list of names")
    names = [value] if isinstance(value, str) else [str(n) for n in value]
    if unknown := sorted(set(names) - set(PLATFORMS)):
        raise ValueError(f"its platforms {', '.join(unknown)} aren't any of {', '.join(PLATFORMS)}")
    return names


def runs_here(platforms: list[str]) -> bool:
    return not platforms or current() in platforms
