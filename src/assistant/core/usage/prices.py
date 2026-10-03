"""What models cost, per million tokens, to turn token counts into money when a report is shown.
The ledger keeps tokens only, so changing a price never changes what was counted.

Anthropic's prices are built in (from its pricing page, 2026-09-25; a cache write is 1.25 times
the input price, for the 5-minute cache). Other models (OpenAI, local servers, Copilot's
subscription) have no cost until MODEL_PRICES in .env sets one, which also overrides these.
"""

from dataclasses import dataclass

from assistant.core.config import settings

_MILLION = 1_000_000


@dataclass(frozen=True)
class Price:
    """US dollars per million tokens."""

    input: float
    output: float
    cache_read: float
    cache_write: float


_BUILT_IN = {
    "claude-fable-5-1": Price(10.0, 50.0, 0.25, 12.5),
    "claude-opus-5-5": Price(4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": Price(2.0, 10.0, 0.20, 2.5),
    "claude-haiku-4-5": Price(1.0, 5.0, 0.10, 1.25),
}


def price(model: str) -> Price | None:
    custom = settings.model_prices.get(model)
    if custom is not None:
        return Price(
            custom.get("input", 0.0),
            custom.get("output", 0.0),
            custom.get("cache_read", custom.get("input", 0.0)),
            custom.get("cache_write", custom.get("input", 0.0)),
        )
    return _BUILT_IN.get(model)


def cost(model: str, input_tokens: int, cache_read: int, cache_write: int, output_tokens: int) -> float | None:
    """`input_tokens` counts every input token, cached ones included. None: the model has no price."""
    known = price(model)
    if known is None:
        return None
    fresh = max(0, input_tokens - cache_read - cache_write)
    dollars = (
        fresh * known.input
        + cache_read * known.cache_read
        + cache_write * known.cache_write
        + output_tokens * known.output
    )
    return dollars / _MILLION
