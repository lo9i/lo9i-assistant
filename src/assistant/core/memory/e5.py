"""Local embeddings with multilingual E5 small (ONNX, int8, on the CPU).

Multilingual, so a query in one language finds memories written in another. The model files
(about 120 MB) download on first use into the models folder and the model is kept for the life of
the process. Embeddings run one at a time in a worker thread.
"""

import asyncio
from pathlib import Path

import numpy as np
import onnxruntime
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

from assistant.core.config import settings
from assistant.core.memory.embedder import EmbeddingError

_REPO = "Xenova/multilingual-e5-small"
# Pinned, so the files never change under vectors already saved.
_REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
_MODEL_FILE = "onnx/model_quantized.onnx"
_MAX_TOKENS = 512


class E5Embedder:
    model = f"{_REPO}@{_REVISION[:12]}/int8"

    def __init__(self) -> None:
        self._session: onnxruntime.InferenceSession | None = None
        self._tokenizer: Tokenizer | None = None
        self._lock = asyncio.Lock()

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        # E5 was trained with these prefixes; without them, queries match passages worse.
        return await self._embed([f"passage: {text}" for text in texts])

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([f"query: {text}"]))[0]

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        async with self._lock:
            try:
                return await asyncio.to_thread(self._run, texts)
            except Exception as e:
                raise EmbeddingError(f"Couldn't embed with {_REPO}: {e}") from e

    def _run(self, texts: list[str]) -> list[list[float]]:
        session, tokenizer = self._load()
        encoded = tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        inputs = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
        hidden = np.asarray(session.run(None, inputs)[0])
        return _mean_pooled(hidden, mask).tolist()

    def _load(self) -> tuple[onnxruntime.InferenceSession, Tokenizer]:
        if self._session is None or self._tokenizer is None:
            tokenizer = Tokenizer.from_file(_download("tokenizer.json"))
            tokenizer.enable_truncation(_MAX_TOKENS)
            tokenizer.enable_padding()
            self._tokenizer = tokenizer
            self._session = onnxruntime.InferenceSession(_download(_MODEL_FILE), providers=["CPUExecutionProvider"])
        return self._session, self._tokenizer


def _download(filename: str) -> str:
    cache = str(Path(settings.embedding_models_dir).expanduser())
    return hf_hub_download(_REPO, filename, revision=_REVISION, cache_dir=cache)


def _mean_pooled(hidden: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """The average of each text's token vectors, padding left out, normalized to length 1."""
    summed = (hidden * mask[..., None]).sum(axis=1)
    pooled = summed / np.maximum(mask.sum(axis=1, keepdims=True), 1)
    return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)
