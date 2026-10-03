"""Chat model construction per provider. Add a provider by adding a builder to `_BUILDERS`; a
provider that needs more than a builder (Copilot's token exchange) gets a module in this package.

Every model uses output_version="v1": AI messages are stored in checkpoints as LangChain
standard content blocks (text, reasoning, tool_call, image, file), not provider-native blocks.
Each provider converts them back to its own format on the next request.
"""

from collections.abc import Callable
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.output_parsers.openai_tools import PydanticToolsParser
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from assistant.core.config import settings
from assistant.core.llm import copilot
from assistant.core.llm.choice import ModelChoice


def build_llm(choice: ModelChoice, model: str) -> BaseChatModel:
    """`model` (the choice's main or worker model) from the choice's provider."""
    return _BUILDERS[choice.provider](choice, model)


def build_structured(choice: ModelChoice, model: str, schema: type[BaseModel]) -> Runnable[list[BaseMessage], Any]:
    """A model that answers with an instance of `schema`."""
    llm = build_llm(choice, model)
    if choice.provider != "copilot":
        return llm.with_structured_output(schema, method="json_schema")
    # Copilot ignores response_format and refuses a forced tool choice, so the model is asked to
    # answer through the schema as its only tool.
    instruction = HumanMessage(f"Answer only by calling the {schema.__name__} tool.")
    ask = RunnableLambda[list[BaseMessage], list[BaseMessage]](lambda messages: [*messages, instruction])
    return (
        ask | llm.bind_tools([schema], tool_choice="auto") | PydanticToolsParser(tools=[schema], first_tool_only=True)
    )


def _anthropic(choice: ModelChoice, model: str) -> BaseChatModel:
    # Top-level cache_control: the API caches the whole prefix (tools, system, history)
    # up to the last block, and the next call reads it back.
    model_kwargs: dict = {"cache_control": {"type": "ephemeral"}}
    betas = []
    if settings.server_fallbacks:
        model_kwargs["fallbacks"] = "default"
        betas.append("server-side-fallback-2026-07-01")
    # Validated from a mapping: langchain-anthropic types its constructor by field alias
    # (`model_name`, `max_tokens_to_sample`), so the documented keywords don't type-check.
    return ChatAnthropic.model_validate(
        {
            "model": model,
            "max_tokens": settings.max_tokens,
            "output_config": {"effort": settings.effort},
            "output_version": "v1",
            "betas": betas or None,
            "model_kwargs": model_kwargs,
            # None: the SDK reads ANTHROPIC_API_KEY.
            "api_key": choice.api_key or None,
        }
    )


def _openai(choice: ModelChoice, model: str) -> BaseChatModel:
    # Without a key or URL in the choice, the SDK reads OPENAI_API_KEY and OPENAI_BASE_URL.
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(choice.api_key) if choice.api_key else None,
        base_url=choice.base_url or None,
        max_completion_tokens=settings.max_tokens,
        output_version="v1",
    )


def _copilot(choice: ModelChoice, model: str) -> BaseChatModel:
    return copilot.chat_model(model, choice.api_key, settings.max_tokens)


_BUILDERS: dict[str, Callable[[ModelChoice, str], BaseChatModel]] = {
    "anthropic": _anthropic,
    "openai": _openai,
    "copilot": _copilot,
}
