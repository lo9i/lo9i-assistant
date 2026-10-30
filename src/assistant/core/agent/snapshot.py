from dataclasses import dataclass, field


@dataclass
class MemorySnapshot:
    """What the assistant currently knows about the user, in plain types for the apps."""

    profile: dict[str, list[str]] = field(default_factory=dict)
    # Every section the profile has, in order, so an app can offer to fill the empty ones.
    profile_sections: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    episodes: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
