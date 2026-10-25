"""The query of a page of a list the daemon pages (files, notifications)."""


def page_params(offset: int, limit: int | None) -> dict[str, int]:
    """Nothing for the whole list, which is what the daemon sends without them."""
    return ({"offset": offset} if offset else {}) | ({"limit": limit} if limit is not None else {})
