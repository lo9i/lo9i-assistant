"""Prompt texts, one Markdown file per prompt in this folder."""

from functools import cache
from importlib.resources import files


@cache
def load(name: str) -> str:
    """Contents of `<name>.md`, without surrounding whitespace."""
    return files(__package__).joinpath(f"{name}.md").read_text(encoding="utf-8").strip()
