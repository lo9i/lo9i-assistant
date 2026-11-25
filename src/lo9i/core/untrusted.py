"""Text from outside the user, which anyone can write instructions into: web pages and search results, email,
the results of untrusted MCP servers, and what a subagent that read some answers. It reaches the model wrapped in
markers that say it's data (`wrap`), cleaned of the characters people don't see (core/hidden_text.py); the apps show
it without them (`shown`). A run whose messages since its user message hold some is tainted (`taint_source`), which
core/tainted.py acts on.

The markers are written once, when the result is made, so the checkpoint and the prompt cache keep them byte for
byte; markers inside the text are escaped, so it can't close them early."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from lo9i.core.conversation import prompts
from lo9i.core.hidden_text import strip_hidden

_OPEN = '<untrusted-data source="'
_CLOSE = "</untrusted-data>"
_MARKER = re.compile(r"<(/?untrusted-data)", re.IGNORECASE)
_SOURCE = re.compile(r'<untrusted-data source="([^"]*)">')
_WRAPPED = re.compile(r'<untrusted-data source="[^"]*">\n(.*?)\n</untrusted-data>', re.DOTALL)
_ESCAPED = re.compile(r"&lt;(/?untrusted-data)", re.IGNORECASE)
# In a subagent's state: the source its delegating run was tainted by, "" when it wasn't.
TAINTED_BY = "tainted_by"


def wrap(text: str, source: str) -> str:
    """`text` as data from `source` (a tool's name, a server's): marked, cleaned, its own markers escaped."""
    if not text:
        return text
    inside = _MARKER.sub(r"&lt;\1", strip_hidden(text))
    named = source.replace('"', "'")
    return f'{_OPEN}{named}">\n{prompts.default("untrusted_data")}\n{inside}\n{_CLOSE}'


def wrap_blocks(content: str | list[Any], source: str) -> str | list[Any]:
    """A result's content, its text blocks wrapped; files left as they are."""
    if isinstance(content, str):
        return wrap(content, source)
    return [_wrapped_block(block, source) for block in content]


def _wrapped_block(block: Any, source: str) -> Any:
    if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
        return {**block, "text": wrap(block["text"], source)}
    return block


def shown(text: str) -> str:
    """`text` as the apps show it: without the markers and the note for the model, its own markers as they were."""
    if not holds(text):
        return text
    note = prompts.default("untrusted_data")
    bare = _WRAPPED.sub(lambda found: found.group(1).removeprefix(note).strip("\n"), text)
    return _ESCAPED.sub(r"<\1", bare)


def holds(text: str) -> bool:
    """Whether `text` has data from outside in it."""
    return _SOURCE.search(text) is not None


def source_in(messages: Sequence[BaseMessage]) -> str:
    """Where the outside content the current run read came from (since its last user message); "" for none."""
    start = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)), 0)
    for message in messages[start:]:
        if isinstance(message, HumanMessage | ToolMessage) and (found := _SOURCE.search(message.text)):
            return found.group(1)
    return ""


def taint_source(state: Mapping[str, Any]) -> str:
    """A graph state's taint: what a subagent inherited, else what its run read."""
    return state.get(TAINTED_BY) or source_in(state.get("messages") or [])
