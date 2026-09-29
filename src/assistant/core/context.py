from dataclasses import dataclass


@dataclass
class Context:
    """Per-run values passed to graph nodes and tools. Not stored in checkpoints."""

    user_id: str
    channel: str
