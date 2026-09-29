"""Markdown for Telegram, and splitting long replies to fit its message limit."""

import telegramify_markdown

# Below Telegram's 4096-character limit, leaving room for MarkdownV2 escaping.
_CHUNK = 3500


def to_markdown_v2(text: str) -> str:
    return telegramify_markdown.markdownify(text)


def split_text(text: str, limit: int = _CHUNK) -> list[str]:
    """Split on paragraph breaks, then line breaks, then hard cuts, keeping each part within `limit`."""
    chunks: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = _cut_point(rest, limit)
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip("\n")
    return [*chunks, rest] if rest else chunks


def _cut_point(text: str, limit: int) -> int:
    for separator in ("\n\n", "\n", " "):
        cut = text.rfind(separator, 0, limit)
        if cut > limit // 2:
            return cut
    return limit
