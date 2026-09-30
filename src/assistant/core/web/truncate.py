"""Long pages: keep the beginning and end, save the full text in the workspace (W3)."""

import hashlib
from pathlib import Path

from assistant.core.config import settings
from assistant.core.web.results import Page

_HEAD_SHARE = 0.7
_TAIL_SHARE = 0.2


def fit(page: Page) -> str:
    """The page text, shortened to the configured limit when needed. Writes to disk; call off the event loop."""
    text = page.text
    limit = settings.web_extract_max_chars
    if len(text) <= limit:
        return text
    relative = _save(page)
    head, tail = text[: int(limit * _HEAD_SHARE)], text[-int(limit * _TAIL_SHARE) :]
    omitted = len(text) - len(head) - len(tail)
    note = (
        f"[{omitted} characters omitted. The full text is saved in the workspace at {relative}. "
        f"Read more with bash, for example: grep -n 'keyword' {relative}, or sed -n '100,200p' {relative}]"
    )
    return f"{head}\n\n{note}\n\n{tail}"


def _save(page: Page) -> str:
    relative = f"web/{hashlib.sha256(page.url.encode()).hexdigest()[:16]}.md"
    path = Path(settings.workspace_dir).expanduser() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {page.title}\n\nSource: {page.url}\n\n{page.text}", encoding="utf-8")
    return relative
