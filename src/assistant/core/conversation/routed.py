"""Messages the inbox sent on (dispatch_nodes.py) as its model calls see them: left out, with the line it
recorded for each. They went to another conversation, so a quick answer in the inbox would only read past
unrelated topics and spend tokens on them. History keeps them.

Which messages are left out depends only on the messages themselves, which are only ever appended, so every
call sends the same ones before the new ones and the prompt cache keeps hitting."""

from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from assistant.core.conversation.dispatched import DISPATCH_ID


def without_routed(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """`messages` without the inbox's lines for the messages it sent on, nor those messages: a routed one is
    the user message right before its line. A message moved later gets only a line, after the inbox's last
    reply or line, so nothing else goes with it."""
    left_out = {i for i, m in enumerate(messages) if _is_line(m)}
    left_out |= {i - 1 for i in left_out if i > 0 and isinstance(messages[i - 1], HumanMessage)}
    return [m for i, m in enumerate(messages) if i not in left_out]


def _is_line(message: BaseMessage) -> bool:
    return isinstance(message, AIMessage) and DISPATCH_ID in message.response_metadata
