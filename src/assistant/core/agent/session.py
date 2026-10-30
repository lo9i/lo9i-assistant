from dataclasses import dataclass, field

from assistant.core.conversation.held import Origin


@dataclass
class Session:
    user_id: str
    channel: str
    thread_id: str
    # Where its messages come from beyond the channel, kept with a run held while an update installs, so it
    # shows there when it runs (core/conversation/held.py).
    origin: Origin = field(default_factory=Origin)
