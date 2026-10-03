"""Chat model construction per provider. Anthropic, Copilot and OpenAI-compatible servers have their
own builders (prompt caching, the token exchange, server URLs); every other provider in
core/llm/providers.py is built by LangChain's `init_chat_model` from the values the user gave.

Every model uses output_version="v1": AI messages are stored in checkpoints as LangChain
standard content blocks (text, reasoning, tool_call, image, file), not provider-native blocks.
Each provider converts them back to its own format on the next request.
"""

import importlib
import json
from collections.abc import Callable
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.output_parsers.openai_tools import PydanticToolsParser
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from assistant.core.config import settings
from assistant.core.llm import copilot
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.providers import provider


def build_llm(choice: ModelChoice, model: str) -> BaseChatModel:
    """`model` (the choice's main or worker model) from the choice's provider. Its package must be
    installed (core/llm/packages.py)."""
    builder = _BUILDERS.get(choice.provider, _langchain)
    return builder(choice, model)


def metered(llm: BaseChatModel, meter: BaseCallbackHandler) -> BaseChatModel:
    """The model, recording its calls with `meter` (core/usage/meter.py). Set on the model itself,
    so LangChain adds it to the run's callbacks: passed in a call's config instead, it would
    replace them, and LangGraph streams replies through one of those."""
    return llm.model_copy(update={"callbacks": [meter]})


def build_structured(
    choice: ModelChoice, model: str, schema: type[BaseModel], meter: BaseCallbackHandler | None = None
) -> Runnable[list[BaseMessage], Any]:
    """A model that answers with an instance of `schema`, its calls recorded with `meter` if given."""
    llm = build_llm(choice, model)
    if meter is not None:
        llm = metered(llm, meter)
    if choice.provider in ("anthropic", "openai"):
        return llm.with_structured_output(schema, method="json_schema")
    if choice.provider != "copilot":
        # Not every provider has strict JSON schemas; tool calling is what they all share.
        return llm.with_structured_output(schema, method="function_calling")
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
            "api_key": choice.values.get("api_key") or None,
        }
    )


def _openai(choice: ModelChoice, model: str) -> BaseChatModel:
    # Without a key or URL in the choice, the SDK reads OPENAI_API_KEY and OPENAI_BASE_URL.
    key = choice.values.get("api_key")
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(key) if key else None,
        base_url=choice.values.get("base_url") or None,
        max_completion_tokens=settings.max_tokens,
        output_version="v1",
        # Ask for token usage on streamed replies too; servers other than OpenAI don't send it unasked.
        stream_usage=True,
    )


def _copilot(choice: ModelChoice, model: str) -> BaseChatModel:
    return copilot.chat_model(model, choice.values.get("api_key", ""), settings.max_tokens)


def _langchain(choice: ModelChoice, model: str) -> BaseChatModel:
    known = provider(choice.provider)
    if known is None:
        raise ValueError(f"Unknown model provider {choice.provider}.")
    options: dict[str, Any] = {k: v for k, v in choice.values.items() if v}
    if "service_account_json" in options:
        options["credentials"] = _google_credentials(options.pop("service_account_json"))
    if known.max_tokens_key:
        options[known.max_tokens_key] = settings.max_tokens
    if known.model_key:
        options[known.model_key] = model
    return init_chat_model(model, model_provider=known.id, output_version="v1", **options)


def _google_credentials(text: str) -> Any:
    """Vertex AI takes credentials, not the key file's text. The module comes with the Vertex AI
    package, installed when that provider is chosen, so it's looked up only then."""
    service_account = importlib.import_module("google.oauth2.service_account")
    return service_account.Credentials.from_service_account_info(
        json.loads(text), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )


_BUILDERS: dict[str, Callable[[ModelChoice, str], BaseChatModel]] = {
    "anthropic": _anthropic,
    "openai": _openai,
    "copilot": _copilot,
}
