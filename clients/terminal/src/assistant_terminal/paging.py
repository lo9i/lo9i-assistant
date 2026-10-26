"""A list the daemon sends a page at a time (files, notifications), as the web app loads it
(`clients/web/src/lib/pagedList.svelte.ts`)."""

from collections.abc import Awaitable, Callable

# How many items a page brings as the list is scrolled.
PAGE_SIZE = 50
# The most the daemon sends in one page (`daemon/api.py::_PageLimit`), for loading again what was shown.
PAGE_MAX = 200

type Load[T] = Callable[[int, int], Awaitable[list[T]]]


class Pages[T]:
    """The items loaded so far, each once by its key, and whether the daemon has more after them."""

    def __init__(self, load: Load[T], key: Callable[[T], str], size: int = PAGE_SIZE) -> None:
        self._load = load
        self._key = key
        self._size = size
        self.items: list[T] = []
        self.done = False
        self._loading = False
        # Only the newest load's answer is kept, so a page loading while the list is loaded again can't add to it.
        self._latest = 0

    async def reload(self) -> list[T]:
        """From the start again, as many as were loaded, so the list keeps its place: something in it changed."""
        self._latest += 1
        wanted = max(self._size, len(self.items))
        items = await self._from(0, wanted)
        self.items = self._unique(items)
        self.done = len(items) < wanted
        return self.items

    async def more(self) -> list[T]:
        """The next page's items, unless one is loading or there's no more."""
        if self._loading or self.done:
            return []
        call = self._latest
        self._loading = True
        try:
            page = await self._load(len(self.items), self._size)
        finally:
            self._loading = False
        if call != self._latest:
            return []
        return self._added(page)

    def _added(self, page: list[T]) -> list[T]:
        """The page's items not loaded yet: one that came again (the list grew at its start) stays where it was."""
        known = {self._key(item) for item in self.items}
        added = self._unique([item for item in page if self._key(item) not in known])
        self.items = self.items + added
        self.done = len(page) < self._size
        return added

    async def _from(self, offset: int, wanted: int) -> list[T]:
        limit = min(wanted, PAGE_MAX)
        page = await self._load(offset, limit)
        if len(page) < limit or wanted == limit:
            return page
        return page + await self._from(offset + limit, wanted - limit)

    def _unique(self, items: list[T]) -> list[T]:
        keys: set[str] = set()
        unique = []
        for item in items:
            if self._key(item) not in keys:
                keys.add(self._key(item))
                unique.append(item)
        return unique
