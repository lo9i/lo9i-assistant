"""The real embedding model: downloads about 120 MB on first use."""

import numpy as np
import pytest

from assistant.core.memory.e5 import E5Embedder

pytestmark = pytest.mark.live


async def test_queries_find_passages_by_meaning_across_languages():
    embedder = E5Embedder()
    passages = ["El auto va al taller el martes", "Prefers window seats on flights"]
    vectors = np.array(await embedder.embed_passages(passages))
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    for query, expected in [("car repair", 0), ("asiento en el avión", 1)]:
        scores = vectors @ np.array(await embedder.embed_query(query))
        assert int(np.argmax(scores)) == expected
