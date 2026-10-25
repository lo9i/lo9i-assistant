"""The inbox's model calls leave out the messages it sent on and their lines, whatever came between them."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from assistant.core.conversation.dispatched import DISPATCH_ID
from assistant.core.conversation.routed import without_routed


def _line(text: str) -> AIMessage:
    return AIMessage(text, response_metadata={DISPATCH_ID: "d1"})


def test_a_routed_message_goes_with_its_line_and_a_quick_exchange_stays():
    asked, answered = HumanMessage("what time is it?"), AIMessage("3 pm.")
    messages = [HumanMessage("book Rome"), _line("→ Started a new conversation."), asked, answered]
    assert without_routed(messages) == [asked, answered]


def test_a_moved_message_leaves_out_only_its_line():
    asked, answered = HumanMessage("what time is it?"), AIMessage("3 pm.")
    assert without_routed([asked, answered, _line("→ Moved “book Rome” to “Trip”.")]) == [asked, answered]


def test_a_tool_result_before_a_line_stays():
    result = ToolMessage("done", tool_call_id="c1")
    assert without_routed([result, _line("→ Moved “x” to a new conversation.")]) == [result]
