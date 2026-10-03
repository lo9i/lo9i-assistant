"""Turns a Markdown reply into text worth reading aloud: no code, no markup, no bare URLs."""

import re

# Long replies take long to synthesize on the CPU; past this, the rest is left to read.
MAX_CHARS = 2000

_RULES = [
    (re.compile(r"```.*?```", re.S), " "),  # code blocks
    (re.compile(r"`([^`]*)`"), r"\1"),  # inline code keeps its text
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), " "),  # images
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),  # links keep their text
    (re.compile(r"https?://\S+"), " "),  # bare URLs
    (re.compile(r"^\s{0,3}#{1,6}\s*", re.M), ""),  # headings
    (re.compile(r"^\s*([-*+]|\d+\.)\s+", re.M), ""),  # list markers
    (re.compile(r"^\s*\|?[-:| ]{3,}\|?\s*$", re.M), " "),  # table separators
    (re.compile(r"[*_~|>#]+"), " "),  # emphasis, tables, quotes
    (re.compile(r"[ \t]+"), " "),
    (re.compile(r" ?\n ?"), "\n"),
    (re.compile(r"\n{2,}"), "\n"),
]


def speakable(markdown: str) -> str:
    text = markdown
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    text = text.strip()
    if len(text) <= MAX_CHARS:
        return text
    cut = text.rfind(". ", 0, MAX_CHARS)
    return text[: cut + 1 if cut > MAX_CHARS // 2 else MAX_CHARS]
