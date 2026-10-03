"""Files in messages: saved as uploads and referred to, their content added only when the model is
called. A tool result's files follow the tool results as a user message."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from assistant.core.attachments import Attachment, hydrate, to_tool_content, upload_paths

PNG = b"\x89PNG\r\n\x1a\nfake"


def _calls(*ids: str) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": "read_email", "args": {}, "id": i} for i in ids])


def _result(call_id: str, *attachments: Attachment) -> ToolMessage:
    return ToolMessage(to_tool_content("Mail text", list(attachments)), tool_call_id=call_id, name="read_email")


def test_a_tool_results_files_follow_the_results_as_one_user_message():
    first = _result("a", Attachment("chart.png", "image/png", PNG))
    second = _result("b", Attachment("notes.txt", "text/plain", b"buy milk"))
    hydrated = hydrate([HumanMessage("read them"), _calls("a", "b"), first, second, AIMessage("done")])
    kinds = [type(m).__name__ for m in hydrated]
    assert kinds == ["HumanMessage", "AIMessage", "ToolMessage", "ToolMessage", "HumanMessage", "AIMessage"]
    note = hydrated[2].content[1]["text"]
    assert note.startswith("[File chart.png, saved at ") and "follows the tool results" in note
    files = hydrated[4].content
    assert files[0]["text"] == "[Files from the tool results above]"
    assert any(b.get("type") == "image" and b["mime_type"] == "image/png" for b in files)
    assert any("buy milk" in b.get("text", "") for b in files)


def test_files_the_model_cant_read_are_named_with_their_path_only():
    result = _result("a", Attachment("budget.xlsx", "application/vnd.ms-excel", b"cells"))
    hydrated = hydrate([_calls("a"), result])
    assert len(hydrated) == 2 and "open it with bash" in hydrated[1].content[1]["text"]


def test_hydration_is_the_same_every_time_and_the_files_are_the_conversations():
    messages = [_calls("a"), _result("a", Attachment("chart.png", "image/png", PNG))]
    assert hydrate(messages) == hydrate(messages)
    assert len(upload_paths(messages)) == 1
