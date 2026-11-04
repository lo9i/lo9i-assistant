"""Turns memory texts and search queries into vectors, so memory can be searched by meaning."""

from typing import Protocol


class EmbeddingError(Exception):
    """The model couldn't be loaded or couldn't embed the texts."""


class Embedder(Protocol):
    # Names the model and its version. Vectors from different models can't be compared, so the
    # index re-embeds whatever another model made.
    model: str

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Vectors for texts to be found, normalized to length 1."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """The vector for a search query, normalized to length 1."""
        ...
