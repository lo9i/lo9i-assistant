"""A tool result's files the model can't read (an email's spreadsheet) are named with where they're
saved, for bash, instead of failing the model call. Images in tool results: test_uploads.py."""

from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from assistant.core.attachments import Attachment, hydrate, reference


@pytest.mark.parametrize("images_in_tool_results", [True, False])
def test_a_file_the_model_cant_read_is_named_with_its_path(images_in_tool_results):
    sheet = reference(Attachment("budget.xlsx", "application/vnd.ms-excel", b"cells"))
    calls = AIMessage("", tool_calls=[{"name": "read_email", "args": {}, "id": "a"}])
    result = ToolMessage("Mail text", tool_call_id="a", name="read_email", artifact=[sheet])
    hydrated = hydrate([calls, result], images_in_tool_results)
    texts = [b.get("text", "") for m in hydrated[1:] for b in cast(list[dict[str, Any]], m.content)]
    assert any("budget.xlsx (application/vnd.ms-excel) saved at" in t and "open it with bash" in t for t in texts)
