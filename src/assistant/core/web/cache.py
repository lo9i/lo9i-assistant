"""Short-lived in-process cache for search results and fetched pages (W4).

Only an optimization: each process has its own, and nothing depends on a hit.
"""

import time
from typing import Any

from assistant.core.config import settings


class TtlCache:
    def __init__(self) -> None:
        self._entries: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        entry = self._entries.get(key)
        if entry is None or time.monotonic() - entry[0] > settings.web_cache_minutes * 60:
            self._entries.pop(key, None)
            return None
        return entry[1]

    def put(self, key: Any, value: Any) -> None:
        if settings.web_cache_minutes > 0:
            self._entries[key] = (time.monotonic(), value)
