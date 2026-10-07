from typing import Any

from assistant.core.agent import KeptKeys


def kept_keys(data: dict[str, Any]) -> KeptKeys | None:
    """What a removed plugin left kept, from a removal's answer (`kept`)."""
    return KeptKeys(**data["kept"]) if data.get("kept") else None
