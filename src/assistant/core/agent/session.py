from dataclasses import dataclass


@dataclass
class Session:
    user_id: str
    channel: str
    thread_id: str
