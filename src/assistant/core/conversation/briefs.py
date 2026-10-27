"""A coding task the assistant wrote for the agent it handed a conversation to (core/agent_tasks/tools.py,
core/tools/side.py), sent there as the conversation's next message. The user didn't write it, so the apps show
it as the task it is, never as the user's own message: its message keeps the agent's name in
`additional_kwargs`, which no model call sends, history shows it as a brief (display.py), and the run that
sends it is announced with it (daemon/runs.py)."""

from langchain_core.messages import BaseMessage

BRIEF = "lo9i_brief"


def kept(agent: str) -> dict[str, str]:
    """What a brief's message keeps for `agent`; nothing for "", a message the user wrote."""
    return {BRIEF: agent} if agent else {}


def agent_of(message: BaseMessage) -> str:
    """The agent a brief was written for; "" for any other message."""
    agent = message.additional_kwargs.get(BRIEF)
    return agent if isinstance(agent, str) else ""
