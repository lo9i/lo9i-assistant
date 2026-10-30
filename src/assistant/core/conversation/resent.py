"""What the user sent the agent the conversation is handed to that it hadn't taken when its run was stopped or
failed, sent to it again as the next message (core/agent/handoffs.py). The run before shows those messages
already, as not taken, so the apps show this one as them sent again, never as new ones: its message keeps a mark
in `additional_kwargs`, which no model call sends, history shows it with it (display.py), and the run that sends
it is announced with it (daemon/runs.py)."""

from langchain_core.messages import BaseMessage

RESENT = "lo9i_resent"


def kept(resent: bool) -> dict[str, bool]:
    """What the message keeps when it's those messages `resent`; nothing for any other."""
    return {RESENT: True} if resent else {}


def of(message: BaseMessage) -> bool:
    """The message is messages sent again."""
    return message.additional_kwargs.get(RESENT) is True
