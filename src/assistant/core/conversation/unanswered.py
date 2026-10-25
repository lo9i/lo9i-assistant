"""Tool calls whose run ended before they answered: a tool that raised (a locked database) ends the run after
the model's tool calls were saved but before any result was. Providers refuse a tool call without its result
right after it, so every later message in the conversation would fail. The checkpoint stays as it is; each
call without a result is sent with a stub saying it didn't finish."""

from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, ToolCall, ToolMessage


def answered(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """`messages` with a stub result after the results of each tool call that has none."""
    result: list[BaseMessage] = []
    waiting: list[ToolCall] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            waiting = [call for call in waiting if call["id"] != message.tool_call_id]
        else:
            result.extend(_stub(call) for call in waiting)
            waiting = list(message.tool_calls) if isinstance(message, AIMessage) else []
        result.append(message)
    return result


def _stub(call: ToolCall) -> ToolMessage:
    text = (
        f"[No result: {call['name']} didn't finish, the run ended with an error. Call it again if it's still needed.]"
    )
    return ToolMessage(text, tool_call_id=call["id"], name=call["name"], status="error")
