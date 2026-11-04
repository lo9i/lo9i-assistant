from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Speech:
    """Mono float samples in [-1, 1]."""

    samples: np.ndarray
    sample_rate: int


class SynthesisError(Exception):
    pass


class Synthesizer(Protocol):
    async def synthesize(self, text: str, voice_id: str) -> Speech:
        """Raises SynthesisError."""
        ...
