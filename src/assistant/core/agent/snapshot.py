from dataclasses import dataclass, field


@dataclass
class MemorySnapshot:
    """What the assistant currently knows about the user, in plain types for gateways."""

    profile: dict[str, list[str]] = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    episodes: list[str] = field(default_factory=list)
