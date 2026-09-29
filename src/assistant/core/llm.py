"""Chat model construction per provider. Add a provider by adding a builder to `_BUILDERS`.

Every model uses output_version="v1": AI messages are stored in checkpoints as LangChain
standard content blocks (text, reasoning, tool_call, image, file), not provider-native blocks.
Each provider converts them back to its own format on the next request.
"""

from collections.abc import Callable

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from assistant.core.config import settings


def build_llm(model: str) -> BaseChatModel:
    return _BUILDERS[settings.provider](model)


def _anthropic(model: str) -> BaseChatModel:
    kwargs = {}
    if settings.server_fallbacks:
        kwargs = {"betas": ["server-side-fallback-2026-07-01"], "model_kwargs": {"fallbacks": "default"}}
    return ChatAnthropic(
        model=model,
        max_tokens=settings.max_tokens,
        output_config={"effort": settings.effort},
        output_version="v1",
        **kwargs,
    )


def _openai(model: str) -> BaseChatModel:
    # Reads OPENAI_API_KEY from the environment.
    return ChatOpenAI(model=model, max_tokens=settings.max_tokens, output_version="v1")


_BUILDERS: dict[str, Callable[[str], BaseChatModel]] = {
    "anthropic": _anthropic,
    "openai": _openai,
}
