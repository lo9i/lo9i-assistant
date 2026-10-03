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
from pydantic import BaseModel

from assistant.core.config import settings
from assistant.core.llm import copilot


def build_llm(model: str) -> BaseChatModel:
    return _BUILDERS[settings.provider](model)


def build_structured(model: str, schema: type[BaseModel]) -> Runnable[list[BaseMessage], Any]:
    """A model that answers with an instance of `schema`."""
    llm = build_llm(model)
    if settings.provider != "copilot":
        return llm.with_structured_output(schema, method="json_schema")
    # Copilot ignores response_format and refuses a forced tool choice, so the model is asked to
    # answer through the schema as its only tool.
    instruction = HumanMessage(f"Answer only by calling the {schema.__name__} tool.")
    ask = RunnableLambda[list[BaseMessage], list[BaseMessage]](lambda messages: [*messages, instruction])
    return (
        ask | llm.bind_tools([schema], tool_choice="auto") | PydanticToolsParser(tools=[schema], first_tool_only=True)
    )


def _anthropic(model: str) -> BaseChatModel:
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
        }
    )


def _openai(model: str) -> BaseChatModel:
    # Reads OPENAI_API_KEY from the environment.
    return ChatOpenAI(model=model, max_completion_tokens=settings.max_tokens, output_version="v1")


def _copilot(model: str) -> BaseChatModel:
    return copilot.chat_model(model, settings.copilot_github_token, settings.max_tokens)


_BUILDERS: dict[str, Callable[[str], BaseChatModel]] = {
    "anthropic": _anthropic,
    "openai": _openai,
    "copilot": _copilot,
}
